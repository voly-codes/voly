<p align="center">
  <img src="docs/assets/voly-logo.png" alt="VOLY" width="720">
</p>

<p align="center">
  <a href="https://github.com/voly-codes/voly/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/voly-codes/voly/ci.yml?branch=main&style=for-the-badge"></a>
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

<p align="center">
  <a href="README.md">English</a> · <strong>Русский</strong>
</p>

# VOLY — Control Plane для AI-агентов

> **VOLY оборачивает Claude Code, Cursor, Codex, Zen и другие AI-агенты, чтобы запускать их дешевле, безопаснее и с полной измеримостью.**

VOLY — не ещё один AI-агент. Это **self-hosted control plane** между разработчиком и агентами:

- **маршрутизирует** задачи по executor-ам с автоматическим billing fallback chain;
- **дробит сложные задачи** на суб-агентов (architect → developer → tester → reviewer → devops), где сильный агент-оркестратор раздаёт каждому уровень модели и скилы;
- **страхует записи в файлы** — dry-run с превью диффа, защищённые пути, лимит на число файлов, git-откат;
- **контролирует расходы** через Cloudflare AI Gateway, spend limits и cost policy;
- **снижает расход токенов** через persistent-кэш, Headroom, model routing и детерминизм;
- **собирает telemetry** по каждому запуску и показывает реальные метрики в Web UI;
- поддерживает **DSPy** как optional optimization layer;
- остаётся **project-agnostic** — целевой проект передаётся через `--cwd` или `VOLY_PROJECT_CWD`.

## Почему VOLY, а не просто агент?

Claude Code, Cursor и Codex — отличные **исполнители**. VOLY — слой **над**
ними: он нужен, потому что ежедневная работа с агентами ставит вопросы,
на которые одиночный CLI не отвечает:

| Вопрос | Ответ VOLY |
|---|---|
| У агента кончились кредиты посреди задачи | Billing fallback chain `claude-code → wrangler → opencode → zen`, автоматически |
| Сколько реально стоил этот запуск? | `TaskEvent` на каждый запуск: стоимость, токены, ретраи, разбивка по ролям в UI |
| Сложная задача = один гигантский промпт? | Мульти-агентная декомпозиция с уровнем модели на роль; implement-роли пишут файлы, ревью — на chat |
| Безопасно ли пускать агента в файлы? | Safety policy: `--dry-run` с превью диффа, защищённые пути (`.env*`, ключи), лимит файлов, git-откат |
| Premium-модель на рутинную правку? | Cost policy + tier routing: дешёвые модели для дешёвых ролей |
| Ключи провайдеров в `.env` на каждой машине? | BYOK: ключи в Cloudflare Secrets Store, gateway подставляет их сам |

Если нужно только «написать код по промпту» — используй агента напрямую.
VOLY окупается, когда агенты становятся частью **ежедневного процесса**
и нужны экономика, контроль и отчёты.

## Демо за 3 минуты

```bash
voly init                                   # конфиг + хуки
voly run "почини редирект после логина" \
    --executor claude-code --cwd ~/my-project
# → executor пишет файлы; при billing-ошибке цепочка сама переключает
#   исполнителя; стоимость и затронутые файлы — в отчёте

voly run "отрефактори загрузку конфига" \
    --executor claude-code --cwd ~/my-project --dry-run
# → тот же запуск, но все изменения откатываются; превью диффа
#   остаётся в результате

voly ui                                     # web-дашборд на :7788
```

Сложный запрос («переделай auth, добавь тесты, сделай ревью») автоматически
уходит в мульти-агент: lead-модель раздаёт роли и тиры, implement-роли пишут
файлы через executor-ы, ревьюер остаётся на chat — в отчёте видно
роль / модель / стоимость / файлы по каждому агенту.

### Отчёт по запуску (Web UI)

Один экран для демо: задача → путь executor → затронутые файлы → cost и токены.

<p align="center">
  <img src="docs/assets/dashboard_task.png" alt="VOLY Web UI — отчёт по задаче: cost, токены, файлы" width="900">
</p>

## Open core vs Cloud

| | **voly** (этот репо, Apache-2.0) | **voly-cloud** (коммерческий) |
|---|---|---|
| Оркестрация, мульти-агент, hybrid executors | ✔ полностью | то же ядро |
| Billing fallback chain, cost policy, telemetry | ✔ полностью | то же ядро |
| Executor safety policy (dry-run, protected paths) | ✔ полностью | то же ядро |
| Локальный Web UI + CLI, self-hosted, один тенант | ✔ | — |
| BYOK в **твоём** Cloudflare-аккаунте | ✔ | managed per tenant |
| Auth / SSO / команды / аудит | — | ✔ |
| Hosted-запуски, общие дашборды расходов, org-лимиты | — | ✔ |

Открытое ядро полное и self-hosted. Платный уровень продаёт хостинг и
командную обвязку — не фичи ядра.

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
   ├─ architect → developer         claude-code → wrangler → opencode → zen
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
git clone https://github.com/voly-codes/voly.git
cd voly
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ui,dev]"
cp .env.example .env       # добавь API ключи
voly init
voly status
```

Web UI (dev):

```bash
# backend API (FastAPI) — :7788
python3 -m uvicorn voly.web.server:create_app --factory --host 127.0.0.1 --port 7788
# UI dev-сервер (Vite) — :5173, проксирует API на :7788
cd ui && npm install && npm run dev
```

Одним процессом (production, отдаёт собранный UI на :7788):

```bash
cd ui && npm run build && cd ..
voly ui
```

Pipeline-раннер для CF agent workers через туннель — отдельный сервис на `:9202`:

```bash
voly serve
```

DSPy (опционально):

```bash
pip install -e ".[dspy,dev]"
voly dspy status
```

### Auth Web UI (опционально)

По умолчанию API **открыт на localhost**. Перед выносом UI/API в сеть включите JWT:

```bash
export VOLY_AUTH_ENABLED=true
export VOLY_JWT_SECRET='long-random-secret-at-least-32-chars'
export VOLY_AUTH_USERS='admin:change-me'
```

Подробности: [docs/backend/api.md](docs/backend/api.md).

## Billing Fallback Chain (executor path)

Если у текущего executor-а кончаются деньги, `AgentRunner` автоматически переходит к следующему:

```
claude-code  →  wrangler  →  opencode  →  zen
(Anthropic)    (CF Workers)  (OpenCode)   (free / last resort)
```

`ExecutorResult.billing_error = True` → следующий executor в цепочке. Все пишут файлы в `--cwd`.

## Executors

| Executor | Запись файлов | Billing | Позиция в цепочке |
|---|---|---|---|
| `claude-code` | да — Claude CLI | Anthropic | 1-й |
| `wrangler` | да — LocalPatchApplier | CF Workers AI | 2-й |
| `opencode` | да — OpenCode CLI | opencode.ai | 3-й |
| `zen` | да — opencode CLI | free / subscription | 4-й (last resort) |
| `cursor` | да — Cursor Agent | Cursor | standalone |
| `deepseek` / `mimo` | нет — text only | API | вне цепочки |

```bash
voly run "implement auth refactor" --executor claude-code --cwd /path/to/target-project
```

Для автоматического выбора — Web UI или `voly match`.

## AI Gateway

`AIGateway.chat()` — единая точка выхода. Middleware: **DLP → Cache → Rate limit → Spend limit → Routing → Provider**.

- **Persistent cache** — ответы кэшируются на диск (`ai_gateway.cache_persist_dir`, по умолчанию `.voly/gateway_cache`), поэтому повторные запросы попадают в кэш между запросами и рестартами.
- **Spend только при успехе** — ошибки провайдера не раздувают дневной бюджет.
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
voly dspy status
voly dspy dataset build
voly dspy compile --agent reviewer
voly dspy promote code-review.v2 --tag production
```

## Конфигурация

```yaml
# voly.yaml
default_cwd: ""              # путь к целевому проекту (или VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare
  cache_enabled: true
  cache_persist_dir: .voly/gateway_cache   # disk-кэш; пусто → только in-memory
  spend_limit_usd_per_day: 20.0

a2a:
  enabled: true
  auto_dispatch: true         # авто мульти-агентность для сложных задач
  min_flags_for_dispatch: 2   # порог capability-флагов
  execution_mode: local       # local (lead + суб-агенты) | federation (remote)
  lead_model: ""              # модель lead-оркестратора; пусто → premium из пула

auth:
  enabled: false              # true + VOLY_JWT_SECRET перед сетевым доступом
  cors_origins:
    - "http://localhost:7788"
    - "http://localhost:5173"

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
VOLY_PROJECT_CWD=/path/to/proj            # default cwd для executor-а и UI
VOLY_A2A_EXCLUDE_PROVIDERS=               # напр. "anthropic" — скрыть из tier-пула
VOLY_AUTH_ENABLED=false
VOLY_JWT_SECRET=
VOLY_AUTH_USERS=admin:change-me
OMNIROUTE_BASE_URL=http://localhost:20128 # если используешь OmniRoute-адаптер
```

### BYOK — ключи провайдеров в Cloudflare (опционально)

При `ai_gateway.byok_enabled: true` ключи anthropic / openai /
google-ai-studio / deepseek хранятся в **CF Secrets Store**, gateway
подставляет их на каждый запрос — в `.env` нужен только `CF_AIG_TOKEN`.
См. `docs/backend/ai-gateway.md` § BYOK (Store Keys).

### Hosted-каталог и маркетплейс (опционально, opt-in)

Можно использовать официальный hosted-каталог скилов вместо деплоя своих
воркеров из `cf-workers/`:

```env
CF_WORKER_CATALOG_URL=https://catalog.voly.codes
CF_WORKER_MARKETPLACE_URL=https://marketplace.voly.codes
```

`voly setup` предложит записать это за тебя. Приватность: запросы каталога
пойдут на эти воркеры; без явного opt-in ничего не отправляется.

## Основные команды

```bash
voly run <task>                        # задача через pipeline (→ мульти-агент при сложности)
voly run <task> --executor claude-code --cwd /path/to/project
voly match <task>                      # подобрать агента / executor / модель
voly status                            # статус компонентов
voly savings                           # отчёт об экономии
voly ui                                # web dashboard (FastAPI + Svelte) :7788
voly serve                             # pipeline HTTP-раннер :9202

voly registry agents | skills          # реестр агентов / скилов
voly model list                        # модели и цены
voly ai-gateway status                 # статус AI Gateway
voly spend status                      # текущий дневной spend
voly dspy status                       # DSPy programs + режим
```

## CI и тесты

```bash
pytest tests/test_dspy_runtime_smoke.py     # обязательно после изменений
pytest tests/test_multiagent_smoke.py       # мульти-агент (мок-gateway)
pytest tests/test_web_auth.py               # JWT auth baseline
pytest tests/ -q                            # полный прогон
```

GitHub Actions: base install (Python 3.10–3.14), import smoke без/с DSPy, runtime smoke tests.

## Не коммитить

```
.voly/events/  .voly/dspy/  .voly/reports/  .voly/gateway_cache/
.venv/  ui/node_modules/  voly/web/static/
```

## Документация

| Файл | Назначение |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Высокоуровневая схема: pipeline, executor, gateway, A2A |
| [docs/backend/pipeline.md](docs/backend/pipeline.md) | Стадии, AgentRouter, авто мульти-агентность, smart dispatch |
| [docs/backend/executors.md](docs/backend/executors.md) | Executor-ы, billing fallback chain, WranglerExecutor |
| [docs/backend/ai-gateway.md](docs/backend/ai-gateway.md) | AIGateway, провайдеры, OmniRoute, persistent cache |
| [docs/backend/dspy.md](docs/backend/dspy.md) | DSPy programs, TaskPlanner, adapter, datasets |
| [docs/backend/config.md](docs/backend/config.md) | voly.yaml, env vars, VOLYConfig |
| [docs/backend/api.md](docs/backend/api.md) | FastAPI endpoints, SSE, JWT auth, CF Worker /infer |
| [docs/frontend/overview.md](docs/frontend/overview.md) | Svelte 5 стек, структура ui/, dev/build |
| [CLAUDE.md](CLAUDE.md) | Инструкции для AI-агентов в этом репозитории |
| [README.md](README.md) | English version of this README |

## Contributing & License

Вклад приветствуется — см. [CONTRIBUTING.md](CONTRIBUTING.md) (DCO, правила,
границы open-core). Код — под лицензией [Apache 2.0](LICENSE).
