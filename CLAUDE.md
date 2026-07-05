# VOLY — Agent Instructions

> **Project:** VOLY — AI control plane для запуска агентов, управления стоимостью, маршрутизации задач и оркестрации.

## OpenWiki

This repository has documentation located in the /openwiki directory.

Start here:
- [OpenWiki quickstart](openwiki/quickstart.md)

OpenWiki includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

When working in this repository, read the OpenWiki quickstart first, then follow its links to the relevant architecture, workflow, domain, operation, and testing notes.

## Цель проекта

VOLY маршрутизирует задачи разработчика к нужному AI-агенту, управляет billing fallback chain, собирает телеметрию и предоставляет web UI + REST API.

**Ключевые компоненты:**
- **Billing fallback chain:** `claude-code → wrangler (CF Workers AI) → zen (бесплатно)` — автоматически при ошибке биллинга
- **Smart dispatch:** Web UI с `executor=pipeline` + code task → автопромоут в `claude-code`
- **DSPy TaskPlanner:** рефайнит задачу перед executor, собирает (task, result) примеры для оптимизации
- **CF AI Gateway route schema:** `/infer` endpoint в CF Worker маршрутизирует через CF Dashboard роут схему
- **Local context:** перед executor собирает релевантные файлы проекта через grep

VOLY project-agnostic — нет product-specific логики в `voly/`.

---

## Стратегическая архитектура — читай ПЕРВЫМ

VOLY = два слоя с разной ценностью:

- **Слой A — model gateway / routing / fallback между провайдерами моделей.** Конкурирует с OmniRoute / LiteLLM / OpenRouter — зрелая, занятая ниша. **Стабилизируется по минимуму и делегируется внешнему gateway** (VOLY уже умеет OmniRoute как upstream). НЕ источник денег и уникальности — не догонять по ширине провайдеров.
- **Слой B — оркестрация над file-capable CLI-агентами.** Executor chain (агенты пишут файлы в проект), billing fallback между CLI, мульти-агентная декомпозиция (тир модели на роль), project-agnostic executor path, телеметрия стоимости задач. **Это уникальность продукта + фундамент монетизации — сюда весь фокус развития.**

**Инвариант №1:** `AIGateway.chat()` — единственный выход к моделям. Через него идут pipeline, DSPy, суб-агенты, рантаймы — тогда кэш, DLP, spend limits, fallback и телеметрия достаются любому компоненту бесплатно. Никогда не вызывай провайдера в обход gateway (кроме executor-ов — это отдельный path).

**Не делать без явного запроса:** свой workflow-движок, Temporal (при необходимости — DBOS/Restate), ранний marketplace, наращивание периферии до стабилизации ядра B.

---

## Скилы — читай ПЕРЕД началом работы

| Скил | Когда использовать |
|---|---|
| `/voly-plan` | Создать план задачи, выбрать агентов (zen vs claude-code), запустить |
| `/voly-backend` | Работа на Python backend: pipeline, executors, gateway, DSPy, API |
| `/voly-frontend` | Работа на Svelte UI: компоненты, API client |
| `/voly-report` | Создать отчёт после завершения задачи |

---

## Документация — читай перед изменениями

```
docs/
  backend/
    pipeline.md      ← Pipeline стадии, AgentRouter, smart dispatch
    executors.md     ← Все executors, billing fallback chain, WranglerExecutor
    ai-gateway.md    ← AIGateway, CF route schema, провайдеры, env vars
    dspy.md          ← DSPy programs, TaskPlanner, shadow/active, adapter
    config.md        ← voly.yaml, env vars, VOLYConfig поля
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
# Запуск через VOLY runner (этот репозиторий: /home/lanies/git/codeops/voly)
voly run "<задача>" --executor zen --cwd /home/lanies/git/codeops/voly
voly run "<задача>" --executor claude-code --cwd /home/lanies/git/codeops/voly
```

---

## Scope rules

| Rule | Meaning |
|---|---|
| Project-agnostic core | Нет hardcoded путей/продуктовой логики в `voly/` |
| Target project via `--cwd` | Executors работают на внешних репо через `--cwd` |
| Generated state not source | Не коммитить `.voly/events/`, DSPy datasets, compiled programs |
| Gateway first | Model calls идут через `AIGateway.chat()` — кроме executors |
| Docs move with code | Docs обновляются вместе с кодом, в том же коммите |

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
voly status
```

Optional: `pip install -e ".[dspy,dev]"` или `pip install -e ".[cursor,dev]"`

Smoke checks:
```bash
python -c "import voly.pipeline, voly.inference; from voly.config import VOLYConfig; assert VOLYConfig().dspy.enabled is False"
pytest tests/test_dspy_runtime_smoke.py
```

---

## Repository structure

```
voly/
  cli/              pipeline/       inference/     dspy/
  ai_gateway/       executor/       catalog/       registry/
  memory/           rtk/            headroom/      telemetry.py
  a2a/              agui/           web/
  runner/           router.py
ui/                 cf-workers/     docs/          tests/
CLAUDE.md           voly.yaml    README.md
```

---

## CLI commands

```
voly run <task>    voly match <task>    voly compare <task>
voly savings       voly status          voly scan
voly registry agents        voly registry skills       voly skill list
voly model list             voly ai-gateway status     voly catalog sync
voly dspy status            voly memory search <query>  voly runs list
voly serve                  voly ui
voly a2a                    voly agui                 voly rtk
voly headroom               voly mcp                  voly runner
voly telemetry              voly balance              voly init
voly setup                  voly config               voly tunnel
voly spend status
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

`.env`, `.voly/events/`, `.voly/dspy/datasets/`, `.voly/dspy/programs/`,
`.voly/reports/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`,
`ui/node_modules/`, `voly/web/static/assets/`

---

## Troubleshooting

| Problem | First check |
|---|---|
| `DSPy is not installed` | `pip install -e ".[dspy]"` или `dspy.enabled: false` |
| Base install imports DSPy | Проверь top-level `import dspy` вне lazy paths |
| Pipeline bypasses gateway | Убедись что runtime использует `AIGateway.chat()` |
| Executor не пишет файлы | Проверь `--cwd` и credentials executor |
| Billing fallback не срабатывает | Детекция в `voly/ai_gateway/error_classifier.py` (`_is_billing_error` делегирует туда); rate-limit 429 НЕ считается billing — только quota-exhausted/account |
| Smart dispatch не срабатывает | Установи `VOLY_PROJECT_CWD` или `default_cwd` в `voly.yaml` |
| Wrangler executor недоступен | Запусти `cd cf-workers/agent && wrangler dev` |
| CI fails with test collection | Проверь `pyproject.toml` pytest config |
