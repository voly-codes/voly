# Workflow Engine

## Что такое Workflow

Workflow в VOLY — конечный автомат, управляющий выполнением задачи от начала до конца. Каждый Workflow состоит из упорядоченных шагов (`WorkflowStep`), объединённых в объекте `WorkflowDefinition`.

Ключевые возможности:
- декларативное описание пайплайна агентов
- зависимости между шагами (DAG)
- human approval gates на критических этапах
- полный жизненный цикл с контролем состояния

## Структура WorkflowDefinition и WorkflowStep

```python
@dataclass
class WorkflowDefinition:
    name: str          # уникальное имя (используется в CLI)
    description: str   # описание
    steps: dict[str, WorkflowStep]  # шаги по имени
```

```python
@dataclass
class WorkflowStep:
    agent: str              # агент-исполнитель (architect, developer, reviewer...)
    depends_on: list[str]   # шаги, которые должны завершиться до запуска
    approval: str           # "auto" | "human" — human требует ручного подтверждения
    task_template: str      # шаблон задачи с {task} и {step_results}
```

## Встроенные Workflow

### `feature-delivery` — доставка новой функциональности

```
architect → develop → review → test → deploy [human approval]
```

| Шаг | Агент | Зависит от | Approval |
|-----|-------|-----------|---------|
| `architect` | architect | — | auto |
| `develop` | developer | architect | auto |
| `review` | reviewer | develop | auto |
| `test` | tester | review | auto |
| `deploy` | devops | test | **human** |

### `bugfix` — исправление бага

```
analyze → fix → review → test
```

| Шаг | Агент | Зависит от |
|-----|-------|-----------|
| `analyze` | developer | — |
| `fix` | developer | analyze |
| `review` | reviewer | fix |
| `test` | tester | review |

### `code-review` — всесторонний аудит кода

```
static ──┐
          ├──→ security ──→ report
architect─┘
```

| Шаг | Агент | Зависит от |
|-----|-------|-----------|
| `static` | reviewer | — |
| `architecture` | architect | — |
| `security` | security | static |
| `report` | reviewer | architecture, security |

## Создание кастомного Workflow

```python
from voly.workflow import Workflow, BUILTIN_WORKFLOWS

wf = Workflow("db-migration")
wf.description = "Безопасная миграция базы данных"

wf.step("backup", agent="devops",
        task_template="Создай бэкап БД перед миграцией: {task}")

wf.step("validate", agent="architect", depends_on=["backup"],
        task_template="Проверь совместимость схем для: {task}")

wf.step("migrate", agent="developer", depends_on=["validate"],
        approval="human",
        task_template="Выполни скрипт миграции: {task}")

wf.step("verify", agent="tester", depends_on=["migrate"],
        task_template="Проверь целостность данных после миграции: {task}")

BUILTIN_WORKFLOWS["db-migration"] = wf
```

## CLI

### Запуск

```bash
voly workflow run feature-delivery "Добавить OAuth2 авторизацию"
voly workflow run bugfix "API возвращает 500 при пустом теле запроса"
voly workflow run code-review "Ревью PR #142"
```

### Статус

```bash
voly workflow list           # все доступные определения
voly workflow status         # активные инстансы
```

### Human Approval Gates

Когда workflow доходит до шага с `approval="human"`, он переходит в состояние `paused` и выводит:

```
Workflow paused — awaiting human approval for: ['deploy']
Use 'voly workflow approve <id> <step>' to continue
```

Подтверждение:

```python
from voly.pipeline import Pipeline
from voly.config import load_config

pipeline = Pipeline(load_config())
pipeline.approve_workflow_step(instance_id="...", step_name="deploy")
```

## WorkflowState — жизненный цикл

```
CREATED → RUNNING → PAUSED ─→ RUNNING (после approve)
                         └─→ FAILED  (после reject)
          RUNNING → COMPLETED
          RUNNING → FAILED
```

| Состояние | Описание |
|-----------|----------|
| `created` | Инстанс создан, ещё не запущен |
| `running` | Агенты выполняют шаги |
| `paused` | Ожидает human approval |
| `waiting_approval` | Шаг поставлен в очередь на одобрение |
| `completed` | Все шаги выполнены |
| `failed` | Ошибка или reject |

## Программный запуск

```python
from voly.pipeline import Pipeline
from voly.config import load_config

pipeline = Pipeline(load_config())
pipeline.setup_environment()

# Запуск
instance_id = pipeline.run_workflow("feature-delivery", "Добавить платёжную страницу")

# Статус
instance = pipeline.workflow.get_instance(instance_id)
print(instance.state.value)          # running / paused / completed
print(instance.progress())           # {"percent": 60, "completed": 3, "total": 5}
print(list(instance.approvals_pending))  # ["deploy"]

# Подтверждение
pipeline.approve_workflow_step(instance_id, "deploy")
```

> **Статус**: прототип. Workflow работает in-memory — инстансы не переживают перезапуск. Production backend (Temporal) запланирован на Beta.
