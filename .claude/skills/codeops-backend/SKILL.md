---
name: codeops-backend
description: Guide for working on VOLY Python backend — pipeline, executors, AI gateway, DSPy, config, API routes. Use this skill for any backend changes.
---

# VOLY Backend Development Skill

## Before writing any code — read

| Меняешь | Прочитай |
|---|---|
| Executor (claude-code, wrangler, zen, ...) | `docs/backend/executors.md` |
| Pipeline стадии / PipelineResult | `docs/backend/pipeline.md` |
| AI Gateway / провайдеры / CF | `docs/backend/ai-gateway.md` |
| DSPy programs / runner / adapter | `docs/backend/dspy.md` |
| Config / env vars / codeops.yaml | `docs/backend/config.md` |
| API routes (/api/run, /api/tasks, ...) | `docs/backend/api.md` |
| CF Worker (infer.ts, index.ts) | `docs/backend/ai-gateway.md` + `cf-workers/agent/src/` |

## Architecture rules

- `AIGateway.chat()` — единственный выход к моделям из Pipeline и DSPy
- Executors могут bypass gateway (они запускают субпроцессы: claude CLI, wrangler dev, opencode)
- Нет product-specific логики в `codeops/` — только через `--cwd`
- `billing_error=True` на ExecutorResult → AgentRunner запускает fallback chain
- DSPy импортируется только lazy (не на уровне модуля)

## Billing fallback chain

```
claude-code  →  wrangler  →  zen
```
Только file-writing executors. Не добавлять text-only провайдеры в цепочку.

## Code patterns

```python
# Новый executor
class MyExecutor(Executor):
    def run(self, task, *, cwd, max_turns, timeout) -> ExecutorResult:
        try:
            ...
            return ExecutorResult(success=True, output=out)
        except SomeBillingError as e:
            return ExecutorResult(success=False, error=str(e), billing_error=True)

# Добавить в _build_executor() factory в agent_runner.py
# Добавить в EXECUTOR_NAMES frozenset
# Если file-capable + свой billing → добавить в BILLING_FALLBACK_CHAIN
```

```python
# DSPy программа (lazy import dspy)
class MyProgram(BaseProgram):
    program_id = "my-program"
    agents = ("developer",)
    strategy = "chain_of_thought"

    def build(self):
        self.ensure_dspy()
        import dspy
        return dspy.ChainOfThought(MySignature())

register_program(MyProgram())  # в конце модуля
```

## Testing

```bash
# Smoke test (всегда после изменений)
python -c "import codeops.pipeline, codeops.inference; from codeops.config import VOLYConfig; assert VOLYConfig().dspy.enabled is False"
pytest tests/test_dspy_runtime_smoke.py -q

# Весь тест-сюит
pytest tests/ -q
```

## Documentation requirement (MANDATORY)

После любого изменения поведения обнови соответствующий файл в `docs/backend/`:

| Что изменил | Обнови |
|---|---|
| Executor (добавил/изменил) | `docs/backend/executors.md` |
| Pipeline стадия | `docs/backend/pipeline.md` + `docs/ARCHITECTURE.md` |
| Gateway / провайдер | `docs/backend/ai-gateway.md` |
| DSPy программа / конфиг | `docs/backend/dspy.md` |
| Config / env var | `docs/backend/config.md` |
| API endpoint | `docs/backend/api.md` |

## Completion report

После завершения задачи создай отчёт: `/codeops-report`
