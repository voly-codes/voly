# Config & Env — Backend Reference

Config is loaded from `voly.yaml` + `.env`. Class: `voly/config.py:VOLYConfig`.

Priority: `.env` > `voly.yaml` > defaults in code.

---

## Key env vars

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
CF_AIG_TOKEN=<from CF Dashboard → AI Gateway → Settings>

# R2 / D1 / Workers AI
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_D1_DATABASE_ID=...
CLOUDFLARE_R2_BUCKET=...
```

### VOLY control

```env
VOLY_PROJECT_CWD=/path/to/target/project
# default cwd for executors (or default_cwd in voly.yaml).

VOLY_A2A_TOKEN=...
# Bearer token for federation requests to A2A/agent workers (a2a.token).

VOLY_A2A_EXCLUDE_PROVIDERS=anthropic,openai
# Exclude providers from the multi-agent tier pool (e.g. when credits are exhausted).

VOLY_PLAN_ENABLED=true
VOLY_PLAN_MODE=active
# Plan gates (Rung B). CLI: voly plan run plan.yaml
```

> Ports for `voly serve` (9202) and `voly ui` (7788) are set via the `--port` flag, NOT via
> env variables. Sync of `docs ↔ .env.example ↔ code` is checked by the CI gate
> `scripts/check_env_doc_sync.py`.

---

## voly.yaml — key fields

```yaml
default_agent: cursor
default_cwd: ""          # default path for executor (overrides VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare   # cloudflare | custom
  cloudflare_account_id: ""
  cloudflare_gateway_id: default
  upstream: ""           # "omniroute" → delegate non-CF routing to external gateway
  upstream_model: ""     # "auto" = auto-combo OmniRoute; "" = passthrough caller's model
  upstream_fallback_direct: true  # if upstream unavailable — direct provider adapter
  cache_enabled: true
  cache_persist_dir: .voly/gateway_cache  # disk cache for responses; empty → in-memory only
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

plan:
  enabled: false
  mode: shadow           # off | shadow | active (hard gates)
  store_dir: .voly/plans
  max_step_retries: 1
  default_on_verify_fail: stop  # stop | retry | continue
  command_timeout_seconds: 120
  allow_skip: false
  executor_default: claude-code
  step_timeout_seconds: 300
  max_turns: 30
  a2a_attach: true                 # wire gates into multi-agent when enabled
  chat_require_output: true        # chat roles: output_nonempty acceptance
  executor_require_git_diff: false # opt-in git_diff_nonempty for executor roles
  tester_command: ""               # e.g. "pytest -q" for tester role

a2a:
  enabled: true
  auto_dispatch: true          # auto multi-agent for complex tasks
  min_flags_for_dispatch: 2    # capability-flag threshold (code_gen/review/testing/deployment)
  execution_mode: local        # local (lead + sub-agents in-process) | federation (remote)
  lead_model: ""               # lead orchestrator model; empty → premium from healthy pool
  federation_url: ""           # only for execution_mode=federation
  task_timeout_seconds: 120    # per-role timeout; watchdog uses it as base

telemetry:
  enabled: true
  events_dir: .voly/events
  runs_dir: .voly/runs          # in-flight multi-agent RunRecords (Rung A)
  watchdog_stale_factor: 2.0    # run is stale if heartbeat older than factor × task_timeout

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

## VOLYConfig — important fields

```python
config.default_cwd           # from voly.yaml default_cwd or VOLY_PROJECT_CWD
config.dspy.enabled          # bool
config.dspy.mode             # "off" | "shadow" | "active"
config.dspy.datasets_dir     # path for saving (task, result) examples
config.plan.enabled          # bool — plan gates subsystem
config.plan.mode             # "off" | "shadow" | "active"
config.plan.store_dir        # .voly/plans
config.cost_policy.max_task_cost_usd
config.ai_gateway.spend_limit_usd_per_day
config.auth.enabled          # bool — Web UI auth (default False)
config.auth.provider         # "local" | "clerk"
config.auth.jwt_secret       # VOLY_JWT_SECRET (local)
config.auth.users            # {username: password} or VOLY_AUTH_USERS (local)
config.auth.clerk_*          # publishable_key, jwks_url, issuer (clerk)
config.auth.cors_origins     # list[str]; avoid ["*"] when auth is on
```

### Auth env overrides

| Env | Effect |
|---|---|
| `VOLY_AUTH_ENABLED` | `true`/`false` |
| `VOLY_AUTH_PROVIDER` | `local` (open-core default) \| `clerk` (optional SSO) |
| `VOLY_JWT_SECRET` | local JWT HMAC secret |
| `VOLY_AUTH_USERS` | `user:pass,user2:pass2` |
| `VOLY_AUTH_CORS` | comma-separated origins |
| `CLERK_*` | optional SSO only — not required for core (see api.md) |

### A2A hybrid (multi-agent → files)

| Field / env | Effect |
|---|---|
| `a2a.hybrid_code_gen` / `VOLY_A2A_HYBRID` | Enable hybrid role modes |
| `a2a.hybrid_require_cwd` | Without cwd keep all roles on chat |
| `a2a.executor_default` | First executor for implement roles |
| `a2a.executor_roles` | Roles that prefer executor mode |

See `docs/proposals/hybrid-multiagent-executor.md` and `docs/backend/pipeline.md`.

---

## Initialization

```bash
voly init              # interactively creates voly.yaml
voly setup             # checks all required keys
voly config            # shows current config
voly status            # health check of all components
```

---

## .env.example

Canonical list of all env vars — `.env.example` at the project root.
When adding a new provider — update `.env.example` and this file.
