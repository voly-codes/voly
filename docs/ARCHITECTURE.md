# VOLY — Architecture

## Текущая архитектура

VOLY — project-agnostic control plane для AI-агентов. Целевой проект передаётся
через `--cwd`; VOLY отвечает за orchestration, routing, cost control, optimization и telemetry.

Есть **два независимых пути** выполнения задачи:

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

**Smart dispatch** (`voly/web/routes/run.py`): когда `POST /api/run` получает
`executor=pipeline` и задача требует code gen (`requires_code_gen=True`) — автоматически
переключается на executor path с `executor=claude-code`.

---

## Design principles

1. **VOLY stays project-agnostic.** Никакой product-specific логики в `voly/`.
2. **AIGateway — единственный выход к моделям.** DSPy, InferenceManager, все рантаймы идут через него.
3. **Optimization is layered.** RTK, Headroom и DSPy независимы с явным fallback.
4. **Shadow before active.** Новое поведение оптимизатора — сначала shadow, потом active.
5. **Runtime state is not source.** `.voly/events/`, datasets, compiled programs — генерируемые артефакты.
6. **Billing fallback chain.** При ошибке биллинга executor автоматически заменяется: `claude-code → wrangler → opencode → zen`.

---

## Слои A/B — make vs delegate

VOLY состоит из двух слоёв с разной инженерной стратегией:

| Слой | Что это | Стратегия |
|---|---|---|
| **A — model gateway** | Маршрутизация/fallback между провайдерами моделей (anthropic, openai, deepseek, workers-ai, …) | **Delegate.** Зрелая ниша (OmniRoute, LiteLLM, OpenRouter) — не догоняем по ширине провайдеров. Стабилизируется по минимуму; провайдерная маршрутизация делегируется внешнему gateway (см. «Upstream delegation» ниже), прямые адаптеры — fallback. |
| **B — оркестрация file-capable CLI-агентов** | Executor chain (агенты пишут файлы), billing fallback между CLI, мульти-агентная декомпозиция (тир модели на роль), телеметрия стоимости задач | **Make.** Уникальность VOLY — сюда весь фокус разработки: устойчивость цепочки, честный FinOps-учёт, project-agnostic executor path. |

**Upstream delegation (слой A first-class):** `ai_gateway.upstream: "omniroute"` в
`voly.yaml` направляет все не-CF вызовы `AIGateway.chat()` через один внешний
gateway (модель passthrough или `upstream_model: "auto"`); при его недоступности —
автоматический fallback на прямой адаптер запрошенного провайдера
(`upstream_fallback_direct`). Кэш, DLP, spend limits и телеметрия не меняются —
они живут вокруг вызова. Детали: `docs/backend/ai-gateway.md`.

### Публичные версионируемые контракты

Ядро общается с любыми внешними сервисами (self-hosted или managed) через
открытые версионируемые интерфейсы — они замораживаются контрактными тестами
(`tests/test_protocol_contracts.py`):

| Контракт | Версия | Где описан |
|---|---|---|
| `TaskEvent` (телеметрия задач) | `schema_version: 1` | `voly/telemetry.py`, `docs/backend/api.md` |
| Spend-протокол (`/spend/record`, `/spend/check`, …) | v1 | `docs/backend/spend-protocol.md` |
| A2A federation | — | `cf-workers/a2a/`, `docs/backend/api.md` |

Изменение контракта = бамп версии + обновление docs + снимка в контрактном тесте.

---

## Pipeline path (text / inference)

`voly/pipeline/core.py:Pipeline.run()` — для text-only задач.

### Стадии

| Stage | Метод | Что делает |
|---|---|---|
| `INIT` | — | setup |
| `AGUI_START` | `_stage_agui_start` | AG-UI SSE session |
| `A2A_DISCOVER` | `_stage_a2a` / `_stage_a2a_auto` | A2A federation + auto-decompose |
| `A2A_DELEGATE` | `_stage_a2a_auto` → `_run_multiagent_local` | lead назначает тир+скилы, суб-агенты через AIGateway (`a2a.execution_mode=local`) |
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

`voly/runner/agent_runner.py:AgentRunner.run()` — для задач с записью файлов.

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
voly.chain logger:
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

### `voly/pipeline/` — central orchestrator (text path)

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
| `claude_code.py` | ClaudeCodeExecutor | запускает `claude` CLI |
| `wrangler.py` | WranglerExecutor | POST /infer → LocalPatchApplier |
| `patch.py` | LocalPatchApplier | парсит FILE blocks + unified diffs → пишет на диск |
| `zen.py` | ZenExecutor | opencode CLI, free tier |
| `cursor.py` | CursorExecutor | Cursor Agent |
| `opencode.py` | OpenCodeExecutor | OpenCode CLI/API |
| `deepseek.py` | DeepSeekExecutor | text only |

### `voly/inference/runtime.py` — runtime selection

| Runtime | Role |
|---|---|
| `ClassicRuntime` | прямой вызов через `AIGateway.chat()` |
| `DSPyRuntime` | optional DSPy program → `DSPyRunner` → `AIGateway.chat()` |
| `InferenceManager` | выбирает runtime, fallback на classic |

### `voly/dspy/` — DSPy optimizer layer

Опциональный слой. Установка: `pip install -e ".[dspy]"`.
Два места интеграции: Pipeline (DSPyRuntime) и AgentRunner (TaskPlannerProgram).

| File | Purpose |
|---|---|
| `adapter.py` | `VOLYDSPyLM` — DSPy LM через `AIGateway.chat()` |
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

### `voly/ai_gateway/` — model gateway

`AIGateway.chat()` — единственный выход к провайдерам.

Middleware stack: DLP → Cache → Rate limit → Spend limit → Provider call.

| Provider group | Routing |
|---|---|
| Anthropic / OpenAI / Google / DeepSeek | Cloudflare AI Gateway |
| MiMo | Direct (CUSTOM) |
| OpenCode Zen / GO | Direct (CUSTOM) |
| OmniRoute | Direct (CUSTOM, opt-in) — self-hosted OpenAI-compat gateway |
| Workers AI | CF AI Gateway `/compat` или `env.AI.run()` |
| Executors | bypass gateway — запускают субпроцессы |

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

`TaskEvent` — эмитируется для каждого pipeline/executor запуска.
`_COST_RATES` — единственный источник правды для pricing rates.

Destinations: `.voly/events/<task_id>.json` + optional CF Pipelines / R2.

### `cf-workers/agent/` — CF Worker

Wrangler dev Worker для WranglerExecutor.

| Endpoint | Purpose |
|---|---|
| `GET /health` | availability + `pipeline_configured` / `a2a_callback_configured` |
| `POST /infer` | CF AI Gateway route schema → FILE blocks → LocalPatchApplier |
| `POST /agents/:name/run` | run task via pipeline runner (or `/infer` fallback) + A2A callback |
| `/mcp` | MCP agent tools |

`infer.ts`: пробует CF AI Gateway (`CF_ACCOUNT_ID`+`CF_AIG_TOKEN` → `dynamic/ai_route`),
fallback на `env.AI.run()`. Agent role (`developer`, `reviewer`, …) injected into system prompt.

**Recursion guard:** A2A subtasks via `pipeline_server` set `VOLY_A2A_NESTED=1` and
`a2a_parent_task_id` — pipeline skips `_stage_a2a_auto` to prevent nested re-dispatch.
See `docs/backend/a2a.md`.

**A2A callback:** после `/agents/:name/run` worker вызывает `completeA2ATask()` → federation
`POST /tasks/:id/complete`. Worker-to-worker fetch на `*.workers.dev` блокируется (CF error 1042);
используется **service binding** `A2A_FEDERATION` → `voly-a2a` (см. `wrangler.jsonc`).

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
- base install на Python 3.10 / 3.11 / 3.12
- import smoke без DSPy extra
- DSPy extra install smoke
- runtime smoke tests (`pytest tests/test_dspy_runtime_smoke.py`)

Не коммитить:
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
docs/ARCHITECTURE.md        ← этот файл — высокоуровневая схема
docs/backend/
  pipeline.md               ← Pipeline stages, AgentRouter, smart dispatch
  executors.md              ← Executors, billing fallback chain, WranglerExecutor
  ai-gateway.md             ← AIGateway middleware, CF route schema, providers
  dspy.md                   ← DSPy programs, TaskPlanner, adapter, datasets
  config.md                 ← env vars, voly.yaml, VOLYConfig
  api.md                    ← FastAPI endpoints, SSE events
docs/frontend/
  overview.md               ← Svelte 5 stack, ui/ structure, dev/build
  components.md             ← component catalog, props, executor order
  api-client.md             ← SSE calls, event formats, billing_fallback in UI
docs/catalog-supervisor.md  ← Catalog, model metadata, Supervisor planning
docs/skills.md              ← SkillRegistry, sources, auto-generation
docs/project-scanner.md     ← ProjectScanner, ProjectProfile (утилита ядра: voly scan, project-скилы, Pipeline.scan_project)
```
