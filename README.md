<p align="center">
  <img src="docs/assets/voly-logo.png" alt="VOLY" width="720">
</p>

<p align="center">
  <a href="https://github.com/VOLY-org/VOLY/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/VOLY-org/VOLY/ci.yml?branch=main&style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Multi-Agent" src="https://img.shields.io/badge/Multi--Agent-A2A-6366F1?style=for-the-badge">
  <img alt="DSPy" src="https://img.shields.io/badge/DSPy-Optional-22C55E?style=for-the-badge">
  <img alt="Cloudflare AI Gateway" src="https://img.shields.io/badge/Cloudflare-AI_Gateway-F38020?style=for-the-badge&logo=cloudflare&logoColor=white">
  <img alt="AG-UI" src="https://img.shields.io/badge/AG--UI-Streaming-0EA5E9?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-orange?style=for-the-badge">
</p>

<p align="center">
  AI Agent Control Plane · Multi-Agent Orchestration · Billing Fallback Chain · DSPy · FinOps · A2A · AG-UI · Cloudflare AI Gateway
</p>

# VOLY — Control Plane для AI-агентов

> **VOLY оборачивает Claude Code, Cursor, Codex, Zen и другие AI-агенты, чтобы запускать их дешевле, безопаснее и с полной измеримостью.**

VOLY — не ещё один AI-агент. Это **control plane** между разработчиком и агентами:

- **маршрутизирует** задачи по executor-ам с автоматическим billing fallback chain;
- **дробит сложные задачи** на суб-агентов (architect → developer → tester → reviewer → devops), где сильный агент-оркестратор раздаёт каждому уровень модели и скилы;
- **контролирует расходы** через Cloudflare AI Gateway, spend limits и cost policy;
- **снижает расход токенов** через persistent-кэш, Headroom, model routing и детерминизм;
- **собирает telemetry** по каждому запуску и показывает реальные метрики в Web UI;
- поддерживает **DSPy** как optional optimization layer;
- остаётся **project-agnostic** — целевой проект передаётся через `--cwd` или `VOLY_PROJECT_CWD`.

## Как это работает

Задача из веба/CLI/CI попадает в единую точку входа и идёт по одному из путей:

```text
Developer / Web UI / CLI / CI
              ↓
       VOLY Entry Point
              ↓
        ROUTE (анализ задачи)
        ┌─────┴───────────────────────────┐
        │                                 │
   сложная,                         простая генерация
   ≥2 capability                    кода (1 флаг)
        │                                 │
        ▼                                 ▼
  PIPELINE · MULTI-AGENT            EXECUTOR PATH
  (A2A local)                       (file-capable)
        │                                 │
  Lead-оркестратор                  executor.run(task, cwd)
   ├─ tier + skills на роль         Billing Fallback Chain:
   ├─ architect → developer         claude-code → wrangler → zen
   ├─ tester / reviewer / devops          │
   └─ каждый через AIGateway.chat()       │
        │                                 │
        └────────────┬────────────────────┘
                     ▼
              AIGateway.chat()
DLP → Cache → Rate limit → Spend limit → Provider → Telemetry
```

Текстовые (не код-генерящие) задачи проходят одиночным вызовом модели через тот же pipeline.

**`AIGateway.chat()`** — единственная точка выхода к моделям. Pipeline, суб-агенты, DSPy и все рантаймы идут через него; сохраняются cache, DLP, spend limits, fallback и telemetry.

**Smart dispatch** (`POST /api/run`, `executor=pipeline`):
- сложная многокомпонентная задача (≥ `a2a.min_flags_for_dispatch` флагов из code-gen/review/testing/deployment, либо `complexity=high`) → **остаётся в pipeline и уходит в мульти-агента**;
- простая код-задача → промоут в `executor=claude-code` с `cwd` из конфига/`VOLY_PROJECT_CWD` (чтобы реально писать файлы);
- текстовая задача → одиночный вызов модели.

## Мульти-агентная оркестрация (A2A local)

Когда задача уходит в мульти-агента (`a2a.execution_mode=local`, по умолчанию):

1. **`TaskDecomposer`** разбивает задачу на роли с зависимостями (architect → developer → tester → reviewer → devops).
2. **Lead-оркестратор** — сильная (premium) модель оценивает задачу и назначает каждой роли **тир модели** (`premium | standard | cheap`) и **скилы** из registry. При сбое LLM-lead — детерминированный fallback.
3. Тир → конкретная `(model, provider)` из **реального пула**, отфильтрованного `ProviderHealthChecker`:
   - **strong**: `anthropic`, `cloudflare-dynamic`
   - **weak/cheap**: `workers-ai`, `deepseek`, `opencode-zen`, `mimo`, `omniroute`
4. Суб-агенты исполняются **в процессе** через `AIGateway.chat()` в порядке зависимостей; результаты предыдущих ролей прокидываются дальше.
5. Merge → `TaskEvent` с `a2a_assignments` (роль / тир / модель / скилы / токены / стоимость / cache_hit). Всё видно в Web UI (панель «Мульти-агенты»).

**Экономия на повторах:** суб-агенты детерминированы (`temperature=0`), а gateway-кэш **persistent** (на диск) — идентичная задача на повторе даёт cache-hit по всей цепочке (стоимость → $0). Пропуск провайдера (например при исчерпании кредитов): `VOLY_A2A_EXCLUDE_PROVIDERS=anthropic`.

## Быстрый старт

```bash
git clone https://github.com/VOLY-org/VOLY.git
cd VOLY
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ui,dev]"
cp .env.example .env       # добавь API ключи
VOLY init
VOLY status
```

Web UI (dev):

```bash
# backend API (FastAPI) — :7788
python3 -m uvicorn VOLY.web.server:create_app --factory --host 127.0.0.1 --port 7788
# UI dev-сервер (Vite) — :5173, проксирует API на :7788
cd ui && npm install && npm run dev
```

Одним процессом (production, отдаёт собранный UI на :7788):

```bash
cd ui && npm run build && cd ..
VOLY ui
```

Pipeline-раннер для CF agent workers через туннель — отдельный сервис на `:9202`:

```bash
VOLY serve
```

DSPy (опционально):

```bash
pip install -e ".[dspy,dev]"
VOLY dspy status
```

## Billing Fallback Chain (executor path)

Если у текущего executor-а кончаются деньги, `AgentRunner` автоматически переходит к следующему:

```
claude-code  →  wrangler  →  zen
(Anthropic)    (CF Workers)  (free)
```

`ExecutorResult.billing_error = True` → следующий executor в цепочке. Все три пишут файлы в `--cwd`.

## Executors

| Executor | Запись файлов | Billing | Позиция в цепочке |
|---|---|---|---|
| `claude-code` | да — Claude CLI | Anthropic | 1-й |
| `wrangler` | да — LocalPatchApplier | CF Workers AI | 2-й |
| `zen` | да — opencode CLI | free / subscription | 3-й (last resort) |
| `cursor` | да — Cursor Agent | Cursor | standalone |
| `opencode` | да — OpenCode CLI | opencode.ai | standalone |
| `deepseek` / `mimo` | нет — text only | API | вне цепочки |

```bash
VOLY run "implement auth refactor" --executor claude-code --cwd /path/to/target-project
```

Для автоматического выбора — Web UI или `VOLY match`.

## AI Gateway

`AIGateway.chat()` — единая точка выхода. Middleware: **DLP → Cache → Rate limit → Spend limit → Routing → Provider**.

- **Persistent cache** — ответы кэшируются на диск (`ai_gateway.cache_persist_dir`, по умолчанию `.VOLY/gateway_cache`), поэтому повторные запросы попадают в кэш между запросами и рестартами.
- **Провайдеры**: `anthropic`, `openai`, `google`, `deepseek`, `workers-ai`, `cloudflare-dynamic`, `opencode-zen`, `mimo`, **`omniroute`** (self-hosted OpenAI-совместимый шлюз, opt-in).
- **Метрики Gateway-вкладки** берутся из телеметрии (реальные запросы/токены/стоимость/`by_provider`/`by_model`/`spent_today`), а не из свежего инстанса.

CF Worker (`cf-workers/agent/src/infer.ts`) маршрутизирует inference через CF AI Gateway route schema (`CF_ACCOUNT_ID` + `CF_AIG_TOKEN`, `POST /infer`) или `env.AI.run()` fallback.

## Web UI

Svelte 5 SPA с hash-routing: `#/tasks`, `#/gateway`, `#/telemetry`, `#/dspy` + шторки Cloudflare и Skill Marketplace.

| Компонент | Назначение |
|---|---|
| `RunPanel` / `RunParams` | Запуск задачи (executor, agent, model, cwd), SSE-стрим |
| `RunResult` | Результат: content, billing chain, **панель «Мульти-агенты»** (роль/тир/модель/скилы/cached) |
| `PipelineInspector` | Стадии pipeline, token flow, назначения суб-агентов, память, DSPy |
| `GatewayPage` | Кэш/rate/spend/fallback/DLP + блоки «По провайдерам / По моделям / состояние ключей» |
| `TelemetryPage` | Аналитика расходов (daily, by_agent, by_model) |
| `DSPyPage` | DSPy программы и lifecycle |
| `CFPage` / `MarketplacePage` | Cloudflare воркеры + spend · каталог скилов |

## DSPy — optional optimization layer

| Mode | Поведение |
|---|---|
| `off` | DSPy выключен |
| `shadow` | запускается параллельно для наблюдения; ответ — classic |
| `active` | DSPy-результат заменяет classic для разрешённых агентов |

```bash
VOLY dspy status
VOLY dspy dataset build
VOLY dspy compile --agent reviewer
VOLY dspy promote code-review.v2 --tag production
```

## Конфигурация

```yaml
# VOLY.yaml
default_cwd: ""              # путь к целевому проекту (или VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare
  cache_enabled: true
  cache_persist_dir: .VOLY/gateway_cache   # disk-кэш; пусто → только in-memory
  spend_limit_usd_per_day: 20.0

a2a:
  enabled: true
  auto_dispatch: true         # авто мульти-агентность для сложных задач
  min_flags_for_dispatch: 2   # порог capability-флагов
  execution_mode: local       # local (lead + суб-агенты) | federation (remote)
  lead_model: ""              # модель lead-оркестратора; пусто → premium из пула

cost_policy:
  max_task_cost_usd: 2.0

dspy:
  enabled: false
  mode: shadow
```

Ключевые env vars:

```env
ANTHROPIC_API_KEY=sk-ant-...              # claude-code / premium tier
OPENCODE_API_KEY=...                      # zen / opencode-zen
CLOUDFLARE_ACCOUNT_ID=...                 # CF AI Gateway + Workers AI
CLOUDFLARE_API_TOKEN=...
CF_AIG_TOKEN=...                          # CF Dashboard → AI Gateway → Settings
VOLY_PROJECT_CWD=/path/to/proj         # default cwd для executor-а и UI
VOLY_A2A_EXCLUDE_PROVIDERS=            # напр. "anthropic" — скрыть из tier-пула
OMNIROUTE_BASE_URL=http://localhost:20128 # если используешь OmniRoute-адаптер
```

## Основные команды

```bash
VOLY run <task>                        # задача через pipeline (→ мульти-агент при сложности)
VOLY run <task> --executor claude-code --cwd /path/to/project
VOLY match <task>                      # подобрать агента / executor / модель
VOLY status                            # статус компонентов
VOLY savings                           # отчёт об экономии
VOLY ui                                # web dashboard (FastAPI + Svelte) :7788
VOLY serve                             # pipeline HTTP-раннер :9202

VOLY registry agents | skills          # реестр агентов / скилов
VOLY model list                        # модели и цены
VOLY ai-gateway status                 # статус AI Gateway
VOLY spend status                      # текущий дневной spend
VOLY dspy status                       # DSPy programs + режим
```

## CI и тесты

```bash
pytest tests/test_dspy_runtime_smoke.py     # обязательно после изменений
pytest tests/test_multiagent_smoke.py       # мульти-агент (мок-gateway)
pytest tests/ -q                            # полный прогон
```

GitHub Actions: base install (Python 3.10–3.14), import smoke без/с DSPy, runtime smoke tests.

## Не коммитить

```
.VOLY/events/  .VOLY/dspy/  .VOLY/reports/  .VOLY/gateway_cache/
.venv/  ui/node_modules/  VOLY/web/static/
```

## Документация

| Файл | Назначение |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Высокоуровневая схема: pipeline, executor, gateway, A2A |
| [docs/backend/pipeline.md](docs/backend/pipeline.md) | Стадии, AgentRouter, авто мульти-агентность, smart dispatch |
| [docs/backend/executors.md](docs/backend/executors.md) | Executor-ы, billing fallback chain, WranglerExecutor |
| [docs/backend/ai-gateway.md](docs/backend/ai-gateway.md) | AIGateway, провайдеры, OmniRoute, persistent cache |
| [docs/backend/dspy.md](docs/backend/dspy.md) | DSPy programs, TaskPlanner, adapter, datasets |
| [docs/backend/config.md](docs/backend/config.md) | VOLY.yaml, env vars, VOLYConfig |
| [docs/backend/api.md](docs/backend/api.md) | FastAPI endpoints, SSE events, CF Worker /infer |
| [docs/frontend/overview.md](docs/frontend/overview.md) | Svelte 5 стек, структура ui/, dev/build |
| [CLAUDE.md](CLAUDE.md) | Инструкции для AI-агентов в этом репозитории |
