---
name: voly-plan
description: Create an action plan for a VOLY task, classify complexity, decide which agents to spawn (zen for simple tasks, claude-code for complex), and prepare the execution with doc-update requirements.
---

# VOLY Plan Skill

Используй этот скил чтобы:
1. Оценить задачу
2. Выбрать нужных агентов (zen для простых, claude-code для сложных)
3. Создать пошаговый план
4. Запустить агентов через `voly runner`

---

## Шаг 1 — Прочитай нужную документацию

Определи область задачи и прочитай перед планированием:

```
Backend (Python)  → docs/backend/pipeline.md, executors.md, ai-gateway.md
Frontend (Svelte) → docs/frontend/overview.md, components.md
DSPy              → docs/backend/dspy.md
Config / env      → docs/backend/config.md
API               → docs/backend/api.md
```

Также прочитай: `CLAUDE.md` (правила проекта) и `voly.yaml` (текущий конфиг).

---

## Шаг 2 — Классификация сложности

### Простые задачи → zen (бесплатные агенты)

- Обновить документацию
- Небольшие исправления (1-2 файла)
- Добавить hint/label в UI
- Исправить опечатку или переименовать переменную
- Добавить env var в config/docs
- Написать простой тест

### Сложные задачи → claude-code

- Новый executor с billing_error logic
- Новая pipeline стадия
- Интеграция нового провайдера в AI Gateway
- DSPy программа с новой сигнатурой
- Рефакторинг с изменением нескольких файлов
- Архитектурные изменения

### Критерии выбора

| Критерий | zen | claude-code |
|---|---|---|
| Файлов для изменения | 1-2 | 3+ |
| Нужно понимать архитектуру | нет | да |
| Новая функциональность | нет | да |
| Только doc/config update | да | нет |
| Рефакторинг существующего | нет | да |

---

## Шаг 3 — Создай план

Формат плана:

```
# Plan: <название задачи>

## Цель
<одно предложение что нужно сделать>

## Сложность: simple / medium / complex
## Агент: zen / claude-code

## Шаги
1. Прочитать <файл> для понимания текущей реализации
2. Изменить <файл>: <что именно>
3. Обновить docs/<backend|frontend>/<doc.md>: <что добавить>
4. Запустить smoke test: `pytest tests/test_dspy_runtime_smoke.py -q`
5. Создать отчёт: /voly-report

## Файлы которые будут изменены
- voly/executor/my_exec.py (создать)
- voly/runner/agent_runner.py (добавить в EXECUTOR_NAMES)
- docs/backend/executors.md (обновить)

## Doc requirements
- docs/backend/executors.md → добавить раздел "MyExecutor"
- docs/ARCHITECTURE.md → обновить executor table

## Тесты
- python -c "import ..." (smoke)
- pytest tests/ -q
```

---

## Шаг 4 — Запуск агентов

### Через VOLY runner (рекомендуется)

```bash
# Простая задача — zen (бесплатно)
voly run "обнови docs/backend/executors.md — добавь раздел про MyExecutor" \
  --executor zen \
  --cwd /home/lanies/git/voly

# Сложная задача — claude-code
voly run "добавь новый WranglerV2Executor с поддержкой streaming" \
  --executor claude-code \
  --cwd /home/lanies/git/voly \
  --max-turns 40
```

### Параллельный запуск

```bash
# Несколько независимых задач параллельно
voly run "обнови docs/frontend/components.md" --executor zen &
voly run "обнови docs/backend/dspy.md" --executor zen &
voly run "реализуй новый executor" --executor claude-code --max-turns 30 &
wait
```

### Через Web UI

1. `voly serve` → открыть http://localhost:7860
2. Для простых задач: executor=zen, вставить задачу
3. Для сложных: executor=claude-code, указать cwd=/home/lanies/git/voly

---

## Шаг 5 — После выполнения

Каждый агент должен:
1. Обновить docs если изменил поведение кода
2. Запустить smoke tests
3. Создать отчёт: `/voly-report`

---

## Правило: docs + code вместе

**Никогда не завершать задачу без обновления docs.**

Если агент изменил код → он же обновляет соответствующий doc файл.
Это не отдельный шаг — это часть того же PR/коммита.
