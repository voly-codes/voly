# A2A — Backend Reference

`codeops/a2a/` — Agent2Agent orchestration: task decomposition, federation dispatch,
parallel subtask execution, and result merging.

---

## Components

| Module | Role |
|---|---|
| `__init__.py` | `A2AOrchestrator`, `A2AClient`, `dispatch_parallel()` |
| `decomposer.py` | `TaskDecomposer` — rule-based split from `TaskAnalysis` flags |
| `merger.py` | `ResultMerger` — combine subtask outputs |
| `report.py` | `A2AReport` — telemetry report after auto-dispatch |
| `federation.py` | HTTP client for `cf-workers/a2a` (D1 + Queues) |

---

## Auto-dispatch (pipeline)

When `a2a.auto_dispatch: true` (default) and `TaskAnalysis` has 2+ capability flags
or `complexity=high`, `Pipeline.run()` calls `_stage_a2a_auto()`:

```
ROUTE → _should_dispatch_a2a() → TaskDecomposer → dispatch_parallel() → ResultMerger
```

Config (`codeops.yaml` → `a2a`):

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Master switch |
| `auto_dispatch` | `true` | Auto-decompose complex tasks |
| `min_flags_for_dispatch` | `2` | Min capability flags to trigger |
| `task_timeout_seconds` | `120` | Poll timeout per auto-dispatch run |
| `federation_url` | — | CF A2A worker URL |

---

## Recursion guard (P0)

A2A subtasks run through `pipeline_server.py` → `Pipeline.run()`. Without a guard,
auto-dispatch would re-decompose every subtask into more subtasks (infinite recursion).

**Skipped when any of:**

- `delegate_to_a2a=False` (always set by pipeline server for subtasks)
- `CODEOPS_A2A_NESTED=1` env var (set by pipeline server during subtask runs)
- `context["a2a_parent_task_id"]` present (from `task_id` / `a2a_parent_task_id` in POST body)

CF agent worker passes `a2a_parent_task_id: task_id` in `/run` requests.

---

## Context handoff between waves

`dispatch_parallel()` runs subtasks in dependency waves:

1. Wave 0 — no `depends_on` (parallel)
2. Poll until terminal state
3. Wave 1+ — inject prior results via `TaskDecomposer.inject_prior_context()`
   into reviewer/tester/devops descriptions before dispatch

Example enriched description:

```
Review code and tests using developer context

## Prior subtask results
### developer
def add(): return 1
```

---

## Agent role passing

| Layer | Mechanism |
|---|---|
| `pipeline_server.py` | `force_agent=agent` on `Pipeline.run()` |
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
codeops run "implement X, write tests, review" --a2a-delegate   # explicit A2A path
# auto-dispatch triggers without flag when a2a.enabled + complex task
```

Web UI: `a2a_delegate` on `/api/run` maps to `delegate_to_a2a`.

---

## Env vars

| Var | Used by |
|---|---|
| `CODEOPS_A2A_NESTED` | Pipeline — skip auto-dispatch for subtasks |
| `PIPELINE_RUNNER_URL` | CF agent worker → local pipeline server |
| `PIPELINE_RUNNER_TOKEN` | Auth for pipeline server |
| `A2A_FEDERATION_URL` / `A2A_FEDERATION_TOKEN` | Federation callbacks |
