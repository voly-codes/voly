# Pipeline — Backend Reference

`codeops/pipeline/core.py:Pipeline` — оркестратор для **text-only** задач (inference через AIGateway).
Для задач с записью файлов — используй `AgentRunner` + executor.

---

## Когда Pipeline, когда AgentRunner

| Сценарий | Что использовать |
|---|---|
| Вопрос / суммаризация / review без правок | Pipeline → AIGateway.chat() |
| Написать/изменить файлы в проекте | AgentRunner → executor (claude-code / wrangler / zen) |
| Web UI задача с кодом | smart dispatch: pipeline → claude-code автоматически |
| CLI `codeops run --executor cursor` | AgentRunner напрямую |

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

`codeops/router.py:AgentRouter`

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
- Нет product-specific логики в `codeops/`
- При изменении — обновить `docs/ARCHITECTURE.md` и этот файл
