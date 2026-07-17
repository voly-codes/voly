# Config & Env — Backend Reference

Config is loaded from `voly.yaml` + `.env`. Class: `voly/config.py:VOLYConfig`.

Priority: `.env` > `voly.yaml` > defaults in code.

---

## Discovery (`voly/config/_loader.py`)

`_find_config_path`/`_load_dotenv` walk upward from the target `--cwd` (or
`Path.cwd()`) looking for `voly.yaml`/`.env`. The walk is bounded — it stops
as soon as it reaches a directory containing `.git` (the target project's own
VCS root), with a fixed `_MAX_UPWARD_LEVELS` (20) depth cap as a backstop for
`--cwd` paths outside any git repo. This matters because VOLY runs against
arbitrary external projects via `--cwd`: without a boundary, an unrelated
`voly.yaml`/`.env` (and its credentials) in an ancestor directory on a
multi-project machine would be silently picked up.

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
# Runtime: auth/billing errors in `run_local` also mark providers unhealthy for
# the rest of the process (see `ProviderHealthChecker.mark_unhealthy`).

VOLY_A2A_EXECUTOR_DEVELOPER=cursor
VOLY_A2A_EXECUTOR_BUGFIXER=deepseek
# Per-role executor override for hybrid mode=executor (see voly/a2a/hybrid.py).

VOLY_PLAN_ENABLED=true
VOLY_PLAN_MODE=active
# Plan gates (Rung B). CLI: voly plan run plan.yaml

VOLY_RUN_POOL_WORKERS=16
# Thread pool size for POST /api/run (web/routes/run.py). Executor calls are
# I/O-bound subprocess waits, not CPU-bound, so a larger pool is cheap and
# reduces invisible queuing under concurrent requests.

VOLY_CLOUD_ENABLED=true
VOLY_CLOUD_URL=http://127.0.0.1:7790
VOLY_CLOUD_TENANT_ID=...
VOLY_CLOUD_TOKEN=...
VOLY_CLOUD_USER_ID=...
# VOLY Cloud link (voly/cloud_link.py): report finished local runs into the
# org's shared history (control plane POST .../runs/report, tenant edge JWT).
# Metadata only — task text capped at 500 chars, cost, files touched; never
# file contents. Env overrides the `cloud:` yaml section; best-effort
# delivery, failures never break the run.

VOLY_CLOUD_LINK_FILE=.voly/cloud.json
# Path of the device link written by `voly cloud login` (default shown).
# Resolution order: explicit cloud: config/env → this link file. The file
# holds the tenant JWT — written 0600, never commit it (.voly/ is ignored).

VOLY_PXPIPE_ENABLED=true
VOLY_PXPIPE_PORT=47821
VOLY_PXPIPE_MODELS=claude-fable-5,gpt-5.6
VOLY_PXPIPE_AUTO_START=false
VOLY_PXPIPE_OVERRIDE_BASE_URL=false
# Optional Claude Code token-saving sidecar for the executor path only.
# When enabled and reachable, ClaudeCodeExecutor sets ANTHROPIC_BASE_URL to
# http://127.0.0.1:<port> for the claude subprocess. Existing
# ANTHROPIC_BASE_URL is preserved unless override is true.
# `voly pxpipe start` also enables local PNG dumps; task artifacts are stored
# under .voly/pxpipe/images/<task_id>/ and surfaced in the UI.
```

### `voly cloud` — device link CLI

```bash
voly cloud login --url http://127.0.0.1:7790 --email you@example.com [--org slug] [--ttl-days 30]
voly cloud status   # show linked org / token expiry
voly cloud logout   # delete the stored token
```

`login` authenticates against the control plane, picks the org (flag needed
only when you belong to several), mints a long-lived tenant edge JWT via
`POST /cloud/v1/tenants/{id}/tokens` and writes `.voly/cloud.json`. From then
on every finished run is reported to the org's shared history automatically.

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
  byok_enabled: false    # provider keys from CF Secrets Store via gateway (VOLY_BYOK env override)
  byok_providers: []     # restrict BYOK to a subset; empty = all supported

# Hosted catalog/marketplace (opt-in): CF_WORKER_CATALOG_URL /
# CF_WORKER_MARKETPLACE_URL env vars — real official URLs are pre-filled
# (commented) in .env.example; `voly setup` offers to write them.
  cache_enabled: true
  cache_persist_dir: .voly/gateway_cache  # disk cache for responses; empty → in-memory only
  rate_limit_rpm: 60
  spend_limit_usd_per_day: 10.0

executor_safety:          # guardrails for file-writing executors (git-based rollback)
  enabled: true
  dry_run: false          # run + roll back all changes, keep diff preview (CLI --dry-run overrides per call)
  protected_paths: []     # fnmatch; empty = defaults (.env*, *.pem, *.key, id_rsa*, .git/**)
  max_files_touched: 0    # 0 = unlimited; exceeding rolls back the whole run

cost_policy:
  max_task_cost_usd: 2.0
  warn_threshold_usd: 1.0

dspy:
  enabled: false
  mode: shadow           # off | shadow | active
  model: claude-sonnet-4-6
  programs_dir: .voly/dspy/programs
  datasets_dir: .voly/dspy/datasets

pxpipe:
  enabled: false
  port: 47821
  models: claude-fable-5,gpt-5.6
  auto_start: false
  override_anthropic_base_url: false
  # Executor-only token-saving proxy for Claude Code.
  # CLI: voly pxpipe start/status.

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
  task_timeout_seconds: 600    # per-role timeout (hybrid executor); watchdog uses it as base

telemetry:
  enabled: true
  events_dir: .voly/events
  runs_dir: .voly/runs          # in-flight multi-agent RunRecords (Rung A)
  watchdog_stale_factor: 2.0    # run is stale if heartbeat older than factor × task_timeout

cloud:                          # VOLY Cloud link — local runs → shared org history
  enabled: false
  base_url: ""                  # control plane, e.g. http://127.0.0.1:7790
  tenant_id: ""
  token: "${VOLY_CLOUD_TOKEN}"  # tenant edge JWT (org manifest), not a user session token
  user_id: ""                   # optional attribution in the org timeline
  timeout_seconds: 5

rtk:
  enabled: true
  auto_install: true

memory:
  enabled: true
  # local | hybrid (CF memory Worker) | agent_memory (Cloudflare Agent Memory API)
  backend: hybrid
  remote_url: "${CF_WORKER_MEMORY_URL}"
  db_path: .voly/memory.db
  # When backend: agent_memory — requires CF_ACCOUNT_ID + CLOUDFLARE_API_TOKEN
  # (token needs Agent Memory permissions; private beta).
  agent_memory_account_id: "${CF_ACCOUNT_ID}"
  agent_memory_namespace: voly
  agent_memory_profile: default

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
```

> **No auth config in open-core.** Web UI authentication (JWT/SSO), team
> dashboards, and org spend governance are commercial Team-tier features in
> the closed voly-cloud distribution — the open-core API is open, localhost
> only. See `docs/backend/api.md`.

### A2A hybrid (multi-agent → files)

| Field / env | Effect |
|---|---|
| `a2a.hybrid_code_gen` / `VOLY_A2A_HYBRID` | Enable hybrid role modes |
| `a2a.hybrid_require_cwd` | Without cwd keep all roles on chat |
| `a2a.executor_default` | Fallback executor when role has no mapping |
| `a2a.executor_roles` | Roles that prefer executor mode (default: developer, bugfixer) |
| `VOLY_A2A_EXECUTOR_<ROLE>` | Per-role executor override (e.g. `VOLY_A2A_EXECUTOR_DEVELOPER=cursor`) |

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
