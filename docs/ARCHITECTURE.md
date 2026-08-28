# VOLY — Architecture

## Current architecture

VOLY is a project-agnostic control plane for AI agents. The target project is passed
via `--cwd`; VOLY handles orchestration, routing, cost control, optimization, and telemetry.

There are **two independent task execution paths**:

```text
Developer / UI / CI
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Entry points                                                    │
│ CLI (voly run ...) · POST /api/run · voly runner          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
┌─────────────────┐       ┌──────────────────────────────────────┐
│ PIPELINE PATH   │       │ EXECUTOR PATH                        │
│ (text / inference)      │ (file-capable agents)                │
│                 │       │                                      │
│ Pipeline.run()  │       │ AgentRunner.run()                    │
│   ↓ ROUTE       │       │   ↓ _dspy_plan_task()  (optional)    │
│   ↓ MEMORY      │       │   ↓ executor.run(refined_task, cwd)  │
│   ↓ RTK         │       │   ↓ BILLING FALLBACK CHAIN:          │
│   ↓ SKILL_SUGGEST*      │     claude-code → cursor → deepseek  │
│   ↓ SKILL       │       │     → wrangler → opencode → zen      │
│   ↓ HEADROOM    │       │   ↓ _dspy_store_example()            │
│   ↓ DSPY*       │       │   ↓ WorkReport (git diff)            │
│   ↓ MODEL_CALL  │       │   ↓ emit TaskEvent                   │
│   ↓ MEMORY_STORE│       └──────────────────────────────────────┘
│   ↓ TaskEvent   │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ AIGateway.chat()  (sole exit to chat models)     │
│ DLP → Cache → Rate limit → Spend limit → Provider │
│ Cloudflare AI Gateway · Direct adapters           │
└──────────────────────────────────────────────────┘
```

**Smart dispatch** (`voly/web/routes/run.py`): when `POST /api/run` receives
`executor=pipeline` and the task is complex (≥ `a2a.min_flags_for_dispatch` or
`complexity=high`) it stays in multi-agent; a simple code-gen task promotes to
the executor path (default `claude-code` + cwd). With `--cwd`, multi-agent
**hybrid** runs implement roles via `AgentRunner` and architect/reviewer via chat.

**Tech stack gate** (`voly/catalog/tech_registry.py` + `/api/tech/*` in
`routes/run.py`): pinned framework/version registry with keyword detection, a
category fallback picker for greenfield tasks, a runtime preflight check, and a
confirmed-stack constraint block prepended to the task before pipeline and
executor runs. A non-existent `cwd` is greenfield-scaffolded (dir + `git init` +
stack-aware `.gitignore` + initial commit). Details: `docs/backend/api.md`.

**Code reuse** (`voly reuse`, Layer B): optional CLI/library cycle
search → shallow clone → pack → LLM/heuristic module pick → license-gated copy
into `--cwd` (`vendor/reuse/…`). Reports under `.voly/reuse/reports/`; a fresh
report may be injected into local context. Details: `docs/backend/reuse.md`.

---

## Design principles

1. **VOLY stays project-agnostic.** No product-specific logic in `voly/`.
2. **AIGateway is the sole exit to chat models.** DSPy, InferenceManager, and pipeline chat roles go through it; file-capable executors are a separate path.
3. **Optimization is layered.** RTK, Headroom, and DSPy are independent with explicit fallback.
4. **Shadow before active.** New optimizer behavior starts in shadow, then becomes active.
5. **Runtime state is not source.** `.voly/events/`, datasets, compiled programs are generated artifacts.
6. **Billing fallback chain.** On a billing error the executor is automatically replaced: `claude-code → cursor → deepseek → wrangler → opencode → zen`.

### Bounded workflow layer

Concrete multi-turn product scenarios may compose the two execution paths
without introducing a general workflow engine. The first scenario is
`ReviewUntilClean`: `AgentRunner` performs file changes, an independent reviewer
uses `AIGateway.chat()`, and blocking findings reactivate the runner until a
clean verdict or an explicit round/deadline/spend/failure guardrail stops the
loop. See [`docs/backend/workflows.md`](backend/workflows.md).

### Multi-agent episode layer

`voly/a2a/episode.py` defines the versioned orchestration lineage:
`MultiAgentEpisode -> AgentTrace -> messages/tool calls/artifacts/decisions/metrics`.
The layer links to, rather than replaces, Evidence Foundation and Eval Engine.
Local A2A runs persist episodes under `.voly/episodes/<task_id>.json`; private
trace content is excluded from remote analytics.

`voly/a2a/environments.py` separates interaction patterns from roles. Pipeline,
solver-judge, parallel-solutions, debate and iterative-repair environments share
one episode output contract. Production currently uses the dependency-wave
pipeline adapter. The optional read-only agentic judge is enabled through the
existing `evaluation.llm_judge.mode` (`shadow` or `required`) and appends its
trace and five role metrics to the episode. The next gate is metric calibration
against deterministic evidence and human feedback; only afterward should VOLY
consider self-play or training work.

---

## Layers A/B — make vs delegate

VOLY consists of two layers with different engineering strategies:

| Layer | What it is | Strategy |
|---|---|---|
| **A — model gateway** | Routing/fallback across model providers (anthropic, openai, deepseek, workers-ai, …) | **Delegate.** Mature niche (OmniRoute, LiteLLM, OpenRouter) — do not compete on provider breadth. Stabilize to a minimum; provider routing is delegated to an external gateway (see “Upstream delegation” below); direct adapters are fallback. |
| **B — orchestration of file-capable CLI agents** | Executor chain (agents write files), billing fallback across CLIs, multi-agent decomposition (model tier per role), task cost telemetry | **Make.** VOLY’s uniqueness — put all development focus here: chain resilience, honest FinOps accounting, project-agnostic executor path. |

**Upstream delegation (layer A first-class):** `ai_gateway.upstream: "omniroute"` in
`voly.yaml` routes all non-CF `AIGateway.chat()` calls through a single external
gateway (model passthrough or `upstream_model: "auto"`); if it is unavailable —
automatic fallback to the direct adapter of the requested provider
(`upstream_fallback_direct`). Cache, DLP, spend limits, and telemetry do not change —
they live around the call. Details: `docs/backend/ai-gateway.md`.

### Public versioned contracts

The core talks to any external services (self-hosted or managed) through
open versioned interfaces — they are frozen by contract tests
(`tests/test_protocol_contracts.py`):

| Contract | Version | Where documented |
|---|---|---|
| `TaskEvent` (task telemetry) | `schema_version: 3` | `voly/telemetry.py`, `docs/backend/api.md` |
| Cloud analytics allowlist | `schema_version: 1` | `voly/telemetry.py`, `docs/backend/api.md` |
| EvidenceRecord (local) | `schema_version: 3` | `voly/evidence/schema.py`, `docs/backend/evidence.md` |
| Evidence Cloud allowlist | `schema_version: 2` | `voly/evidence/privacy.py`, `docs/backend/evidence.md` |
| Spend protocol (`/spend/record`, `/spend/check`, …) | v1 | `docs/backend/spend-protocol.md` |
| A2A federation | — | `cf-workers/a2a/`, `docs/backend/api.md` |

Changing a contract = version bump + docs update + snapshot update in the contract test.

---

## Pipeline path (text / inference)

`voly/pipeline/core.py:Pipeline.run()` — for text-only tasks.

### Stages

| Stage | Method | What it does |
|---|---|---|
| `INIT` | — | setup |
| `REPO_INTELLIGENCE` | `_stage_repo_intelligence` | Pre-run repo analysis: admission, license, architecture map; feeds `task_features` to capability matcher |
| `AGUI_START` | `_stage_agui_start` | AG-UI SSE session |
| `A2A_DISCOVER` | `_stage_a2a` / `_stage_a2a_auto` | A2A federation + auto-decompose |
| `A2A_DELEGATE` | `_stage_a2a_auto` → `_run_multiagent_local` | lead assigns tier+skills; hybrid: implement roles → AgentRunner, architect/reviewer → AIGateway (`a2a.execution_mode=local`) |
| `ROUTE` | `_stage_route` | AgentRouter → RouteDecision |
| `MEMORY_RETRIEVE` | `_stage_memory_retrieve` | MemoryStore.search |
| `RTK_FILTER` | `_stage_rtk` | RTK token stats |
| `SKILL_SUGGEST` | `_stage_skill_suggest` | non-blocking marketplace skill suggestions |
| `SKILL_INJECT` | `_stage_skill_inject` | inject skill into system prompt |
| `HEADROOM_COMPRESS` | — | context compression |
| `DSPY_PROGRAM_CALL` | — | DSPyRunner.run() if enabled |
| `MODEL_CALL` | — | AIGateway.chat() |
| `MEMORY_STORE` | `_stage_memory_store` | persist result |
| `AGUI_DONE` | `_stage_agui_done` | close AG-UI stream |
| `DONE` / `ERROR` | — | final + emit TaskEvent |

### PipelineResult

```python
@dataclass
class PipelineResult:
    success: bool
    stage: PipelineStage
    duration_ms: float
    response: GatewayResponse | None
    route: RouteDecision | None
    error: str | None
    injected_skills: list[str]
    tokens_saved_by_rtk: int
    tokens_saved_by_headroom: int
    dspy_used: bool
    dspy_mode: str
    a2a_tasks: list[A2ATask]
```

---

## Executor path (file-capable agents)

`voly/runner/agent_runner.py:AgentRunner.run()` — for tasks that write files.
With Evidence Foundation enabled, the path is:

```text
repository baseline → DSPy plan → executor/fallback → WorkReport
→ root-cause classification → local EvidenceRecord → TaskEvent
```

EvidenceRecord is separate from the frozen TaskEvent v3 contract. It stores a
versioned execution bundle and prevents provider/tool/environment or
pre-existing repository failures from reducing agent capability evidence.

### Billing fallback chain

```
claude-code → cursor → deepseek → wrangler → opencode → zen
(Anthropic)   (Cursor)  (DeepSeek)  (CF)      (OpenCode)  (last resort)
```

`ExecutorResult.billing_error = True` (or `not_available`) → next in chain.
Only file-capable executors. Text-only (`mimo`, workers-ai chat) — not in the chain.

### DSPy in the executor path

```
task
  ↓ _dspy_plan_task()  (if dspy.enabled)
    → TaskPlannerProgram.ChainOfThought → refined_task + success_criteria
  ↓ executor.run(refined_task, cwd)
  ↓ _dspy_store_example()  → datasets_dir/task_planner/*.jsonl
```

### Chain logs

```
voly.chain logger:
[CHAIN:START]            — first attempt
[CHAIN:DSPY_PLAN]        — DSPy refined the task
[CHAIN:RESULT]           — result + billing_error
[CHAIN:BILLING_FALLBACK] — executor switch
[CHAIN:FALLBACK_RESULT]  — fallback result
[CHAIN:DSPY_STORE]       — example saved
```

### Executor table

| Executor | File writes | Billing | Chain position |
|---|---|---|---|
| `claude-code` | yes — Claude CLI | Anthropic | 1st |
| `cursor` | yes — Cursor Agent SDK | Cursor | 2nd |
| `deepseek` | yes — DeepSeek file executor | DeepSeek API | 3rd |
| `wrangler` | yes — LocalPatchApplier | CF Workers AI | 4th |
| `opencode` | yes — OpenCode CLI | opencode.ai | 5th |
| `zen` | yes — opencode CLI | free | 6th (last resort) |
| `mimo` | no — text only | MiMo API | NOT in chain |

---

## Plan gates (Rung B)

Enforced multi-step plans with verification gates. Design:
[`docs/proposals/plan-gate-verification.md`](proposals/plan-gate-verification.md).

| PR | Status | Module |
|---|---|---|
| PR1 | **landed** — types, store, FSM engine | `voly/plan/` |
| PR2 | **landed** — acceptance verifiers | `voly/plan/verify*.py` (`verify` + `verify_types` / `verify_git` / `verify_checks`) |
| PR3 | **landed** — CLI + PlanRunner | `voly plan …`, `voly/plan/runner.py` |
| PR4 | **landed** — multi-agent bridge | `voly/plan/bridge.py` + `run_local` gates |
| PR5 | **landed** — criteria + scanner DX | `criteria.py`, `suggest.py`, `docs/backend/plan.md` |

User guide: [`docs/backend/plan.md`](backend/plan.md).

PR1: `Plan` / `PlanStep` FSM (`pending → running → done → verifying → verified`), dependency **gate**, atomic store under `.voly/plans/`.

PR2: `run_check` / `complete_verification` — evidence-based acceptance
(`command`, `files_exist`, `files_missing`, `git_diff_nonempty`, `git_diff_contains`,
`output_nonempty`, `output_regex`). Unknown types fail closed. Path checks are
cwd-jailed; `command` runs with `shell=False` + timeout.

PR3: `PlanRunner` executes steps (`mode=chat` → AIGateway, `mode=executor` →
AgentRunner), persists state, emits TaskEvent (`workflow=plan:<id>`, summary in
`result`/`stage_log` without schema bump). Config: `plan.*` / `VOLY_PLAN_*`.
CLI: `voly plan run|list|show|status|validate`.

PR4: when `plan.enabled` + `mode` shadow|active + `a2a_attach`, multi-agent
`run_local` mirrors roles as plan steps. Dependents start only after prior steps
are **verified**. Defaults: chat `output_nonempty`; optional
`executor_require_git_diff` / `tester_command`. `Assignment.plan_status` + UI badges;
`RunRecord.plan_id` / `step_statuses`.

PR5: `compile_success_criteria()` drafts acceptance from free text (always
`review_required`); `voly plan criteria` / `suggest`; loader fills empty
`acceptance` from step `success_criteria`; scanner can suggest `tester_command`.

Layer C business Decisions reuse the same Plan FSM as two steps:
`approve-option` waits in `verifying`, while dependent `execute-action` remains
blocked in `pending`. Explicit approve/reject is persisted through
`DecisionService`; approval opens the dependency gate but does not itself run
the external action. UI route: `#/decisions`; API: `/api/decisions`.

### `voly/pipeline/` — central orchestrator (text path)

`Pipeline.run()` → stage methods via `_PipelineStageMixin` (`stages.py`), composed from:

`stages_a2a` · `stages_route` · `stages_context` · `stages_emit`

Does not contain product logic.

| Method | Module | Responsibility |
|---|---|---|
| `_stage_agui_start` / `_stage_agui_done` | `stages_a2a` | AG-UI session |
| `_stage_a2a` / `_stage_a2a_auto` | `stages_a2a` | A2A delegation / multi-agent |
| `_stage_route` | `stages_route` | routing + cost policy |
| `_stage_spend_check` | `stages_route` | pre-call spend limit |
| `_stage_memory_retrieve` / `_stage_memory_store` | `stages_context` | memory search / persist |
| `_stage_rtk` | `stages_context` | RTK stats |
| `_stage_skill_inject` / `_stage_skill_suggest` | `stages_context` | skills |
| `_emit_task_event` | `stages_emit` | telemetry |

### `voly/runner/` — executor path

`AgentRunner.run()` orchestrates: repository baseline → DSPy plan → executor →
billing fallback → git diff → EvidenceRecord → telemetry.

Capability-aware fallback (`voly/capability/fallback.py`) replaces the static `BILLING_FALLBACK_CHAIN` when capability profiles are loaded: `ExecutorMatcher` scores available executors against the task dimension and project features, reordering or excluding executors via `hard_exclude()` before the billing chain runs.

| Module | Role |
|---|---|
| `agent_runner.py` | `AgentRunner` / `RunnerResult` (+ stable re-exports) |
| `executor_factory.py` | `EXECUTOR_NAMES`, `BILLING_FALLBACK_CHAIN`, `_build_executor` |
| `work_report.py` | git porcelain → `WorkReport` |
| `dspy_hooks.py` | optional TaskPlanner plan/store |

### `voly/evidence/` — Evidence Foundation

Local, versioned facts for executor runs. `baseline.py` captures stack and
deterministic pre-run checks; `classifier.py` attributes root cause;
`record.py` binds task/executor/model/runtime/eval-policy versions; `store.py`
writes `.voly/evidence/<task_id>.json` atomically and appends human feedback.
Explicit feedback enters through `voly evidence feedback` or
`POST /api/evidence/{task_id}/feedback`; task ids are path-safe and comments
remain local.
Canonical details: `docs/backend/evidence.md`.

### `voly/evaluation/` — deterministic Eval Engine

`registry.py` selects a versioned built-in policy before execution;
`engine.py` evaluates executor/safety/trajectory/file-change evidence and
replays exact baseline argv after execution. The bounded trajectory evaluator
aggregates retries and fallback statuses without copying error text, and fails
on safety events or rollbacks. EvalReport is stored in EvidenceRecord v2 but
does not yet gate primary routing. Canonical details:
`docs/backend/evaluation.md`.

Golden datasets are the controlled regression companion to per-run evaluation.
`voly eval validate|run` loads a strict versioned JSON dataset, fingerprints
its canonical content, copies each reviewed fixture into an isolated temporary
workspace, and executes exact argv with `shell=False` and a credential-minimized
environment. Local reports live under `.voly/eval-runs/`; the runner makes no
model calls, but v1 does not enforce OS-level network isolation.

`voly eval calibrate` is the local judge-quality feedback loop. It reads
append-only human calibration events from EvidenceRecord files and aggregates
confusion matrices per exact policy/rubric/model/provider/threshold lineage.
Reports are observational: they never tune thresholds or routing automatically.

Documentation tasks additionally use the project-agnostic Markdown link
evaluator and a pending human-review requirement. `EvidenceStore` resolves the
review check atomically when explicit feedback arrives.

Testing tasks require a retained conventional test artifact in addition to
baseline replay. Security tasks scan only changed supported source files,
redact matched source values from evidence, and remain pending until explicit
human review.

An opt-in rubric judge calls models only through `AIGateway.chat()`. Shadow mode
records non-gating evidence; required mode extends the policy's success
definition. Strict parsing, bounded inputs, separate policy versions, total
cost accounting and human-feedback calibration prevent judge output from
becoming an unversioned source of truth.

```python
BILLING_FALLBACK_CHAIN = ["claude-code", "cursor", "deepseek", "wrangler", "opencode", "zen"]
```

### `voly/executor/` — file-capable runtimes

| Executor | File | Purpose |
|---|---|---|
| `base.py` | — | `Executor`, `ExecutorResult`, `billing_error`, `_is_billing_error()` |
| `claude_code.py` | ClaudeCodeExecutor | runs `claude` CLI |
| `wrangler.py` | WranglerExecutor | POST /infer → LocalPatchApplier |
| `patch.py` | LocalPatchApplier | parses FILE blocks + unified diffs → writes to disk |
| `zen.py` | ZenExecutor | opencode CLI, free tier |
| `cursor.py` | CursorExecutor | Cursor Agent |
| `opencode.py` | OpenCodeExecutor | OpenCode CLI/API |
| `deepseek.py` | DeepSeekExecutor | file-capable DeepSeek executor (in billing chain) |

### `voly/inference/runtime.py` — runtime selection

| Runtime | Role |
|---|---|
| `ClassicRuntime` | direct call via `AIGateway.chat()` |
| `DSPyRuntime` | optional DSPy program → `DSPyRunner` → `AIGateway.chat()` |
| `InferenceManager` | selects runtime, falls back to classic |

### `voly/intelligence/` — repository intelligence

Pre-run analysis of external repositories. Provides license gate, architecture map, reuse candidates, and security risk summary. `task_features` output feeds into the capability matcher for stack-aware scoring.

| Module | Role |
|---|---|
| `schema.py` | `RepositoryIntelligence` and sub-dataclasses |
| `admission.py` | Pre-clone GitHub API checks |
| `license_analyzer.py` | SPDX risk matrix and policy gate |
| `architecture_mapper.py` | Language/framework detection, entrypoints |
| `dependency_analyzer.py` | Manifest parsing (package.json, requirements, go.mod, …) |
| `security_scanner.py` | Pure-Python regex risk patterns (no external tools) |
| `repo_analyzer.py` | Main orchestrator, cache by SHA |

### `voly/capability/` — capability registry

Evidence-based executor routing. Each executor has a measured capability profile; routing score replaces static tier resolution. `ExecutorMatcher` is used by LeadOrchestrator for A2A role assignment.

| Module | Role |
|---|---|
| `schema.py` | `ExecutorCapabilityProfile`, `CapabilityDomain`, `CapabilityMatchResult` |
| `calibration.py` | Benchmark → VOLY dimension mapping |
| `registry.py` | Load/save profiles from `.voly/capability/profiles/` |
| `scorer.py` | Pure routing score + hard-gate functions |
| `matcher.py` | `ExecutorMatcher` — CF Worker `/match` with local fallback |
| `evidence.py` | Fire-and-forget run evidence → local EMA + CF Worker `/profiles/evidence` |
| `fallback.py` | Capability-aware executor fallback (replaces static chain) |
| `packs.py` | Read-only external capability-pack discovery and provenance |
| `pack_admission.py` | Bounded static admission, permissions, risk, quarantine |
| `pack_security_patterns.py` | External prompt/config risk indicators |
| `pack_manifest.py` | Manifest schema v1, provenance, aliases, component hashes |
| `pack_store.py` | Atomic staged install, verification, listing, and removal |
| `seeds/` | Bundled seed profiles for known executors |

External capability repositories are untrusted data. Discovery and admission
may read supported files but never import source modules, execute hooks or
commands, start MCP servers, copy components, or activate them. High and
critical findings quarantine affected components. The staged store copies only
admitted components and remains disconnected from runtime skill injection and
executor routing; staging is not activation.

### `voly/dspy/` — DSPy optimizer layer

Optional layer. Install: `pip install -e ".[dspy]"`.
Two integration points: Pipeline (DSPyRuntime) and AgentRunner (TaskPlannerProgram).

| File | Purpose |
|---|---|
| `adapter.py` | `VOLYDSPyLM` — DSPy LM via `AIGateway.chat()` |
| `runner.py` | `DSPyRunner` — integration with InferenceManager |
| `programs/task_planner.py` | TaskPlannerProgram — executor path planning |
| `programs/reviewer.py` | code-review program |
| `programs/architect.py` | architecture-analysis program |
| `programs/bugfixer.py` | bug-analysis program |
| `programs/documenter.py` | generate-docs program |
| `programs/router.py` | task-routing program |
| `signatures.py` | typed DSPy signatures |
| `compiler.py` | dataset loading + compile |
| `store.py` | versioned program storage |
| `versioning.py` | tags: candidate / production |
| `metrics.py` | optimizer metrics |

### `voly/ai_gateway/` — model gateway

`AIGateway.chat()` — sole exit to providers.

Middleware stack: DLP → Cache → Rate limit → Spend limit → Provider call.

| Provider group | Routing |
|---|---|
| Anthropic / OpenAI / Google / DeepSeek | Cloudflare AI Gateway |
| MiMo | Direct (CUSTOM) |
| OpenCode Zen / GO | Direct (CUSTOM) |
| OmniRoute | Direct (CUSTOM, opt-in) — self-hosted OpenAI-compat gateway |
| Workers AI | CF AI Gateway `/compat` or `env.AI.run()` |
| Executors | bypass gateway — run subprocesses |

### `voly/web/` — backend API

| File | Purpose |
|---|---|
| `server.py` | FastAPI app, CORS, health |
| `routes/run.py` | POST `/api/run` — SSE + smart dispatch + context gather + tech gate endpoints (`/api/tech/*`) + greenfield scaffolding |
| `routes/tasks.py` | GET `/api/tasks`, SSE stream, artifacts |
| `routes/runs.py` | GET `/api/runs` — in-flight RunRecords (Rung A) |
| `routes/evidence.py` | GET local EvidenceRecord; POST explicit human feedback |
| `routes/registry.py` | agents, models, skills |
| `routes/marketplace.py` | skill suggest / install (pre-run gate) |
| `routes/environment.py` | GET `/api/environment` — local readiness |
| `routes/gateway.py` | gateway status |
| `routes/providers.py` | BYOK provider keys (localhost-only) |
| `routes/telemetry.py` | spending analytics |
| `routes/dspy.py` | DSPy status |
| `routes/cf.py` | CF workers status |

### `ui/` — Svelte 5 web dashboard

Hash-based routing: `#/tasks`, `#/gateway`, `#/telemetry`, `#/dspy`.

| Component | Purpose |
|---|---|
| `App.svelte` | nav, hash router, keyboard shortcuts |
| `tasks/RunPanel.svelte` | task runner: executor selector, SSE stream |
| `tasks/RunParams.svelte` | parameters: executor, agent, model, cwd |
| `tasks/RunResult.svelte` | result: content, billing_fallback badge, cost |
| `tasks/TechSelectionModal.svelte` | pre-run tech gate: version dropdowns, runtime preflight badges |
| `tasks/CategoryPickerModal.svelte` | fallback project-type picker when tech detection is empty |
| `tasks/TaskSidebar.svelte` | task list, search, filter |
| `tasks/PipelineInspector.svelte` | pipeline stages, token flow, DSPy metadata |
| `tasks/CostPanel.svelte` | spend summary cards |
| `tasks/WorkReport.svelte` | files created/changed/deleted |
| `gateway/GatewayPage.svelte` | AI Gateway dashboard |
| `telemetry/TelemetryPage.svelte` | spending analytics |
| `dspy/DSPyPage.svelte` | DSPy programs + lifecycle |

### `voly/telemetry.py` — task telemetry

`TaskEvent` — emitted for every pipeline/executor run.
`_COST_RATES` — sole source of truth for pricing rates.

Local destination: `.voly/events/<task_id>.json` with the complete TaskEvent.
Remote CF Pipelines, R2 and linked Cloud run history are fail-closed behind
`cloud_analytics.enabled` (default false) and receive only an explicit metadata
allowlist. Raw prompts/results/errors, repository paths, reports and artifacts
never cross that boundary. Remote run/evidence identifiers are one-way hashes.
The TaskEvent remote allowlist is `schema_version: 1`; the Evidence remote
allowlist is `schema_version: 2`. Both carry
`source_schema_version` for the local TaskEvent/EvidenceRecord lineage.

### `cf-workers/agent/` — CF Worker

Wrangler dev Worker for WranglerExecutor.

| Endpoint | Purpose |
|---|---|
| `GET /health` | availability + `pipeline_configured` / `a2a_callback_configured` |
| `POST /infer` | CF AI Gateway route schema → FILE blocks → LocalPatchApplier |
| `POST /agents/:name/run` | run task via pipeline runner (or `/infer` fallback) + A2A callback |
| `GET /tech-registry` | static tech version registry (mirrors `voly/catalog/tech_registry.py`), 1h cache |
| `/mcp` | MCP agent tools |

`infer.ts`: tries CF AI Gateway (`CF_ACCOUNT_ID`+`CF_AIG_TOKEN` → `dynamic/ai_route`),
falls back to `env.AI.run()`. Agent role (`developer`, `reviewer`, …) injected into system prompt.

**Recursion guard:** A2A subtasks via `pipeline_server` set `VOLY_A2A_NESTED=1` and
`a2a_parent_task_id` — pipeline skips `_stage_a2a_auto` to prevent nested re-dispatch.
See `docs/backend/a2a.md`.

**A2A callback:** after `/agents/:name/run` the worker calls `completeA2ATask()` → federation
`POST /tasks/:id/complete`. Worker-to-worker fetch to `*.workers.dev` is blocked (CF error 1042);
a **service binding** `A2A_FEDERATION` → `voly-a2a` is used (see `wrangler.jsonc`).

### `cf-workers/a2a/` — A2A federation hub

| Endpoint | Purpose |
|---|---|
| `POST /tasks` | create task (+ optional queue dispatch) |
| `GET /tasks/:id` | task status |
| `POST /tasks/:id/complete` | agent callback (**idempotent** — no-op if already completed) |
| queue consumer | `AGENT_WORKER` service binding → `voly-agent` `/agents/:name/run` (skips non-`submitted`) |

Secrets: `API_TOKEN`, `AGENT_WORKER_TOKEN` (must match agent `API_TOKEN`),
`AGENT_WORKER_URL` (fallback if binding missing). Agent secrets: `A2A_FEDERATION_TOKEN`
(must match federation `API_TOKEN`), `PIPELINE_RUNNER_URL` + `PIPELINE_RUNNER_TOKEN`.

---

## CI and release hygiene

GitHub Actions smoke gate:
- base install on Python 3.10 / 3.11 / 3.12
- import smoke without DSPy extra
- DSPy extra install smoke
- runtime smoke tests (`pytest tests/test_dspy_runtime_smoke.py`)

Do not commit:
```
.voly/events/
.voly/dspy/datasets/
.voly/dspy/programs/
.voly/reports/
.voly/evidence/
.voly/eval-runs/
.voly/wheels/
```

---

## Documentation map

```
CLAUDE.md                   ← agent instructions, skill references, doc navigation
docs/ARCHITECTURE.md        ← this file — high-level scheme
docs/backend/
  pipeline.md               ← Pipeline stages, AgentRouter, smart dispatch
  a2a.md                    ← A2A modules, auto-dispatch, federation, context handoff
  executors.md              ← Executors, billing fallback chain, WranglerExecutor
  ai-gateway.md             ← AIGateway middleware, CF route schema, providers
  dspy.md                   ← DSPy programs, TaskPlanner, adapter, datasets
  plan.md                   ← plan gates (shadow/active, acceptance, CLI)
  reuse.md                  ← voly reuse: GitHub search → pack → pick → apply
  research.md               ← offline research-first shadow decisions and benchmark
  strategic-memory.md       ← scoped compact handoffs, retrieval budgets, safe export
  continuous-learning.md    ← evidence-gated instincts and shadow selection
  lifecycle-hooks.md        ← constrained harness-neutral hooks and audit contract
  intelligence.md           ← Repository Intelligence: admission, license, architecture map
  capability.md             ← Capability Registry: evidence-based executor routing, matcher, scorer
  evaluated-capability-packs.md ← measured agent/skill pilots and retirement policy
  production-validation.md ← 20-task RAT probe and staged activation gate
  evidence.md               ← baseline, EvidenceRecord v2, root-cause attribution
  evaluation.md             ← versioned EvalPolicy and post-run evaluation
  config.md                 ← env vars, voly.yaml, VOLYConfig
  api.md                    ← FastAPI endpoints, SSE events, tech gate, CF Worker endpoints
  spend-protocol.md         ← spend protocol contract (/spend/record, /spend/check)
docs/frontend/
  overview.md               ← Svelte 5 stack, ui/ structure, dev/build
  components.md             ← component catalog, props, executor order
  api-client.md             ← SSE calls, event formats, billing_fallback in UI
docs/catalog-supervisor.md  ← Catalog, model metadata, Supervisor planning
docs/skills.md              ← SkillRegistry, sources, auto-generation
docs/project-scanner.md     ← ProjectScanner, ProjectProfile (core utility: voly scan, project skills, Pipeline.scan_project)
docs/proposals/
  business-ooda-loop.md     ← draft Layer C business-signal loop and phased delivery contracts
```
