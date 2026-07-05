# Skill Registry

## Введение

**Skill Registry** — централизованное хранилище и система управления скиллами в VOLY. Реестр предоставляет единый API и CLI для регистрации, поиска, версионирования и автоматического создания скиллов. Любой агент VOLY обращается к реестру, чтобы найти подходящий скилл для текущей задачи на основе контекста, совместимости и атрибутов запроса.

## Что такое скиллы

**Скилл** — модульное, переиспользуемое описание способности агента выполнить конкретное действие. Скилл может представлять:
- вызов внешнего API (например, `deploy-to-kubernetes`)
- выполнение скрипта (`run-tests`)
- взаимодействие с сервисами (`create-jira-ticket`)
- последовательность команд для CI/CD

Скиллы отделены от логики агентов. Агенты *ссылаются* на скиллы, а определяются скиллы в реестре — это позволяет переиспользовать навык в разных агентах и проектах.

## Источники скиллов (SkillSource)

| Источник | Описание | Приоритет |
|----------|----------|-----------|
| `BUILTIN` | Встроенные скиллы ядра VOLY | Базовый |
| `PROJECT` | Скиллы проекта из `.voly/skills/` | Высокий |
| `ORGANIZATION` | Скиллы организации из общего репозитория | Высокий |
| `MARKETPLACE` | Скиллы сообщества (Cloudflare Worker) | Средний |
| `GENERATED` | Авто-генерация из успешных выполнений | Черновик до подтверждения |

## Встроенные скиллы

| ID | Название | Теги |
|----|----------|------|
| `skill-architecture` | Software Architecture | architecture, design, system |
| `skill-nextjs` | Next.js Development | nextjs, react, frontend |
| `skill-dotnet` | .NET Development | dotnet, csharp, aspnet |
| `skill-postgres` | PostgreSQL | postgres, sql, database |
| `skill-docker` | Docker & Containers | docker, container, devops |
| `skill-kubernetes` | Kubernetes | kubernetes, k8s, orchestration |
| `skill-security` | Security Best Practices | security, owasp, compliance |
| `skill-testing` | Testing Strategy | testing, quality, tdd |
| `skill-temporal` | Temporal Workflows | temporal, workflow |
| `skill-cloudflare` | Cloudflare Platform | cloudflare, serverless, edge |

## Структура скилла

```python
@dataclass
class Skill:
    id: str                          # уникальный идентификатор
    name: str                        # человекочитаемое название
    description: str                 # описание
    source: SkillSource              # источник (builtin/project/org/marketplace/generated)
    tags: list[str]                  # теги для поиска
    capabilities: list[str]          # что умеет делать (architecture, frontend, testing...)
    required_tools: list[str]        # необходимые MCP-инструменты
    compatible_agents: list[str]     # агенты, которые могут использовать скилл
    compatible_languages: list[str]  # языки программирования (* = все)
    compatible_frameworks: list[str] # фреймворки (* = все)
    content: str                     # тело скилла (инструкции / best practices)
    version: str                     # версия скилла
    usage_count: int                 # счётчик использований
    success_rate: float              # доля успешных применений (0.0–1.0)
```

## Регистрация скилла из YAML

**Шаг 1: создайте файл `.voly/skills/deploy-service.yaml`**

```yaml
id: deploy-service
name: Deploy Service
description: Деплоит сервис в Kubernetes по манифесту
source: project
tags:
  - kubernetes
  - deploy
  - microservices
capabilities:
  - deployment
  - orchestration
required_tools:
  - kubernetes
compatible_agents:
  - devops
  - architect
compatible_languages:
  - "*"
compatible_frameworks:
  - "*"
content: |
  Для деплоя используй kubectl apply -f <manifest>.
  Всегда проверяй readiness probe перед финализацией деплоя.
  Откатывай через kubectl rollout undo.
```

**Шаг 2: файлы из `.voly/skills/` подхватываются автоматически** при запуске `voly` из директории проекта.

## Поиск скиллов через CLI

```bash
# Все скиллы
voly registry skills

# По тегу
voly registry skills --tag kubernetes
voly registry skills --tag deploy --tag devops

# По совместимому агенту
voly registry skills --agent devops

# По языку
voly registry skills --lang python
voly registry skills --lang typescript --lang go

# Комбинированный поиск
voly registry skills --tag security --agent reviewer --lang python
```

## Авто-генерация скиллов

После каждого успешного выполнения задачи VOLY анализирует результат и может сгенерировать новый скилл:

```python
# Внутри pipeline.py — вызывается автоматически
skill = registry.auto_generate(
    task="задача",
    result="результат выполнения",
    agent_name="developer",
)
# skill.source = SkillSource.GENERATED
# skill.status = SkillStatus.CANDIDATE
```

Сгенерированный скилл попадает в очередь кандидатов. Для подтверждения:

```python
from voly.registry.skills import SkillRegistry

reg = SkillRegistry()
reg.approve_candidate("skill-id")  # переводит в ACTIVE
reg.reject_candidate("skill-id")   # удаляет кандидата
```

## Программный доступ

```python
from voly.registry.skills import SkillRegistry, Skill, SkillSource

reg = SkillRegistry()

# Поиск
skills = reg.search(tags=["kubernetes"], agent="devops", language="go")

# Регистрация
reg.register(Skill(
    id="my-skill",
    name="My Skill",
    description="...",
    source=SkillSource.PROJECT,
    tags=["custom"],
    capabilities=["custom-action"],
    compatible_agents=["developer"],
    compatible_languages=["python"],
    compatible_frameworks=["*"],
    content="Инструкции для агента...",
))

# Получить конкретный скилл
skill = reg.get("skill-postgres")
print(skill.content)
```

## Marketplace CLI

Marketplace развёрнут как Cloudflare Worker. URL задаётся в `voly.yaml`:

```yaml
registry:
  skills_path: ".voly/skills"
  marketplace_url: "${CF_WORKER_MARKETPLACE_URL}"
```

Или через переменные окружения: `CF_WORKER_MARKETPLACE_URL`, `MARKETPLACE_URL`.

```bash
# Список скиллов в marketplace
voly skill list

# Локальный реестр (builtin + .voly/skills/)
voly skill list --local

# Семантический поиск
voly skill search "react frontend"

# Установка в .voly/skills/
voly skill install skill-nextjs

# Публикация YAML
voly skill publish .voly/skills/my-skill.yaml

# Детали скилла
voly skill show skill-nextjs
voly skill show my-skill --local
```

## Программный доступ к marketplace

```python
from voly.registry.skills import create_skill_registry

reg = create_skill_registry(
    skills_path=".voly/skills",
    marketplace_url="${CF_WORKER_MARKETPLACE_URL}",
)

# Установка из marketplace
skill = reg.install_from_marketplace("skill-nextjs")

# Публикация
reg.publish_to_marketplace({"id": "my-skill", "name": "My Skill", ...})
```
