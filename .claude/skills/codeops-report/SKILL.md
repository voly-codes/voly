---
name: codeops-report
description: Create a task completion report after finishing any CodeOps task. Shows what changed, which files were modified, test results, doc updates, and open items.
---

# CodeOps Report Skill

Создай отчёт о завершённой задаче. Сохрани в `.codeops/reports/`.

---

## Формат отчёта

Создай файл: `.codeops/reports/YYYY-MM-DD-<краткое-название>.md`

```markdown
# Report: <название задачи>

**Date:** YYYY-MM-DD
**Agent:** claude-code / zen / wrangler / pipeline
**Status:** completed / partial / failed

## Summary

<2-3 предложения — что было сделано и почему>

## Changed files

| File | Action | Description |
|---|---|---|
| codeops/executor/wrangler.py | created | WranglerExecutor — calls CF Workers AI |
| codeops/runner/agent_runner.py | modified | Added wrangler to BILLING_FALLBACK_CHAIN |
| docs/backend/executors.md | updated | Added WranglerExecutor section |

## What was added / changed

### <Компонент 1>
<что именно изменилось>

### <Компонент 2>
...

## Documentation updates

- [ ] docs/backend/executors.md — обновлён (добавлен WranglerExecutor)
- [ ] docs/backend/ai-gateway.md — обновлён (CF route schema)
- [ ] docs/ARCHITECTURE.md — обновлён если меняли архитектуру

## Tests

```bash
# Запущенные тесты
pytest tests/test_dspy_runtime_smoke.py -q
# Результат: 3 passed
```

## Billing / cost impact

- Executor chain: claude-code → wrangler → zen
- Новый executor wrangler: CF Workers AI (отдельный billing)
- Zen как last resort: бесплатно

## Open items / TODO

- [ ] Написать интеграционный тест для WranglerExecutor
- [ ] Добавить wrangler в CI health check

## Chain logs (если применимо)

```
[CHAIN:START] task='...' executor=claude-code cwd='/path'
[CHAIN:BILLING_FALLBACK] claude-code → wrangler  reason='credit balance is too low'
[CHAIN:FALLBACK_RESULT] executor=wrangler success=True
```
```

---

## Как создать отчёт

```bash
# Узнать что изменилось
git diff --stat HEAD

# Узнать какие файлы созданы/изменены с последнего коммита
git status

# Запустить тесты перед отчётом
pytest tests/test_dspy_runtime_smoke.py -q

# Создать директорию если нет
mkdir -p .codeops/reports

# Записать отчёт
# Используй текущую дату из env: date +%Y-%m-%d
```

---

## Правила

1. Отчёт создаётся ПОСЛЕ завершения задачи — не во время
2. Список файлов берётся из `git diff --stat` или `git status`
3. Тесты должны быть запущены ДО создания отчёта
4. Open items — честный список что осталось незакрытым
5. Если задача провалилась — отчёт всё равно создаётся с `Status: failed` и объяснением
6. Отчёты НЕ коммитятся (`.codeops/` в `.gitignore`)
