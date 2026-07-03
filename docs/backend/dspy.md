# DSPy — Backend Reference

DSPy — опциональный слой оптимизации. Он может заменять или улучшать промпты
через телепромптеры (BootstrapFewShot, MIPROv2). Весь трафик DSPy идёт через
`AIGateway.chat()` — никакого прямого доступа к моделям.

Если `dspy` не установлен — всё работает как прежде через ClassicRuntime.

---

## Режимы

| Режим | Поведение |
|---|---|
| `off` | DSPy не используется |
| `shadow` | DSPy запускается параллельно, результат логируется, но не возвращается пользователю |
| `active` | DSPy-результат заменяет классический для агентов из `config.dspy.agents` |

Проверить статус: `voly dspy status`

---

## Два места интеграции DSPy

### 1. Pipeline path (inference)

```
HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL
```

`voly/inference/runtime.py` вызывает `DSPyRunner.run()` перед финальным
обращением к `AIGateway.chat()`. Работает для text-only задач через Pipeline.

Программы: `reviewer`, `architect`, `bugfixer`, `documenter`, `router`.

### 2. Executor path (AgentRunner)

```
task → _dspy_plan_task() → refined_task → executor.run() → result
                                                          ↓
                                              _dspy_store_example()
                                              → datasets_dir/task_planner/
```

`voly/runner/agent_runner.py` вызывает `TaskPlannerProgram` перед запуском
любого executor. Активно только если `dspy.enabled=true`.

После выполнения сохраняет пример `(task, refined_task, result)` в JSONL для
последующей оптимизации.

---

## TaskPlannerProgram (`voly/dspy/programs/task_planner.py`)

**Сигнатура:**
- Input: `task` (оригинальная задача), `project_context` (краткий контекст проекта)
- Output: `refined_task` (переформулированная задача), `success_criteria`, `estimated_complexity`

**Стратегия:** `ChainOfThought` — модель рассуждает пошагово перед ответом.

**Применение:** перед executor. Если DSPy недоступен или падает — executor
получает оригинальный `task` (graceful fallback).

**Метрика оптимизации:** `task_quality_metric` — вознаграждает за специфичность
(длина refined_task vs оригинал) и completeness (количество критериев приёмки).

---

## Остальные программы

| Program ID | Агенты | Сигнатура |
|---|---|---|
| `task_planner` | developer, architect, bugfixer, tester, devops | task → refined_task + criteria |
| `code-review` | reviewer | task + diff → summary + risks + bugs + patch |
| `architecture-analysis` | architect | task + files → diagnosis + proposed_design + plan |
| `generate-docs` | documenter | task + source → title + overview + usage |
| `bug-analysis` | bugfixer | task + code + stacktrace → root_cause + patch |
| `task-routing` | router | task → agent + complexity + confidence |

---

## DSPy adapter (`voly/dspy/adapter.py`)

`VOLYDSPyLM` — адаптер между DSPy и VOLY AIGateway. Реализует DSPy `BaseLM`
интерфейс. Все DSPy-вызовы идут через `gateway.chat()` — сохраняется cache, DLP,
rate limits, spend limits.

```python
lm = VOLYDSPyLM(gateway=gateway, model="claude-sonnet-4-6", provider="anthropic")
dspy.configure(lm=lm)
```

---

## Datasets и compilation

Сохранённые примеры (`datasets_dir/task_planner/*.jsonl`) можно использовать для
оптимизации через телепромптеры:

```python
from voly.dspy.compiler import DSPyCompiler
compiler = DSPyCompiler(config)
compiler.compile("task_planner", optimizer="bootstrap", tag="v1")
```

Compiled programs хранятся в `programs_dir/` — это **runtime artifacts**, не source.
Не коммитить в git. Продвинуть в production: `voly dspy status` → promote.

---

## Конфиг

```yaml
# voly.yaml
dspy:
  enabled: false          # true чтобы включить
  mode: shadow            # off | shadow | active
  model: llama-scout      # модель для DSPy inference (из секции models:)
  provider: workers-ai    # провайдер для DSPy; пустая строка = из model config
  agents: []              # empty = все агенты (в active mode)
  programs_dir: .voly/dspy/programs
  datasets_dir: .voly/dspy/datasets
  active_tag: production
  shadow_tag: candidate
```

`model` / `provider` — определяют какую модель использует DSPy для inference, **независимо** от routing модели задачи. Рекомендуется указывать дешёвую/бесплатную модель (например `llama-scout` через `workers-ai`), чтобы DSPy не конкурировал за баланс с основными executor-ами.

Логика выбора модели в `DSPyRunner._get_lm()`:
1. `config.dspy.model` → `config.dspy.provider` если оба заданы
2. `config.dspy.model` → provider из `get_model_config(model)` если provider пустой
3. Route model / provider как fallback (если `dspy.model` не задан)

---

## Телеметрия — `dspy_used`

В `TaskEvent.dspy_used`:
- `True` — DSPy успешно выполнился (в `shadow` mode — результат не возвращён пользователю, но DSPy отработал)
- `False` — DSPy не запускался или завершился с ошибкой

В `shadow` mode `dspy_used=True` означает "DSPy запустился", а не "результат использован". Поле `mode="shadow"` показывает что вывод не влиял на ответ.

---

## Правила

- `AIGateway.chat()` — единственный выход к моделям
- `shadow` mode НЕ меняет вывод для пользователя
- `active` mode должен иметь fallback на classic
- Compiled programs/datasets — runtime artifacts, не коммитить
- Не импортировать `dspy` на уровне модуля — только в lazy paths
