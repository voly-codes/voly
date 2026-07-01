# CodeOps — Architecture

## Текущая архитектура

CodeOps — project-agnostic control plane для AI-агентов. Целевой проект передаётся
через `--cwd`; CodeOps отвечает за orchestration, routing, cost control, optimization и telemetry.

Есть **два независимых пути** выполнения задачи:

```text
Developer / UI / CI
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Entry points                                                    │
│ CLI (codeops run ...) · POST /api/run · codeops runner          │
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
│   ↓ SKILL       │       │     claude-code → wrangler → zen     │
│   ↓ HEADROOM    │       │   ↓ _dspy_store_example()            │
│   ↓ DSPY*       │       │   ↓ WorkReport (git diff)            │
│   ↓ MODEL_CALL  │       │   ↓ emit TaskEvent                   │
│   ↓ MEMORY_STORE│       └──────────────────────────────────────┘
│   ↓ TaskEvent   │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ AIGateway.chat()  (единственный выход к моделям) │
│ DLP → Cache → Rate limit → Spend limit → Provider │
│ Cloudflare AI Gateway · Direct adapters           │
└──────────────────────────────────────────────────┘
```

**Smart dispatch** (`codeops/web/routes/run.py`): когда `POST /api/run` получает
`executor=pipeline` и задача требует code gen (`requires_code_gen=True`) — автоматически
переключается на executor path с `executor=claude-code`.

---

## Design principles

1. **CodeOps stays project-agnostic.** Никакой product-specific логики в `codeops/`.
2. **AIGateway — единственный выход к моделям.** DSPy, InferenceManager, все рантаймы идут через него.
3. **Optimization is layered.** RTK, Headroom и DSPy независимы с явным fallback.
4. **Shadow before active.** Новое поведение оптимизатора — сначала shadow, потом active.
5. **Runtime state is not source.** `.codeops/events/`, datasets, compiled programs — генерируемые артефакты.
6. **Billing fallback chain.** При ошибке биллинга executor автоматически заменяется: `claude-code → wrangler → zen`.

---

## Pipeline path (text / inference)

`codeops/pipeline/core.py:Pipeline.run()` — для text-only задач.

### Стадии

| Stage | Метод | Что делает |
|---|---|---|
| `INIT` | — | setup |
| `AGUI_START` | `_stage_agui_start` | AG-UI SSE session |
| `A2A_DISCOVER` | `_stage_a2a` | A2A federation |
| `A2A_DELEGATE` | `_stage_a2a` | делегирование подзадач |
| `ROUTE` | `_stage_route` | AgentRouter → RouteDecision |
| `MEMORY_RETRIEVE` | `_stage_memory_retrieve` | MemoryStore.search |
| `RTK_FILTER` | `_stage_rtk` | RTK token stats |
| `SKILL_INJECT` | `_stage_skill_inject` | inject skill into system prompt |
| `HEADROOM_COMPRESS` | — | context compression |
| `DSPY_PROGRAM_CALL` | — | DSPyRunner.run() если enabled |
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

`codeops/runner/agent_runner.py:AgentRunner.run()` — для задач с записью файлов.

### Billing fallback chain

```
claude-code  →  wrangler  →  zen
(Anthropic)    (CF Workers)  (free)
```

`ExecutorResult.billing_error = True` → следующий executor в цепочке.
Только file-capable executors. Text-only (deepseek, workers-ai) — не в цепочке.

### DSPy в executor path

```
task
  ↓ _dspy_plan_task()  (если dspy.enabled)
    → TaskPlannerProgram.ChainOfThought → refined_task + success_criteria
  ↓ executor.run(refined_task, cwd)
  ↓ _dspy_store_example()  → datasets_dir/task_planner/*.jsonl
```

### Chain logs

```
codeops.chain logger:
[CHAIN:START]            — первая попытка
[CHAIN:DSPY_PLAN]        — DSPy отрефайнил задачу
[CHAIN:RESULT]           — результат + billing_error
[CHAIN:BILLING_FALLBACK] — переключение executor
[CHAIN:FALLBACK_RESULT]  — результат fallback
[CHAIN:DSPY_STORE]       — сохранение примера
```

### Executor table

| Executor | File writes | Billing | Chain position |
|---|---|---|---|
| `claude-code` | да — Claude CLI | Anthropic | 1st |
| `wrangler` | да — LocalPatchApplier | CF Workers AI | 2nd |
| `zen` | да — opencode CLI | free | 3rd (last resort) |
| `cursor` | да — Cursor Agent | Cursor | standalone |
| `opencode` | да — OpenCode CLI | opencode.ai | standalone |
| `deepseek` | нет — text only | DeepSeek API | NOT in chain |
| `mimo` | нет — text only | MiMo API | NOT in chain |

---

## Key modules

### `codeops/pipeline/` — central orchestrator (text path)

`Pipeline.run()` → stage methods + mixins. Не содержит product logic.

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

### `codeops/runner/agent_runner.py` — executor path

`AgentRunner.run()` orchestrates: DSPy plan → executor → billing fallback → git diff → telemetry.

```python
BILLING_FALLBACK_CHAIN = ["claude-code", "wrangler", "zen"]
EXECUTOR_NAMES = frozenset({"cursor", "claude-code", "mimo", "opencode", "deepseek", "zen", "wrangler"})
```

### `codeops/executor/` — file-capable runtimes

| Executor | File | Purpose |
|---|---|---|
| `base.py` | — | `Executor`, `ExecutorResult`, `billing_error`, `_is_billing_error()` |
| `claude_code.py` | ClaudeCodeExecutor | запускает `claude` CLI |
| `wrangler.py` | WranglerExecutor | POST /infer → LocalPatchApplier |
| `patch.py` | LocalPatchApplier | парсит FILE blocks + unified diffs → пишет на диск |
| `zen.py` | ZenExecutor | opencode CLI, free tier |
| `cursor.py` | CursorExecutor | Cursor Agent |
| `opencode.py` | OpenCodeExecutor | OpenCode CLI/API |
| `deepseek.py` | DeepSeekExecutor | text only |

### `codeops/inference/runtime.py` — runtime selection

| Runtime | Role |
|---|---|
| `ClassicRuntime` | прямой вызов через `AIGateway.chat()` |
| `DSPyRuntime` | optional DSPy program → `DSPyRunner` → `AIGateway.chat()` |
| `InferenceManager` | выбирает runtime, fallback на classic |

### `codeops/dspy/` — DSPy optimizer layer

Опциональный слой. Установка: `pip install -e ".[dspy]"`.
Два места интеграции: Pipeline (DSPyRuntime) и AgentRunner (TaskPlannerProgram).

| File | Purpose |
|---|---|
| `adapter.py` | `CodeOpsDSPyLM` — DSPy LM через `AIGateway.chat()` |
| `runner.py` | `DSPyRunner` — интеграция с InferenceManager |
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

### `codeops/ai_gateway/` — model gateway

`AIGateway.chat()` — единственный выход к провайдерам.

Middleware stack: DLP → Cache → Rate limit → Spend limit → Provider call.

| Provider group | Routing |
|---|---|
| Anthropic / OpenAI / Google / DeepSeek | Cloudflare AI Gateway |
| MiMo | Direct (CUSTOM) |
| OpenCode Zen / GO | Direct (CUSTOM) |
| Workers AI | CF AI Gateway `/compat` или `env.AI.run()` |
| Executors | bypass gateway — запускают субпроцессы |

### `codeops/web/` — backend API

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

### `codeops/telemetry.py` — task telemetry

`TaskEvent` — эмитируется для каждого pipeline/executor запуска.
`_COST_RATES` — единственный источник правды для pricing rates.

Destinations: `.codeops/events/<task_id>.json` + optional CF Pipelines / R2.

### `cf-workers/agent/` — CF Worker

Wrangler dev Worker для WranglerExecutor.

| Endpoint | Purpose |
|---|---|
| `GET /health` | availability + `pipeline_configured` / `a2a_callback_configured` |
| `POST /infer` | CF AI Gateway route schema → FILE blocks → LocalPatchApplier |
| `POST /agents/:name/run` | run task via pipeline runner (or `/infer` fallback) + A2A callback |
| `/mcp` | MCP agent tools |

`infer.ts`: пробует CF AI Gateway (`CF_ACCOUNT_ID`+`CF_AIG_TOKEN` → `dynamic/ai_route`),
fallback на `env.AI.run()`.

**A2A callback:** после `/agents/:name/run` worker вызывает `completeA2ATask()` → federation
`POST /tasks/:id/complete`. Worker-to-worker fetch на `*.workers.dev` блокируется (CF error 1042);
используется **service binding** `A2A_FEDERATION` → `codeops-a2a` (см. `wrangler.jsonc`).

### `cf-workers/a2a/` — A2A federation hub

| Endpoint | Purpose |
|---|---|
| `POST /tasks` | create task (+ optional queue dispatch) |
| `GET /tasks/:id` | task status |
| `POST /tasks/:id/complete` | agent callback |
| queue consumer | `AGENT_WORKER` service binding → `codeops-agent` `/agents/:name/run` |

Secrets: `API_TOKEN`, `AGENT_WORKER_TOKEN` (must match agent `API_TOKEN`),
`AGENT_WORKER_URL` (fallback if binding missing). Agent secrets: `A2A_FEDERATION_TOKEN`
(must match federation `API_TOKEN`), `PIPELINE_RUNNER_URL` + `PIPELINE_RUNNER_TOKEN`.

---

## CI and release hygiene

GitHub Actions smoke gate:
- base install на Python 3.10 / 3.11 / 3.12
- import smoke без DSPy extra
- DSPy extra install smoke
- runtime smoke tests (`pytest tests/test_dspy_runtime_smoke.py`)

Не коммитить:
```
.codeops/events/
.codeops/dspy/datasets/
.codeops/dspy/programs/
.codeops/reports/
```

---

## Documentation map

```
CLAUDE.md                   ← agent instructions, skill references, doc navigation
docs/ARCHITECTURE.md        ← этот файл — высокоуровневая схема
docs/backend/
  pipeline.md               ← Pipeline stages, AgentRouter, smart dispatch
  executors.md              ← Executors, billing fallback chain, WranglerExecutor
  ai-gateway.md             ← AIGateway middleware, CF route schema, providers
  dspy.md                   ← DSPy programs, TaskPlanner, adapter, datasets
  config.md                 ← env vars, codeops.yaml, CodeOpsConfig
  api.md                    ← FastAPI endpoints, SSE events
docs/frontend/
  overview.md               ← Svelte 5 stack, ui/ structure, dev/build
  components.md             ← component catalog, props, executor order
  api-client.md             ← SSE calls, event formats, billing_fallback in UI
docs/catalog-supervisor.md  ← Catalog, model metadata, Supervisor planning
docs/skills.md              ← SkillRegistry, sources, auto-generation
docs/workflows.md           ← WorkflowEngine, human approval gates [prototype]
docs/project-scanner.md     ← ProjectScanner, ProjectProfile [prototype]
```
