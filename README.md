<p align="center">
  <img src="docs/assets/codeops-logo.png" alt="CodeOps" width="720">
</p>

<p align="center">
  <a href="https://github.com/codeops-org/codeops/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/codeops-org/codeops/ci.yml?branch=main&style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="DSPy" src="https://img.shields.io/badge/DSPy-Optional-22C55E?style=for-the-badge">
  <img alt="Cloudflare AI Gateway" src="https://img.shields.io/badge/Cloudflare-AI_Gateway-F38020?style=for-the-badge&logo=cloudflare&logoColor=white">
  <img alt="A2A" src="https://img.shields.io/badge/A2A-Supported-6366F1?style=for-the-badge">
  <img alt="AG-UI" src="https://img.shields.io/badge/AG--UI-Streaming-0EA5E9?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-orange?style=for-the-badge">
</p>

<p align="center">
  AI Agent Control Plane · Billing Fallback Chain · DSPy Optimization · FinOps · A2A · AG-UI · Cloudflare AI Gateway
</p>

# CodeOps — Control Plane для AI-агентов

> **CodeOps оборачивает Claude Code, Zen, Cursor, Codex и другие AI-агенты, чтобы запускать их дешевле, безопаснее и с полной измеримостью.**

CodeOps — не ещё один AI-агент. Это **control plane** между разработчиком и агентами:

- маршрутизирует задачи по executor-ам с автоматическим billing fallback chain;
- контролирует расходы через Cloudflare AI Gateway, spend limits и cost policy;
- снижает расход токенов через RTK, Headroom, cache и model routing;
- собирает telemetry по каждому запуску;
- поддерживает DSPy как optional optimization layer;
- остаётся project-agnostic — целевой проект передаётся через `--cwd` или `CODEOPS_PROJECT_CWD`.

## Как это работает

Есть два независимых пути выполнения задачи:

```text
Developer / Web UI / CLI / CI
         ↓
   CodeOps Entry Point
         ↓
    ┌────┴────┐
    │         │
    ▼         ▼
PIPELINE   EXECUTOR
  PATH       PATH
(text/     (file-
inference) capable)
    │         │
    │         ├─ DSPy TaskPlanner  (optional)
    │         ├─ executor.run(task, cwd)
    │         └─ Billing Fallback Chain:
    │              claude-code → wrangler → zen
    │
    ├─ ROUTE → MEMORY → RTK → SKILL
    ├─ HEADROOM → DSPY* → MODEL_CALL
    └─ AIGateway.chat()
         DLP → Cache → Rate limit → Spend limit → Provider
```

**`AIGateway.chat()`** — единственная точка выхода к моделям. DSPy, InferenceManager и все рантаймы идут через него. Сохраняются cache, DLP, spend limits, fallback и telemetry.

**Smart dispatch** (`POST /api/run`): когда `executor=pipeline` и задача требует генерации кода, сервер автоматически переключается на `executor=claude-code` с `cwd` из конфига или `CODEOPS_PROJECT_CWD`.

## Быстрый старт

```bash
git clone https://github.com/codeops-org/codeops.git
cd codeops
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # добавь API ключи
codeops init
codeops status
```

Запуск web UI:

```bash
codeops serve          # backend на :7860
cd ui && npm install && npm run dev   # UI на :5173
```

Для DSPy:

```bash
pip install -e ".[dspy,dev]"
codeops dspy status
```

## Billing Fallback Chain

Ключевой механизм: если у текущего executor-а кончаются деньги, `AgentRunner` автоматически переходит к следующему.

```
claude-code  →  wrangler  →  zen
(Anthropic)    (CF Workers)  (free)
```

`ExecutorResult.billing_error = True` → следующий executor в цепочке.

Все три executor-а умеют **писать файлы** в `--cwd`. Text-only executor-а (`deepseek`, `workers-ai`) в цепочку не входят.

## Executors

| Executor | Запись файлов | Billing | Позиция в цепочке |
|---|---|---|---|
| `claude-code` | да — Claude CLI | Anthropic | 1-й |
| `wrangler` | да — LocalPatchApplier | CF Workers AI | 2-й |
| `zen` | да — opencode CLI | free / subscription | 3-й (last resort) |
| `cursor` | да — Cursor Agent | Cursor | standalone |
| `opencode` | да — OpenCode CLI | opencode.ai | standalone |
| `deepseek` | нет — text only | DeepSeek API | вне цепочки |
| `mimo` | нет — text only | MiMo API | вне цепочки |

Пример запуска:

```bash
codeops run "implement auth refactor" \
  --executor claude-code \
  --cwd /path/to/target-project
```

Для автоматического выбора executor-а и routing — используй Web UI или `codeops match`.

## WranglerExecutor + CF Worker

`wrangler` executor вызывает локальный CF Workers AI через `wrangler dev`, применяет ответ к файлам через `LocalPatchApplier`.

```bash
# Запустить Worker перед использованием wrangler executor:
cd cf-workers/agent && wrangler dev
```

CF Worker (`cf-workers/agent/src/infer.ts`) маршрутизирует inference через:
1. CF AI Gateway route schema (`CF_ACCOUNT_ID` + `CF_AIG_TOKEN`) — `POST /infer`
2. `env.AI.run()` direct binding — fallback если gateway не настроен

Модель по умолчанию: `@cf/moonshotai/kimi-k2.7-code`

## Web UI

Svelte 5 SPA с hash-routing: `#/tasks`, `#/gateway`, `#/telemetry`, `#/dspy`.

| Компонент | Назначение |
|---|---|
| `RunPanel.svelte` | Запуск задачи: executor, agent, model, cwd, SSE stream |
| `RunParams.svelte` | Параметры запуска с hints по executor-ам |
| `RunResult.svelte` | Результат: content, billing_fallback badge, cost |
| `TaskSidebar.svelte` | История задач с поиском и фильтром |
| `PipelineInspector.svelte` | Стадии pipeline, token flow, DSPy metadata |
| `WorkReport.svelte` | Файлы созданные/изменённые/удалённые |
| `GatewayPage.svelte` | AI Gateway dashboard |
| `TelemetryPage.svelte` | Аналитика расходов |
| `DSPyPage.svelte` | DSPy программы и lifecycle |

`RunPanel` при загрузке автоматически подставляет `cwd` из `GET /api/status` → `default_cwd` (берётся из `CODEOPS_PROJECT_CWD` или `codeops.yaml`).

## DSPy — optional optimization layer

DSPy подключается между стадиями `HEADROOM_COMPRESS` и `AI Gateway` в pipeline, и как `TaskPlanner` перед executor-ом.

| Mode | Поведение |
|---|---|
| `off` | DSPy выключен |
| `shadow` | DSPy запускается параллельно для наблюдения; ответ — classic |
| `active` | DSPy-результат заменяет classic response для разрешённых агентов |

```bash
codeops dspy status
codeops dspy dataset build
codeops dspy compile --agent reviewer
codeops dspy promote code-review.v2 --tag production
```

## Конфигурация

```yaml
# codeops.yaml
default_agent: claude
default_cwd: ""             # путь к целевому проекту (или задай CODEOPS_PROJECT_CWD)

ai_gateway:
  provider: cloudflare
  cloudflare_account_id: "${CF_ACCOUNT_ID}"
  cloudflare_gateway_id: "${CF_GATEWAY_ID}"
  cache_enabled: true
  spend_limit_usd_per_day: 20.0

cost_policy:
  max_task_cost_usd: 2.0

dspy:
  enabled: false
  mode: shadow
```

Ключевые env vars:

```env
ANTHROPIC_API_KEY=sk-ant-...       # claude-code executor
OPENCODE_API_KEY=...               # zen / opencode executor
CF_ACCOUNT_ID=...                  # CF AI Gateway + CF Worker
CF_GATEWAY_ID=default
CF_AIG_TOKEN=...                   # от CF Dashboard → AI Gateway → Settings
CODEOPS_PROJECT_CWD=/path/to/proj  # default cwd для executor-а и UI
```

## Основные команды

```bash
codeops run <task>              # запустить задачу через pipeline
codeops run <task> --executor claude-code --cwd /path/to/project
codeops match <task>            # подобрать агента / executor / модель
codeops compare <task>          # прямой API vs CodeOps pipeline
codeops status                  # статус компонентов
codeops savings                 # отчёт об экономии
codeops serve                   # запустить backend на :7860
codeops ui                      # открыть UI в браузере

codeops registry agents         # список агентов
codeops registry skills         # список скиллов
codeops model list              # модели и цены
codeops ai-gateway status       # статус AI Gateway
codeops spend status            # текущий дневной spend
codeops dspy status             # DSPy programs + режим
```

## CI

GitHub Actions smoke gate:

- base install Python 3.10 / 3.11 / 3.12
- import smoke без DSPy extra
- DSPy extra install smoke
- `pytest tests/test_dspy_runtime_smoke.py`

```bash
pytest tests/test_dspy_runtime_smoke.py   # обязательно после изменений
pytest tests/ -q                          # полный прогон
```

## Не коммитить

```
.codeops/events/
.codeops/dspy/datasets/
.codeops/dspy/programs/
.codeops/reports/
.venv/
ui/node_modules/
codeops/web/static/assets/
```

## Документация

| Файл | Назначение |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Высокоуровневая схема: pipeline, executor, gateway |
| [docs/backend/pipeline.md](docs/backend/pipeline.md) | Pipeline стадии, AgentRouter, smart dispatch |
| [docs/backend/executors.md](docs/backend/executors.md) | Executor-ы, billing fallback chain, WranglerExecutor |
| [docs/backend/ai-gateway.md](docs/backend/ai-gateway.md) | AIGateway, CF route schema, провайдеры |
| [docs/backend/dspy.md](docs/backend/dspy.md) | DSPy programs, TaskPlanner, adapter, datasets |
| [docs/backend/config.md](docs/backend/config.md) | codeops.yaml, env vars, CodeOpsConfig |
| [docs/backend/api.md](docs/backend/api.md) | FastAPI endpoints, SSE events, CF Worker /infer |
| [docs/frontend/overview.md](docs/frontend/overview.md) | Svelte 5 стек, структура ui/, dev/build |
| [docs/frontend/components.md](docs/frontend/components.md) | Компоненты, props, executor order |
| [docs/frontend/api-client.md](docs/frontend/api-client.md) | SSE вызовы, event format, billing_fallback в UI |
| [CLAUDE.md](CLAUDE.md) | Инструкции для AI-агентов в этом репозитории |
