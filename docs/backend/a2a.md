# A2A — Backend Reference

`voly/a2a/` — Agent2Agent orchestration: task decomposition, federation dispatch,
parallel subtask execution, and result merging.

---

## Components

| Module | Role |
|---|---|
| `__init__.py` | `A2AOrchestrator`, `A2AClient`, `dispatch_parallel()` |
| `decomposer.py` | `TaskDecomposer` — rule-based split from `TaskAnalysis` flags |
| `multiagent.py` | Public surface: `run_local`, `LeadOrchestrator`, `merge_report` re-exports |
| `multiagent_run.py` | `_LocalRun` + wave scheduling (`run_local` implementation) |
| `multiagent_plan.py` | Plan-gate setup / `finish_step_plan` |
| `multiagent_roles.py` | Role prepare / executor / chat helpers |
| `hybrid.py` | Role → `chat` / `executor` policy + `make_agent_runner_executor` |
| `context.py` | Role prompts, git-diff evidence, skills/memory blocks |
| `waves.py` | Dependency-wave grouping for parallel chat roles |
| `chat_fallback.py` | Healthy-provider fallback loop for chat roles |
| `assignment.py` | Tiers, outcome evaluation, `VOLY_A2A_EXCLUDE_PROVIDERS` |
| `lead.py` | Lead orchestrator (tier + skills; `lead_mode` auto/llm/deterministic) |
| `merger.py` | `ResultMerger` — combine subtask outputs |
| `report.py` | `A2AReport` + `merge_report` for local multi-agent |
| `cwd_lock.py` | Cross-process executor lock on shared `--cwd` |
| `federation.py` | HTTP client for `cf-workers/a2a` (D1 + Queues) |

Local hybrid details (default executor roles, cascade, plan gates): see
[`docs/backend/pipeline.md`](pipeline.md) § Multi-agent / Hybrid.

---

## Frontend roles

Four frontend-focused roles extend `ROLE_REGISTRY` (`voly/a2a/roles.py`). Each defines
`decomposer_signals` (keyword substrings) and `capability_requirements` for
capability-aware assignment.

| Role | Tier | Mode | Signals (sample) | Capability requirements |
|---|---|---|---|---|
| `ui_architect` | standard | chat | `svelte`, `react`, `frontend`, `design system`, `tailwind` | `frontend >= 0.70` |
| `visual_reviewer` | premium | chat | `screenshot`, `figma`, `ui review`, `wcag`, `accessibility` | `frontend >= 0.75`, `image_input: true` |
| `browser_tester` | standard | executor | `e2e`, `playwright`, `cypress`, `browser test` | `frontend >= 0.70`, `browser_tools: true` |
| `ux_reviewer` | cheap | chat | `ux`, `usability`, `user flow`, `interaction design` | `frontend >= 0.55` |

Bare tokens like `design`, `visual`, `ui`, `component`, and `layout` are intentionally
omitted — they false-positive on backend prompts (e.g. “architecture design”).

**`ui_architect`** — plans component structure, state, routing, and visual hierarchy
(chat-only; no full implementations).

**`visual_reviewer`** — reviews pixel accuracy, WCAG 2.1 AA accessibility, responsive
behavior, and design-system consistency. Requires `image_input` capability on the
assigned provider. `inject_prior_context=True` so prior subtask summaries are appended
before the review prompt.

**`browser_tester`** — executor role (default executor: `cursor`); writes Playwright or
Cypress end-to-end tests for user flows, visual regressions, and cross-browser checks.
Requires `browser_tools: true` on the matched executor.

**`ux_reviewer`** — cheap-tier chat role for usability, information architecture, and
interaction patterns. `inject_prior_context=True` for context from earlier waves.

### Signal-driven decomposition

`TaskDecomposer._signal_driven_roles(task)` scans the task string against every role's
`decomposer_signals` in `ROLE_REGISTRY`. Multi-word signals use case-insensitive
substring match; single-word signals use word-boundary (`\b`) match. Roles with
empty signals are skipped.

- When flag-based decomposition already produced subtasks, `_with_signal_roles()` appends
  any matched roles not already in the list (with `depends_on` set to prior indices).
- When flag-based decomposition returns nothing but signals match, `_signal_subtasks()`
  builds a subtask list from the matched roles alone (e.g. screenshot review tasks).

Vision-capable model providers for `visual_reviewer` are seeded in
`voly/capability/seeds/kimi-cli-vision.yaml` and `claude-vision.yaml`.

---

## Capability-aware role assignment

`LeadOrchestrator` accepts optional `matcher` (`ExecutorMatcher`) and
`project_context` (dict with `task_features` from `REPO_INTELLIGENCE` or project scan).

For each subtask with a role, when `matcher` is set:

1. Resolve `kind`: `executor` if the role is in `EXECUTOR_CAPABLE_ROLES`, else
   `model_provider`.
2. Call `matcher.find_executors(MatchRequest(dimension=role_to_dimension(role), kind=kind, …))`.
3. When `result.recommended` is not `None`, use its id (executor) or model/provider
   hint on the assignment.

When the matcher returns `None` or raises, assignment falls back to the existing
tier resolution (`_ROLE_TIER` + `resolve_role_model()`).

---

## Auto-dispatch (pipeline)

When `a2a.auto_dispatch: true` (default) and `TaskAnalysis` has 2+ capability flags
or `complexity=high`, `Pipeline.run()` calls `_stage_a2a_auto()`.
`analyze_task` also sets `requires_review=True` whenever two or more capability
flags are already set (e.g. code-gen + tests → developer + tester + reviewer).

```
ROUTE → _should_dispatch_a2a() → TaskDecomposer → dispatch_parallel() → ResultMerger
```

Config (`voly.yaml` → `a2a`):

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master switch |
| `auto_dispatch` | `true` | Auto-decompose complex tasks |
| `min_flags_for_dispatch` | `2` | Min capability flags to trigger |
| `task_timeout_seconds` | `600` | Per-role hybrid executor timeout (watchdog base) |
| `architect_max_tokens` | `4096` | Architect plan chat budget |
| `executor_roles` | (built-in) | Empty → developer, bugfixer, tester, devops |
| `federation_url` | — | CF A2A worker URL |

---

## Recursion guard (P0)

A2A subtasks run through `pipeline_server.py` → `Pipeline.run()`. Without a guard,
auto-dispatch would re-decompose every subtask into more subtasks (infinite recursion).

**Skipped when any of:**

- `delegate_to_a2a=False` (always set by pipeline server for subtasks)
- `VOLY_A2A_NESTED=1` env var (set by pipeline server during subtask runs)
- `context["a2a_parent_task_id"]` present (from `task_id` / `a2a_parent_task_id` in POST body)

CF agent worker passes `a2a_parent_task_id: task_id` in `/run` requests.

---

## Spend limit — early exit

`run_local` stops the whole chain the moment a sub-agent comes back
`spend_limited` (budget exhausted): remaining roles are marked
`error="Spend limit exceeded"` **without another `AIGateway.chat()` call** and the
loop breaks. Same observable outcome as walking every role, minus the wasted
calls — the budget won't recover mid-run. Tested in
`tests/test_failure_paths.py` and `tests/test_tenant_isolation.py`.

## Context handoff between waves

`dispatch_parallel()` (federation) and `run_local` (local) both process roles in
dependency waves:

1. Wave 0 — no `depends_on` (parallel where allowed)
2. Later waves — inject prior results via `TaskDecomposer.inject_prior_context()`
   (files list + truncated body, labeled **untrusted**). Reviewer/tester also
   receive a git-diff evidence block from prior `files_touched`.

Example enriched description:

```
Review code and tests using developer context

## Prior subtask summaries (untrusted context)
### developer
Files touched:
- app/main.py
implemented restore endpoint
```

---

## Agent role passing

| Layer | Mechanism |
|---|---|
| `pipeline_server.py` | `force_agent=agent` on `Pipeline.run()` |
| `voly a2a call` (local) | `Pipeline.run(force_agent=agent_name, context={cwd, project_cwd})` — not `agent=` |
| `cf-workers/agent/pipeline.ts` | passes `agent` to `/run` and `/infer` |
| `cf-workers/agent/infer.ts` | system prompt prefix: `You are the {agent} agent...` |

---

## Federation worker (`cf-workers/a2a`)

| Endpoint | Behavior |
|---|---|
| `POST /tasks` | Create task; queue dispatch when `agent_name` set |
| `GET /tasks/:id` | Task status |
| `POST /tasks/:id/complete` | Agent callback; **no-op if already completed** |
| Queue consumer | Skips dispatch when state ≠ `submitted` |

Agent worker (`cf-workers/agent`):

- `getA2ATaskState()` — fetch status before re-execute
- Skips `/agents/:name/run` when task already `completed` or `failed`
- `completeA2ATask()` — callback to federation after pipeline run

---

## CLI / API

```bash
voly run "implement X, write tests, review" --a2a-delegate   # explicit A2A path
# auto-dispatch triggers without flag when a2a.enabled + complex task
```

Web UI: `a2a_delegate` on `/api/run` maps to `delegate_to_a2a`.

---

## Env vars

| Var | Used by |
|---|---|
| `VOLY_A2A_NESTED` | Pipeline — skip auto-dispatch for subtasks |
| `PIPELINE_RUNNER_URL` | CF agent worker → local pipeline server |
| `PIPELINE_RUNNER_TOKEN` | Auth for pipeline server |
| `A2A_FEDERATION_URL` / `A2A_FEDERATION_TOKEN` | Federation callbacks |
