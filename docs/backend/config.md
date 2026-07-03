# Config & Env — Backend Reference

Конфиг загружается из `codeops.yaml` + `.env`. Класс: `codeops/config.py:VOLYConfig`.

Приоритет: `.env` > `codeops.yaml` > defaults в коде.

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
CODEOPS_PROJECT_CWD=/path/to/target/project
# Если задан — executor использует его как cwd по умолчанию.
# Можно также задать default_cwd в codeops.yaml.

CODEOPS_LOG_LEVEL=INFO
CODEOPS_SERVER_PORT=7860
CODEOPS_SERVER_HOST=0.0.0.0
```

---

## codeops.yaml — ключевые поля

```yaml
default_agent: cursor
default_cwd: ""          # path для executor по умолчанию (overrides CODEOPS_PROJECT_CWD)

ai_gateway:
  provider: cloudflare   # cloudflare | custom
  cloudflare_account_id: ""
  cloudflare_gateway_id: default
  cache_enabled: true
  cache_persist_dir: .codeops/gateway_cache  # disk-кэш ответов; пусто → только in-memory
  rate_limit_rpm: 60
  spend_limit_usd_per_day: 10.0

cost_policy:
  max_task_cost_usd: 2.0
  warn_threshold_usd: 1.0

dspy:
  enabled: false
  mode: shadow           # off | shadow | active
  model: claude-sonnet-4-6
  programs_dir: .codeops/dspy/programs
  datasets_dir: .codeops/dspy/datasets

a2a:
  enabled: true
  auto_dispatch: true          # авто мульти-агентность для сложных задач
  min_flags_for_dispatch: 2    # порог capability-флагов (code_gen/review/testing/deployment)
  execution_mode: local        # local (lead + суб-агенты in-process) | federation (remote)
  lead_model: ""               # модель lead-оркестратора; пусто → premium из здорового пула
  federation_url: ""           # только для execution_mode=federation

rtk:
  enabled: true
  auto_install: true

memory:
  enabled: true
  storage: .codeops/memory/

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
config.default_cwd           # из codeops.yaml default_cwd или CODEOPS_PROJECT_CWD
config.dspy.enabled          # bool
config.dspy.mode             # "off" | "shadow" | "active"
config.dspy.datasets_dir     # путь для сохранения (task, result) примеров
config.cost_policy.max_task_cost_usd
config.ai_gateway.spend_limit_usd_per_day
```

---

## Инициализация

```bash
codeops init              # интерактивно создаёт codeops.yaml
codeops setup             # проверяет все нужные ключи
codeops config            # показывает текущий конфиг
codeops status            # health check всех компонентов
```

---

## .env.example

Эталон всех env vars — `.env.example` в корне проекта.
При добавлении нового провайдера — обновить `.env.example` и этот файл.
