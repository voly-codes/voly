# Pipeline — Backend Reference

`voly/pipeline/core.py:Pipeline` — оркестратор для **text-only** задач (inference через AIGateway).
Для задач с записью файлов — используй `AgentRunner` + executor.

---

## Когда Pipeline, когда AgentRunner

| Сценарий | Что использовать |
|---|---|
| Вопрос / суммаризация / review без правок | Pipeline → AIGateway.chat() |
| Написать/изменить файлы в проекте | AgentRunner → executor (claude-code / wrangler / zen) |
| Web UI задача с кодом | smart dispatch: pipeline → claude-code автоматически |
| CLI `voly run --executor cursor` | AgentRunner напрямую |

---

## Стадии Pipeline

```
INIT
  ↓ AGUI_START       — уведомить AG-UI о начале задачи (SSE events)
  ↓ A2A_DISCOVER     — найти внешних агентов (A2A federation)
  ↓ A2A_DELEGATE     — делегировать подзадачи если нужно
  ↓ ROUTE            — AgentRouter.analyze_task() + route()
  ↓ MEMORY_RETRIEVE  — MemoryStore.search() — релевантный контекст
  ↓ RTK_FILTER       — RTK токен-фильтрация контекста
  ↓ SKILL_INJECT     — вставить system prompt из Catalog Skills
  ↓ HEADROOM_COMPRESS — Headroom: сжать messages если > token limit
  ↓ DSPY_PROGRAM_CALL — опционально: DSPyRunner.run() (shadow или active)
  ↓ MODEL_CALL        — AIGateway.chat() → response
  ↓ MEMORY_STORE      — сохранить (task, response) в memory
  ↓ AGUI_DONE         — закрыть AG-UI stream
  ↓ DONE / ERROR
  ↓ emit TaskEvent → telemetry
```

---

## Авто мульти-агентность (A2A)

После `ROUTE` пайплайн проверяет `_should_dispatch_a2a(analysis)`. Если A2A включён
и задача сложная/многокомпонентная (≥ `a2a.min_flags_for_dispatch` флагов из
`requires_code_gen/review/testing/deployment`, либо `complexity == "high"`), задача
уходит в мульти-агентный путь `_stage_a2a_auto` вместо одиночного `MODEL_CALL`.

**`a2a.execution_mode` (по умолчанию `"local"`):**

- **`local`** — `_run_multiagent_local`:
  1. `TaskDecomposer` разбивает задачу на роли (architect → developer → tester →
     reviewer → devops) с зависимостями.
  2. **Lead-оркестратор** (`a2a/multiagent.py::LeadOrchestrator`) — сильная модель
     (premium-тир или `a2a.lead_model`) оценивает задачу и назначает каждой роли
     **тир модели** (`premium|standard|cheap`) и **скилы** (из registry). При сбое
     LLM-lead — детерминированный fallback (`_ROLE_TIER` + top-скилы роли).
  3. Тир → конкретная (model, provider) через `resolve_tier_model()`: реальный пул
     `_PROVIDER_MODELS`, отфильтрованный `ProviderHealthChecker`
     (strong = anthropic/cloudflare-dynamic, weak = workers-ai/deepseek/opencode-zen/
     mimo/omniroute).
  4. `run_local` исполняет суб-агентов **в процессе** через `AIGateway.chat()` в
     порядке зависимостей, прокидывая результаты предыдущих ролей. Каждый агент — со
     своей моделью, персоной и скилами.
  5. Merge → `TaskEvent` с `a2a_dispatched=True`, `a2a_agents_used`,
     `a2a_assignments` (роль/тир/модель/скилы/токены/стоимость).

- **`federation`** — суб-задачи уходят на remote-агентов (`a2a.federation_url`)
  через `dispatch_parallel` (старый путь).

**Промоут в вебе:** `/api/run` с `executor=pipeline` для сложной задачи больше НЕ
промоутится в `claude-code` — `_would_dispatch_a2a()` оставляет её в пайплайне.
Простые код-задачи (1 флаг) по-прежнему идут в `claude-code` executor.

---

## Устойчивость мульти-агента (Rung A: heartbeat + watchdog)

`TaskEvent` эмитится только в **конце** прогона, поэтому зависшая/упавшая
мульти-агентная цепочка не оставляет следа, и watchdog её не видит. Rung A
(`voly/runtime/runs.py`) добавляет лёгкую in-flight запись:

- `run_local` пишет `RunRecord` в `telemetry.runs_dir` (`.voly/runs/<task_id>.json`)
  при старте и обновляет **heartbeat после каждого суб-агента** (`current_role`,
  `done_roles`, `heartbeat_at`). В конце — `status = completed | failed`.
- `Watchdog` считает прогон **stale**, если heartbeat старше
  `watchdog_stale_factor × a2a.task_timeout_seconds` (по умолчанию 2 × 120s).
  Крашнувшийся процесс оставляет запись `running` со старым heartbeat → её ловит
  watchdog.
- Трекинг **best-effort**: любые ошибки записи глотаются и не ломают прогон
  (как телеметрия). Запись атомарна (`tempfile` + `os.replace`).

CLI:

```bash
voly runs list                 # все прогоны (status/progress/age/role)
voly runs show <task_id>       # детали одного прогона
voly runs reap [--yes]         # найти (и пометить) прогоны без heartbeat
```

Записи заодно дают эмпирику для roadmap §6 — реальную длину цепочек и частоту
зависаний, — чтобы решить, нужны ли более дорогие рунги (checkpoint/resume).

---

## PipelineResult

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

## Agent Router

`voly/router.py:AgentRouter`

```python
analysis = router.analyze_task(task)
# analysis.requires_code_gen — True если задача требует изменения файлов
# analysis.task_type         — "code_generation" | "review" | "question" | ...

route = router.route(analysis)
# route.agent    — "developer" | "reviewer" | "architect" | ...
# route.model    — конкретная модель
# route.provider — "anthropic" | "openai" | ...
```

`requires_code_gen = True` когда задача содержит ключевые слова: implement, create, build,
add, write, fix, refactor, migrate, напиши, создай, добавь, реализуй, исправь, ...

Это используется в `web/routes/run.py` для smart dispatch.

---

## Изменение Pipeline

Правила:
- Сохранять `PipelineResult` структуру
- Каждая стадия — именованный метод `_stage_*`
- Обязательно `emit TaskEvent` в telemetry
- Нет product-specific логики в `voly/`
- При изменении — обновить `docs/ARCHITECTURE.md` и этот файл
