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
│ Pipeline (codeops/pipeline.py)                              │
│                                                             │
│ INIT → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE →  │
│ MEMORY_RETRIEVE → RTK_FILTER → HEADROOM_COMPRESS →         │
│ DSPY_PROGRAM_CALL → MODEL_CALL → MEMORY_STORE →            │
│ AGUI_DONE → DONE → emit TaskEvent                           │
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

### `codeops/pipeline.py` — central orchestrator

`Pipeline.run(task)` wires together routing, context, inference and telemetry. It emits `PipelineStage` hooks so UI/AG-UI/debug tools can observe execution.

```text
task
  → AgentRouter.analyze_task()
  → AgentRouter.route()
  → CostPolicy
  → MemoryStore.search()
  → RTK / Headroom
  → InferenceManager.run()
  → ModelResponse
  → MemoryStore.add()
  → TaskEvent
  → PipelineResult
```

Important stages:

| Stage | Purpose |
|---|---|
| `ROUTE` | selected agent/model/provider/tools |
| `MEMORY_RETRIEVE` | memory hits injected into context |
| `RTK_FILTER` | command output/context reduction |
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
6. Metrics/cost recording

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
| `docs/ARCHITECTURE.md` | this architecture document |
