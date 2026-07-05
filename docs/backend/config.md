# Config & Env — Backend Reference

Конфиг загружается из `voly.yaml` + `.env`. Класс: `voly/config.py:VOLYConfig`.

Приоритет: `.env` > `voly.yaml` > defaults в коде.

---

## Ключевые env vars

### Executors

```env
ANTHROPIC_API_KEY=sk-ant-...        # claude-code executor
OPENAI_API_KEY=sk-...               # openai provider
DEEPSEEK_API_KEY=sk-...             # deepseek executor/provider
CURSOR_API_KEY=...                  # cursor executor
OPENCODE_API_KEY=...                # opencode / zen executor

# Wrangler executor (CF Workers AI)
WRANGLER_DEV_URL=http://127.0.0.1:8787
WRANGLER_AI_MODEL=@cf/moonshotai/kimi-k2.7-code
WRANGLER_DEV_TOKEN=                 # optional
```

### Cloudflare

```env
CF_ACCOUNT_ID=073ae0130b7cee5e55a1ac1a335431a8
CF_GATEWAY_ID=default
CF_AIG_TOKEN=<от CF Dashboard → AI Gateway → Settings>

# R2 / D1 / Workers AI
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_D1_DATABASE_ID=...
CLOUDFLARE_R2_BUCKET=...
```

### VOLY control

```env
VOLY_PROJECT_CWD=/path/to/target/project
# cwd по умолчанию для executor-ов (или default_cwd в voly.yaml).

VOLY_A2A_TOKEN=...
# Bearer-токен для federation-запросов к A2A/agent воркерам (a2a.token).

VOLY_A2A_EXCLUDE_PROVIDERS=anthropic,openai
# Исключить провайдеров из tier-пула мульти-агента (напр. при исчерпании кредитов).
```

> Порты `voly serve` (9202) и `voly ui` (7788) задаются флагом `--port`, НЕ через
> env-переменные. Синхронизацию `docs ↔ .env.example ↔ код` проверяет CI-гейт
> `scripts/check_env_doc_sync.py`.

---

## voly.yaml — ключевые поля

```yaml
default_agent: cursor
default_cwd: ""          # path для executor по умолчанию (overrides VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare   # cloudflare | custom
  cloudflare_account_id: ""
  cloudflare_gateway_id: default
  cache_enabled: true
  cache_persist_dir: .voly/gateway_cache  # disk-кэш ответов; пусто → только in-memory
  rate_limit_rpm: 60
  spend_limit_usd_per_day: 10.0

cost_policy:
  max_task_cost_usd: 2.0
  warn_threshold_usd: 1.0

dspy:
  enabled: false
  mode: shadow           # off | shadow | active
  model: claude-sonnet-4-6
  programs_dir: .voly/dspy/programs
  datasets_dir: .voly/dspy/datasets

a2a:
  enabled: true
  auto_dispatch: true          # авто мульти-агентность для сложных задач
  min_flags_for_dispatch: 2    # порог capability-флагов (code_gen/review/testing/deployment)
  execution_mode: local        # local (lead + суб-агенты in-process) | federation (remote)
  lead_model: ""               # модель lead-оркестратора; пусто → premium из здорового пула
  federation_url: ""           # только для execution_mode=federation
  task_timeout_seconds: 120    # таймаут на роль; watchdog берёт его за базу

telemetry:
  enabled: true
  events_dir: .voly/events
  runs_dir: .voly/runs          # in-flight RunRecord'ы мульти-агента (Rung A)
  watchdog_stale_factor: 2.0    # прогон stale, если heartbeat старше factor × task_timeout

rtk:
  enabled: true
  auto_install: true

memory:
  enabled: true
  storage: .voly/memory/

agents:
  cursor:
    executor: cursor
    model: claude-sonnet-4-6
  zen:
    executor: zen
    model: auto
```

---

## VOLYConfig — важные поля

```python
config.default_cwd           # из voly.yaml default_cwd или VOLY_PROJECT_CWD
config.dspy.enabled          # bool
config.dspy.mode             # "off" | "shadow" | "active"
config.dspy.datasets_dir     # путь для сохранения (task, result) примеров
config.cost_policy.max_task_cost_usd
config.ai_gateway.spend_limit_usd_per_day
```

---

## Инициализация

```bash
voly init              # интерактивно создаёт voly.yaml
voly setup             # проверяет все нужные ключи
voly config            # показывает текущий конфиг
voly status            # health check всех компонентов
```

---

## .env.example

Эталон всех env vars — `.env.example` в корне проекта.
При добавлении нового провайдера — обновить `.env.example` и этот файл.
