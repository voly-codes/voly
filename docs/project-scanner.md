# Project Scanner

## Назначение

Project Scanner анализирует репозиторий и строит профиль проекта (`ProjectProfile`), который используется на двух уровнях:

1. **AgentRouter** — подбирает агентов и скиллы, соответствующие стеку
2. **SkillRegistry** — фильтрует скиллы по совместимому языку и фреймворку

Без сканирования роутер работает как generic-агент без учёта контекста проекта.

## Что обнаруживает Scanner

### Языки (`LanguageInfo`)

| Поле | Описание |
|------|----------|
| `name` | Название языка (Python, TypeScript...) |
| `percentage` | Доля файлов данного языка |
| `files_count` | Количество файлов |
| `version` | Версия из `pyproject.toml`, `package.json`, `.tool-versions` |
| `package_manager` | pip, npm, yarn, pnpm, cargo, go mod... |

Детектируются по расширениям файлов и конфиг-файлам (`go.mod`, `Cargo.toml`, `pubspec.yaml` и т.д.)

### Фреймворки (`FrameworkInfo`)

| Поле | Описание |
|------|----------|
| `name` | Название фреймворка |
| `language` | Связанный язык |
| `config_file` | Конфиг-файл, по которому обнаружен |
| `version` | Версия из зависимостей |

Примеры паттернов детектирования:

| Конфиг-файл | Фреймворк |
|------------|-----------|
| `next.config.js/ts` | Next.js |
| `pyproject.toml` + `[tool.fastapi]` | FastAPI |
| `angular.json` | Angular |
| `Cargo.toml` + `actix-web` dep | Actix |
| `pom.xml` / `build.gradle` | Spring Boot |
| `mix.exs` | Phoenix |

### CI/CD (`CIInfo`)

| Поле | Описание |
|------|----------|
| `provider` | github-actions, gitlab-ci, circleci, travis... |
| `config_path` | Путь к конфиг-файлу |
| `has_deploy` | Есть ли deploy-шаги |
| `has_tests` | Есть ли test-шаги |

### Инфраструктура (`InfraInfo`)

Детектируется по наличию файлов:

| Файл | Инструмент |
|------|-----------|
| `Dockerfile` / `docker-compose.yml` | Docker |
| `*.tf` | Terraform |
| `kubernetes/`, `k8s/`, `*.yaml` с `kind: Deployment` | Kubernetes |
| `serverless.yml` | Serverless Framework |
| `cdk.json` | AWS CDK |

## ProjectProfile — полная структура

```python
@dataclass
class ProjectProfile:
    # Базовые метаданные
    name: str              # имя директории
    root_path: str         # абсолютный путь
    total_files: int       # всего файлов
    total_lines: int       # всего строк кода

    # Стек
    languages: list[LanguageInfo]     # по убыванию percentage
    frameworks: list[FrameworkInfo]
    ci: CIInfo | None
    infra: InfraInfo

    # Типология
    project_type: str      # web-app, api, library, cli, monorepo...
    has_tests: bool
    has_docs: bool
    has_docker: bool

    # Рекомендации
    recommended_agents: list[str]    # agent ids подходящие для проекта
    recommended_skills: list[str]    # skill ids подходящие для проекта
    complexity_score: float          # 0.0–1.0
```

## CLI

```bash
# Сканировать текущую директорию
codeops scan

# Сканировать конкретный путь
codeops scan /path/to/project

# Вывод в JSON
codeops scan --json

# Только языки и фреймворки (быстрый режим)
codeops scan --summary
```

### Пример вывода

```
Project Profile
══════════════════════════════════════════

Name:        my-saas
Path:        /home/user/projects/my-saas
Files:       1,247
Lines:       89,341
Type:        web-app
Complexity:  0.73

Languages:
  TypeScript  68%  (847 files)   v5.4    [npm]
  Python      24%  (299 files)   v3.12   [pip]
  SQL          8%  (101 files)

Frameworks:
  Next.js   15.0  →  next.config.ts
  FastAPI   0.111 →  pyproject.toml

CI/CD:  github-actions
  Config:    .github/workflows/
  Tests:     yes
  Deploy:    yes

Infra:  Docker, Kubernetes
  docker-compose.yml, kubernetes/

Recommended Agents:  developer, architect, devops
Recommended Skills:  skill-nextjs, skill-postgres, skill-docker, skill-kubernetes
```

### JSON-вывод

```json
{
  "name": "my-saas",
  "root_path": "/home/user/projects/my-saas",
  "total_files": 1247,
  "total_lines": 89341,
  "project_type": "web-app",
  "complexity_score": 0.73,
  "languages": [
    {"name": "TypeScript", "percentage": 68, "files_count": 847, "version": "5.4", "package_manager": "npm"},
    {"name": "Python", "percentage": 24, "files_count": 299, "version": "3.12", "package_manager": "pip"}
  ],
  "frameworks": [
    {"name": "Next.js", "language": "TypeScript", "config_file": "next.config.ts", "version": "15.0"},
    {"name": "FastAPI", "language": "Python", "config_file": "pyproject.toml", "version": "0.111"}
  ],
  "ci": {"provider": "github-actions", "config_path": ".github/workflows/", "has_tests": true, "has_deploy": true},
  "infra": {"docker": true, "kubernetes": true, "terraform": false},
  "recommended_agents": ["developer", "architect", "devops"],
  "recommended_skills": ["skill-nextjs", "skill-postgres", "skill-docker", "skill-kubernetes"]
}
```

## Влияние на AgentRouter

После сканирования `AgentRouter` использует `ProjectProfile` при расчёте `routing_score`:

```
routing_score = base_score × language_match × framework_match × skill_coverage
```

- `language_match` — совпадение языка задачи с языками проекта (0.0–1.0)
- `framework_match` — совпадение фреймворка (0.0–1.0)
- `skill_coverage` — доля навыков агента, покрывающих стек проекта

Агент с `language_match=0.9` и `framework_match=0.85` будет выбран перед generic-агентом с `routing_score=0.5`.

## Расширение детектирования

### Добавить новый язык

```python
from codeops.scanner import Scanner

scanner = Scanner(".")
scanner.add_language_pattern(
    name="Zig",
    extensions=[".zig"],
    config_files=["build.zig"],
    version_source="build.zig.zon",
)
```

### Добавить новый фреймворк

```python
scanner.add_framework_pattern(
    name="Bun",
    language="TypeScript",
    config_file="bun.lockb",
    dep_key="bun",         # ищет в package.json dependencies
)
```

## Программный доступ

```python
from codeops.scanner import Scanner

scanner = Scanner("/path/to/project")
profile = scanner.scan()

print(profile.project_type)          # "web-app"
print(profile.complexity_score)      # 0.73
print([l.name for l in profile.languages])   # ["TypeScript", "Python"]
print(profile.recommended_skills)    # ["skill-nextjs", "skill-postgres"]

# Экспорт в dict
data = profile.to_dict()

# Сохранить в .codeops/profile.json для кэширования
profile.save()

# Загрузить кэш без повторного сканирования
profile = Scanner.load_cached("/path/to/project")
```

> **Статус**: прототип. Детектирование языков и фреймворков работает. `recommended_agents`/`recommended_skills` формируются эвристически; интеграция с `routing_score` в AgentRouter — в разработке.
