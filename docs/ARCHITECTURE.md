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
│   ↓ SKILL_SUGGEST*      │     claude-code → wrangler → zen     │
│   ↓ SKILL       │       │   ↓ _dspy_store_example()            │
│   ↓ HEADROOM    │       │   ↓ _dspy_store_example()            │
│   ↓ DSPY*       │       │   ↓ WorkReport (git diff)            │
│   ↓ MODEL_CALL  │       │   ↓ emit TaskEvent                   │
│   ↓ MEMORY_STORE│       └──────────────────────────────────────┘
│   ↓ TaskEvent   │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ AIGateway.chat()  (sole exit to models)          │
│ DLP → Cache → Rate limit → Spend limit → Provider │
│ Cloudflare AI Gateway · Direct adapters           │
└──────────────────────────────────────────────────┘
```

**Smart dispatch** (`voly/web/routes/run.py`): when `POST /api/run` receives
`executor=pipeline` and the task requires code generation (`requires_code_gen=True`) — it
automatically switches to the executor path with `executor=claude-code`.

---

## Design principles

1. **VOLY stays project-agnostic.** No product-specific logic in `voly/`.
2. **AIGateway is the sole exit to models.** DSPy, InferenceManager, and all runtimes go through it.
3. **Optimization is layered.** RTK, Headroom, and DSPy are independent with explicit fallback.
4. **Shadow before active.** New optimizer behavior starts in shadow, then becomes active.
5. **Runtime state is not source.** `.voly/events/`, datasets, compiled programs are generated artifacts.
6. **Billing fallback chain.** On a billing error the executor is automatically replaced: `claude-code → wrangler → opencode → zen`.

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
| `TaskEvent` (task telemetry) | `schema_version: 1` | `voly/telemetry.py`, `docs/backend/api.md` |
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
| `AGUI_START` | `_stage_agui_start` | AG-UI SSE session |
| `A2A_DISCOVER` | `_stage_a2a` / `_stage_a2a_auto` | A2A federation + auto-decompose |
| `A2A_DELEGATE` | `_stage_a2a_auto` → `_run_multiagent_local` | lead assigns tier+skills; hybrid: implement roles → AgentRunner, architect/reviewer → AIGateway (`a2a.execution_mode=local`) |
| `ROUTE` | `_stage_route` | AgentRouter → RouteDecision |
| `MEMORY_RETRIEVE` | `_stage_memory_retrieve` | MemoryStore.search |
| `RTK_FILTER` | `_stage_rtk` | RTK token stats |
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

### Billing fallback chain

```
claude-code  →  wrangler  →  zen
(Anthropic)    (CF Workers)  (free)
```

`ExecutorResult.billing_error = True` → next executor in the chain.
Only file-capable executors. Text-only (deepseek, workers-ai) — not in the chain.

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
| `wrangler` | yes — LocalPatchApplier | CF Workers AI | 2nd |
| `zen` | yes — opencode CLI | free | 3rd (last resort) |
| `cursor` | yes — Cursor Agent | Cursor | standalone |
| `opencode` | yes — OpenCode CLI | opencode.ai | standalone |
| `deepseek` | no — text only | DeepSeek API | NOT in chain |
| `mimo` | no — text only | MiMo API | NOT in chain |

---

## Plan gates (Rung B)

Enforced multi-step plans with verification gates. Design:
[`docs/proposals/plan-gate-verification.md`](proposals/plan-gate-verification.md).

| PR | Status | Module |
|---|---|---|
| PR1 | **landed** — types, store, FSM engine | `voly/plan/` |
| PR2 | **landed** — acceptance verifiers | `voly/plan/verify.py` |
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

### `voly/pipeline/` — central orchestrator (text path)

`Pipeline.run()` → stage methods + mixins. Does not contain product logic.

| Method | Responsibility |
|---|---|
| `_stage_agui_start` | AG-UI session init |
| `_stage_a2a` | A2A delegation |
| `_stage_route` | routing + cost policy |
| `_stage_spend_check` | pre-call spend limit |
| `_stage_memory_retrieve` | memory search |
| `_stage_rtk` | RTK stats |
| `_stage_skill_inject` | match+inject skills |
| `_stage_memory_store` | persist result |
| `_stage_agui_done` | stream to AG-UI |
| `_emit_task_event` | telemetry |

### `voly/runner/agent_runner.py` — executor path

`AgentRunner.run()` orchestrates: DSPy plan → executor → billing fallback → git diff → telemetry.

```python
BILLING_FALLBACK_CHAIN = ["claude-code", "wrangler", "zen"]
EXECUTOR_NAMES = frozenset({"cursor", "claude-code", "mimo", "opencode", "deepseek", "zen", "wrangler"})
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
| `deepseek.py` | DeepSeekExecutor | text only |

### `voly/inference/runtime.py` — runtime selection

| Runtime | Role |
|---|---|
| `ClassicRuntime` | direct call via `AIGateway.chat()` |
| `DSPyRuntime` | optional DSPy program → `DSPyRunner` → `AIGateway.chat()` |
| `InferenceManager` | selects runtime, falls back to classic |

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
| `routes/run.py` | POST `/api/run` — SSE + smart dispatch + context gather |
| `routes/tasks.py` | GET `/api/tasks`, SSE stream |
| `routes/registry.py` | agents, models, skills |
| `routes/gateway.py` | gateway status |
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

Destinations: `.voly/events/<task_id>.json` + optional CF Pipelines / R2.

### `cf-workers/agent/` — CF Worker

Wrangler dev Worker for WranglerExecutor.

| Endpoint | Purpose |
|---|---|
| `GET /health` | availability + `pipeline_configured` / `a2a_callback_configured` |
| `POST /infer` | CF AI Gateway route schema → FILE blocks → LocalPatchApplier |
| `POST /agents/:name/run` | run task via pipeline runner (or `/infer` fallback) + A2A callback |
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
```

---

## Documentation map

```
CLAUDE.md                   ← agent instructions, skill references, doc navigation
docs/ARCHITECTURE.md        ← this file — high-level scheme
docs/backend/
  pipeline.md               ← Pipeline stages, AgentRouter, smart dispatch
  executors.md              ← Executors, billing fallback chain, WranglerExecutor
  ai-gateway.md             ← AIGateway middleware, CF route schema, providers
  dspy.md                   ← DSPy programs, TaskPlanner, adapter, datasets
  plan.md                   ← plan gates (shadow/active, acceptance, CLI)
  config.md                 ← env vars, voly.yaml, VOLYConfig
  api.md                    ← FastAPI endpoints, SSE events
docs/frontend/
  overview.md               ← Svelte 5 stack, ui/ structure, dev/build
  components.md             ← component catalog, props, executor order
  api-client.md             ← SSE calls, event formats, billing_fallback in UI
docs/catalog-supervisor.md  ← Catalog, model metadata, Supervisor planning
docs/skills.md              ← SkillRegistry, sources, auto-generation
docs/project-scanner.md     ← ProjectScanner, ProjectProfile (core utility: voly scan, project skills, Pipeline.scan_project)
```
