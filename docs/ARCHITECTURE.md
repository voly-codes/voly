# CodeOps — Architecture

## Текущая архитектура

CodeOps — project-agnostic control plane для AI-агентов. Он не содержит логики конкретного продукта: целевой проект передаётся через `--cwd`, а CodeOps отвечает за orchestration, routing, cost control, optimization и telemetry.

```text
Developer / UI / CI / Scheduler
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ CLI (codeops/cli/main.py)                                   │
│ init · run · compare · scan · match · status · workflow     │
│ registry · model · ai-gateway · memory · a2a · rtk          │
│ headroom · mcp · config · catalog · spend · telemetry · dspy│
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ AG-UI Gateway (codeops/agui/)                               │
│ SSE streaming · run_started/finished · tool events          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Pipeline (codeops/pipeline/core.py)                         │
│                                                             │
│ INIT → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE →  │
│ MEMORY_RETRIEVE → RTK_FILTER → SKILL_INJECT →              │
│ HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL →       │
│ MEMORY_STORE → AGUI_DONE → DONE / ERROR → emit TaskEvent   │
│                                                             │
│ Returns: PipelineResult { response, route, analysis, event }│
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Agent Router + Cost Policy                                  │
│ analyze_task → TaskAnalysis                                 │
│ route → RouteDecision { agent, model, provider, tools }     │
│ budget_status / cheaper model routing / per-task cost cap   │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Context Optimization                                        │
│ MemoryStore.search → RTK_FILTER → Headroom compression      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Inference Runtime (codeops/inference/runtime.py)            │
│                                                             │
│ ClassicRuntime ─────────────┐                               │
│ DSPyRuntime (optional) ─────┼──→ AIGateway.chat()           │
│                             │                               │
│ DSPy mode: off | shadow | active                            │
│ shadow: logs DSPy result but returns classic response        │
│ active: DSPy response may replace classic for opted agents   │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ AI Gateway (codeops/ai_gateway/)                            │
│ DLP scan → Cache check → Rate limit → Spend limit → Fallback│
│ Cloudflare AI Gateway providers + direct provider adapters  │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Providers                                                   │
│ Anthropic · OpenAI · Google · DeepSeek · MiMo · OpenCode Zen│
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Telemetry                                                   │
│ TaskEvent → .codeops/events/ + optional CF Pipelines / R2   │
└─────────────────────────────────────────────────────────────┘
```

---

## Design principles

1. **CodeOps stays project-agnostic.** Product-specific missions, paths and prompts do not live in the core package.
2. **AIGateway remains the single model exit.** DSPy and future runtimes must go through the gateway to keep DLP/cache/spend/fallback.
3. **Optimization is layered, not hardcoded.** RTK, Headroom and DSPy are independent layers with clear fallback.
4. **Shadow before active.** New optimizer behavior should be observed in telemetry before it affects user-visible responses.
5. **Runtime state is not source code.** `.codeops/events/`, datasets and compiled DSPy programs are generated artifacts.

---

## Key modules

### `codeops/pipeline/` — central orchestrator

`Pipeline.run(task)` wires together routing, context, inference and telemetry. It emits `PipelineStage` hooks so UI/AG-UI/debug tools can observe execution. Hook errors are logged at DEBUG level and never propagate.

`run()` (~140 lines in `core.py`) delegates to stage methods and mixins:

| Method | Responsibility |
|---|---|
| `_stage_agui_start` | initialise AG-UI session |
| `_stage_a2a` | A2A delegation; returns `PipelineResult` if delegated |
| `_stage_route` | routing + cost policy; returns `(route, analysis, task_type)` |
| `_stage_spend_check` | pre-call spend limit; returns `PipelineResult` if blocked |
| `_stage_memory_retrieve` | memory search → context messages |
| `_stage_rtk` | RTK stats |
| `_stage_skill_inject` | match skills for task/agent, inject into system prompt |
| `_check_gateway_errors` | DLP / rate / spend errors after model call |
| `_build_model_response` | `ModelResponse` from gateway dict |
| `_stage_memory_store` | persist task result to memory |
| `_stage_agui_done` | stream response to AG-UI |
| `_extract_dspy_fields` | unpack DSPy metadata from `DSPyResult` |
| `_emit_task_event` | build and emit `TaskEvent` to telemetry |

Important `PipelineStage` values:

| Stage | Purpose |
|---|---|
| `ROUTE` | selected agent/model/provider/tools |
| `MEMORY_RETRIEVE` | memory hits injected into context |
| `RTK_FILTER` | command output/context reduction |
| `SKILL_INJECT` | skill matching and system prompt injection |
| `HEADROOM_COMPRESS` | context compression boundary |
| `DSPY_PROGRAM_CALL` | DSPy optimizer boundary when enabled |
| `MODEL_CALL` | user-visible LLM response produced |
| `DONE` / `ERROR` | final status |

### `codeops/inference/runtime.py` — runtime selection

Inference is separated from Pipeline so CodeOps can support multiple LLM execution modes:

| Runtime | Role |
|---|---|
| `ClassicRuntime` | direct prompt/messages call through `AIGateway.chat()` |
| `DSPyRuntime` | optional DSPy program call through `DSPyRunner` |
| `InferenceManager` | chooses runtime and falls back to classic when needed |

This keeps Pipeline stable while allowing future runtimes such as Responses API, LangGraph or Semantic Kernel.

### `codeops/dspy/` — DSPy optimizer layer

DSPy is optional. It is installed with:

```bash
pip install -e ".[dspy]"
```

Core files:

| File | Purpose |
|---|---|
| `adapter.py` | `CodeOpsDSPyLM`, DSPy LM adapter over `AIGateway.chat()` |
| `runner.py` | `DSPyRunner`, integration point used by `InferenceManager` |
| `signatures.py` | structured DSPy signatures |
| `modules.py` | DSPy modules with forward/optimize methods |
| `programs/` | program registry and per-program factories |
| `compiler.py` | dataset loading and program compilation |
| `store.py` | versioned compiled program storage |
| `versioning.py` | tags such as `candidate` / `production` |
| `metrics.py` | optimizer metrics |

DSPy config:

```yaml
dspy:
  enabled: false
  mode: shadow       # off | shadow | active
  optimizer: bootstrap_fewshot
  min_examples: 20
  compile_budget: small
  routing_mode: shadow
  agents:
    - reviewer
    - documenter
    - architect
  active_tag: production
  shadow_tag: candidate
  program_overrides: {}
```

Rollout model:

```text
off → shadow → candidate program → eval → promote production → active
```

### `codeops/ai_gateway/` — model gateway

`AIGateway.chat()` is the single gateway to external model providers. It applies middleware on every call:

1. DLP scan
2. Cache check
3. Rate limit
4. Spend limit
5. Provider call with fallback
6. Metrics/cost recording (`_calculate_cost` delegates to `telemetry._estimate_cost` — single source of truth for pricing rates)

Supported provider groups:

| Provider group | Path |
|---|---|
| Anthropic / OpenAI / Google / DeepSeek | Cloudflare AI Gateway |
| MiMo | Direct OpenAI/Anthropic-compatible API |
| OpenCode Zen / GO | Direct OpenCode endpoints |
| Cursor | Executor layer, not gateway text call |

### `codeops/executor/` — file-capable agents

Executors are used when a task must actually inspect or modify files in `--cwd`.

| Executor | Purpose |
|---|---|
| `cursor` | multi-file implementation via Cursor Agent |
| `opencode` | OpenCode CLI/API execution |
| `claude-code` | Claude CLI execution |
| `deepseek` | low-cost text/code generation |
| `zen` | readonly analysis/review/planning |
| `mimo` | batch/text tasks |

### `codeops/catalog/` — model catalog and routing support

Catalog stores OpenCode Zen model metadata and helps choose executor/model combinations for tasks. It is now a generic model planning component, not tied to any product-specific combat missions.

| File | Purpose |
|---|---|
| `types.py` | catalog and plan dataclasses |
| `zen_sync.py` | sync model metadata from OpenCode Zen |
| `store.py` | local cache under `.codeops/catalog/` |
| `routing.py` | task matching / executor-model selection |
| `supervisor.py` | supervised planning helpers |
| `client.py` | optional Cloudflare Worker client |
| `multi_agent.py` | parallel/sequential task orchestration (in `codeops/executor/`) |

### `codeops/telemetry.py` — task telemetry

`TaskEvent` is emitted for each pipeline/executor run.

Important fields:

```python
@dataclass
class TaskEvent:
    task_id: str
    agent: str
    status: str
    tokens: TokenMetrics
    gateway: GatewayMetrics
    skill_ids: list[str]
    routing_score: float
    cost_usd: float
    duration_ms: float
    model: str
    provider: str
    executor: str
    task_type: str | None
    dspy_enabled: bool
    dspy_mode: str | None
    dspy_program_id: str | None
    dspy_program_version: int | None
    dspy_program_tag: str | None
    dspy_optimizer: str | None
    dspy_dataset: str | None
    dspy_compile_id: str | None
    dspy_score: float | None
    dspy_shadow_delta: float | None
```

Local fallback path:

```text
.codeops/events/<task_id>.json
```

Optional remote destinations:

- CF Pipelines ingest endpoint;
- R2 telemetry upload;
- spend tracking Durable Object/client.

### `ui/` — web dashboard

CodeOps ships a Svelte 5 web frontend under `ui/src/`:

| Component | Purpose |
|---|---|
| `App.svelte` | main layout: nav, page routing, drawer triggers |
| `TaskSidebar.svelte` | task list with search, status dots, cost display |
| `PipelineInspector.svelte` | task detail: pipeline stages, token flow, work report, gateway/DSPy/metadata |
| `RunPanel.svelte` | task runner: parameters grid, streaming result, pinned input area |
| `CostPanel.svelte` | summary cards, by-agent/by-model breakdown, selected task detail |
| `DSPyPage.svelte` | DSPy status and management page |
| `CFPage.svelte` / `MarketplacePage.svelte` | Cloudflare and skill marketplace drawers |
| `Drawer.svelte` | generic slide-out panel for Run/CF/Skills drawers |
| `shared/` | reusable primitives: StatusDot, etc. |
| `tasks/lib/utils.js` | shared formatters: `fmtTokens`, `fmtDur`, `fmtRel`, `calcPct`, `statusRu` |

The UI is served by `codeops serve` (FastAPI + static files under `codeops/web/`).

### `codeops/web/` — backend API

| File | Purpose |
|---|---|
| `server.py` | FastAPI app with CORS, health/liveness endpoints |
| `routes/run.py` | POST `/api/run` — SSE streaming task execution |
| `routes/` | additional routes for tasks, agents, models, summary, status |

---

## CI and release hygiene

The repository includes a smoke-test GitHub Actions workflow:

- base install on Python 3.10 / 3.11 / 3.12;
- import smoke test without DSPy extra;
- DSPy extra install smoke test;
- runtime smoke tests.

Full historical tests can be re-enabled as a stricter job once older integration tests are stabilized.

Generated runtime state should stay out of git:

```text
.codeops/events/
.codeops/dspy/datasets/
.codeops/dspy/programs/
```

---

## Documentation map

| File | Purpose |
|---|---|
| `README.md` | quick start and product positioning |
| `CLAUDE.md` | agent instructions for this repository |
| `docs/executors.md` | executor runtime guide |
| `docs/catalog-supervisor.md` | catalog/model planning guide |
| `docs/dspy.md` | DSPy integration guide |
| `docs/ai-gateway.md` | AI Gateway: DLP, cache, rate/spend limits, fallback |
| `docs/workflows.md` | workflow engine and human approval gates |
| `docs/skills.md` | skill registry and marketplace |
| `docs/project-scanner.md` | project scanner and profile detection |
| `docs/ARCHITECTURE.md` | this architecture document |
