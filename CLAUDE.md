# CodeOps — Agent Instructions

> **Project:** CodeOps — AI control plane для запуска агентов, управления стоимостью, маршрутизации задач и оркестрации.

## Цель проекта

CodeOps маршрутизирует задачи разработчика к нужному AI-агенту, управляет billing fallback chain, собирает телеметрию и предоставляет web UI + REST API.

**Ключевые компоненты:**
- **Billing fallback chain:** `claude-code → wrangler (CF Workers AI) → zen (бесплатно)` — автоматически при ошибке биллинга
- **Smart dispatch:** Web UI с `executor=pipeline` + code task → автопромоут в `claude-code`
- **DSPy TaskPlanner:** рефайнит задачу перед executor, собирает (task, result) примеры для оптимизации
- **CF AI Gateway route schema:** `/infer` endpoint в CF Worker маршрутизирует через CF Dashboard роут схему
- **Local context:** перед executor собирает релевантные файлы проекта через grep

CodeOps project-agnostic — нет product-specific логики в `codeops/`.

---

## Скилы — читай ПЕРЕД началом работы

| Скил | Когда использовать |
|---|---|
| `/codeops-plan` | Создать план задачи, выбрать агентов (zen vs claude-code), запустить |
| `/codeops-backend` | Работа на Python backend: pipeline, executors, gateway, DSPy, API |
| `/codeops-frontend` | Работа на Svelte UI: компоненты, API client |
| `/codeops-report` | Создать отчёт после завершения задачи |

---

## Документация — читай перед изменениями

```
docs/
  backend/
    pipeline.md      ← Pipeline стадии, AgentRouter, smart dispatch
    executors.md     ← Все executors, billing fallback chain, WranglerExecutor
    ai-gateway.md    ← AIGateway, CF route schema, провайдеры, env vars
    dspy.md          ← DSPy programs, TaskPlanner, shadow/active, adapter
    config.md        ← codeops.yaml, env vars, CodeOpsConfig поля
    api.md           ← FastAPI endpoints, SSE events, CF Worker /infer
  frontend/
    overview.md      ← Svelte 5 стек, структура ui/, dev/build
    components.md    ← Все компоненты, их props/events
    api-client.md    ← SSE вызовы, формат событий, обработка fallback
  ARCHITECTURE.md    ← Высокоуровневая схема + таблицы стадий/executor
```

---

## Правило документации (ОБЯЗАТЕЛЬНО)

**Любое изменение поведения кода = обновление соответствующего doc файла.**

| Что изменил | Обнови |
|---|---|
| Executor (добавил/изменил) | `docs/backend/executors.md` |
| Pipeline стадия / PipelineResult | `docs/backend/pipeline.md` + `docs/ARCHITECTURE.md` |
| AI Gateway / провайдер | `docs/backend/ai-gateway.md` |
| DSPy программа / конфиг | `docs/backend/dspy.md` |
| Config / env var | `docs/backend/config.md` |
| API endpoint | `docs/backend/api.md` |
| Svelte компонент | `docs/frontend/components.md` |
| API вызов из UI | `docs/frontend/api-client.md` |

---

## Выбор агента для задачи

| Задача | Агент | Почему |
|---|---|---|
| Обновить документацию | `zen` | простая задача, бесплатно |
| Добавить label/hint в UI | `zen` | 1-2 файла |
| Исправить опечатку/переименовать | `zen` | минимальный риск |
| Новый executor / DSPy программа | `claude-code` | сложная архитектура |
| Новая pipeline стадия | `claude-code` | несколько файлов + docs |
| Интеграция провайдера | `claude-code` | gateway + config + docs |
| Рефакторинг 3+ файлов | `claude-code` | нужен контекст |

```bash
# Запуск через CodeOps runner
codeops run "<задача>" --executor zen --cwd /home/lanies/git/codeops
codeops run "<задача>" --executor claude-code --cwd /home/lanies/git/codeops
```

---

## Scope rules

| Rule | Meaning |
|---|---|
| Project-agnostic core | Нет hardcoded путей/продуктовой логики в `codeops/` |
| Target project via `--cwd` | Executors работают на внешних репо через `--cwd` |
| Generated state not source | Не коммитить `.codeops/events/`, DSPy datasets, compiled programs |
| Gateway first | Model calls идут через `AIGateway.chat()` — кроме executors |
| Docs move with code | Docs обновляются вместе с кодом, в том же коммите |

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
codeops status
```

Optional: `pip install -e ".[dspy,dev]"` или `pip install -e ".[cursor,dev]"`

Smoke checks:
```bash
python -c "import codeops.pipeline, codeops.inference; from codeops.config import CodeOpsConfig; assert CodeOpsConfig().dspy.enabled is False"
pytest tests/test_dspy_runtime_smoke.py
```

---

## Repository structure

```
codeops/
  cli/              pipeline/       inference/     dspy/
  ai_gateway/       executor/       catalog/       registry/
  memory/           rtk/            headroom/      telemetry.py
  workflow/         a2a/            agui/          web/
  runner/           router.py
ui/                 cf-workers/     docs/          tests/
CLAUDE.md           codeops.yaml    README.md
```

---

## CLI commands

```
codeops run <task>    codeops match <task>    codeops compare <task>
codeops savings       codeops status          codeops scan
codeops registry agents        codeops registry skills       codeops skill list
codeops model list             codeops ai-gateway status     codeops catalog sync
codeops dspy status            codeops workflow list        codeops workflow run
codeops memory search <query>  codeops serve                codeops ui
codeops a2a                    codeops agui                 codeops rtk
codeops headroom               codeops mcp                  codeops runner
codeops telemetry              codeops balance              codeops init
codeops setup                  codeops config               codeops tunnel
codeops spend status
```

При удалении команды: убери из `cli/main.py`, `cli/commands/__init__.py`, тесты, README, docs.

---

## Testing

CI: smoke gate — base install, import без DSPy, import с DSPy, runtime smoke tests.

```bash
pytest tests/test_dspy_runtime_smoke.py   # обязательно после любых изменений
pytest tests/ -q                          # полный прогон
```

---

## Do not commit

`.env`, `.codeops/events/`, `.codeops/dspy/datasets/`, `.codeops/dspy/programs/`,
`.codeops/reports/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`,
`ui/node_modules/`, `codeops/web/static/assets/`

---

## Troubleshooting

| Problem | First check |
|---|---|
| `DSPy is not installed` | `pip install -e ".[dspy]"` или `dspy.enabled: false` |
| Base install imports DSPy | Проверь top-level `import dspy` вне lazy paths |
| Pipeline bypasses gateway | Убедись что runtime использует `AIGateway.chat()` |
| Executor не пишет файлы | Проверь `--cwd` и credentials executor |
| Billing fallback не срабатывает | Проверь `billing_error=True` в ExecutorResult |
| Smart dispatch не срабатывает | Установи `CODEOPS_PROJECT_CWD` или `default_cwd` в `codeops.yaml` |
| Wrangler executor недоступен | Запусти `cd cf-workers/agent && wrangler dev` |
| CI fails with test collection | Проверь `pyproject.toml` pytest config |
