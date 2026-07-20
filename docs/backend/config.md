# Config & Env — Backend Reference

Config is loaded from `voly.yaml` + `.env`. Class: `voly/config/_types.py:VOLYConfig`
(package `voly/config/`: `_types.py` dataclasses, `_parser.py` yaml parsing,
`_loader.py` discovery, `_defaults.py`, `_template.py`).

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

### CF Workers (optional hosted services)

```env
# Telemetry ingest — cf-workers/telemetry/ (POST /events)
CF_PIPELINE_TELEMETRY_ENDPOINT=https://telemetry.voly.codes/events
CF_PIPELINE_TELEMETRY_TOKEN=<worker API_TOKEN secret>

# Spend tracker + AGUI sessions — cf-workers/spend/
CF_WORKER_SPEND_URL=https://spend.voly.codes
CF_WORKER_SPEND_TOKEN=<worker API_TOKEN secret>  # must match wrangler secret API_TOKEN
CF_WORKER_AGUI_URL=https://spend.voly.codes      # AGUI uses /agui/* on the same worker

# Memory store — cf-workers/memory/
CF_WORKER_MEMORY_URL=https://memory.voly.codes
CF_WORKER_MEMORY_TOKEN=<worker API_TOKEN secret> # must match wrangler secret API_TOKEN

# A2A federation — cf-workers/a2a/
CF_WORKER_A2A_URL=https://a2a.voly.codes
```

> **Token setup**: each worker reads `API_TOKEN` from its own wrangler secrets
> (Dashboard → Worker → Settings → Variables & Secrets, or `wrangler secret put API_TOKEN`).
> The value in `.env` must match. Never reuse `CLOUDFLARE_API_TOKEN` for worker auth —
> that is the account-level token with broad permissions.

### GitHub (reuse pipeline)

```env
GITHUB_TOKEN=ghp_...   # or GH_TOKEN — voly reuse search / pack (GitHub REST)
```

### VOLY control

```env
VOLY_PROJECT_CWD=/path/to/target/project
# default cwd for executors (or default_cwd in voly.yaml).

VOLY_A2A_TOKEN=...
# Bearer token for federation requests to A2A/agent workers (a2a.token).

VOLY_A2A_EXCLUDE_PROVIDERS=anthropic,openai
# Exclude providers from the multi-agent tier pool (e.g. when credits are exhausted).
# Applied before the first chat call (mark_unhealthy) and on every tier resolve.
# Runtime auth/billing errors in `run_local` also mark providers unhealthy (TTL).

VOLY_PROVIDER_EXCLUDE_TTL=3600
# Seconds to keep a provider unhealthy after auth/billing errors (`0` = forever).
# See docs/backend/ai-gateway.md.

VOLY_A2A_EXECUTOR_DEVELOPER=cursor
VOLY_A2A_EXECUTOR_BUGFIXER=deepseek
VOLY_A2A_EXECUTOR_TESTER=cursor
VOLY_A2A_EXECUTOR_DEVOPS=cursor
# Per-role executor override for hybrid mode=executor (see voly/a2a/hybrid.py).

VOLY_ARCHITECT_MODEL=kimi-k3
# OpenCode Go model selected for architecture routing. This overrides the
# built-in architecture model when the provider's roster changes.

VOLY_PLAN_ENABLED=true
VOLY_PLAN_MODE=active
# Plan gates (Rung B). CLI: voly plan run plan.yaml

VOLY_RUN_POOL_WORKERS=16
# Thread pool size for POST /api/run (web/routes/run.py). Executor calls are
# I/O-bound subprocess waits, not CPU-bound, so a larger pool is cheap and
# reduces invisible queuing under concurrent requests.

VOLY_JSON_LOGS=1
# JSON-lines logs with correlation_id (web server). See docs/backend/api.md.

VOLY_ROLES=architect,developer,tester,reviewer
VOLY_MODELS=shared-model-a,shared-model-b
VOLY_MODELS_PIPELINE=claude-sonnet-4-6,gpt-4o
VOLY_MODELS_CLAUDE_CODE=claude-sonnet-4-6,claude-opus-4-8
VOLY_MODELS_CURSOR=composer-2.5
VOLY_MODELS_OPENCODE=kimi-k3,deepseek-v4-flash
VOLY_MODELS_ZEN=mimo-v2.5-free,deepseek-v4-flash-free
VOLY_MODELS_DEEPSEEK=deepseek-chat,deepseek-reasoner
VOLY_MODELS_MIMO=mimo-v2.5-free
VOLY_MODELS_WRANGLER=@cf/moonshotai/kimi-k2.7-code
VOLY_MODELS_WORKERS_AI=@cf/meta/llama-4-scout-17b-16e-instruct
VOLY_MODELS_CLOUDFLARE_DYNAMIC=dynamic/ai_route
# Comma-separated Web UI dropdown values. Executor-specific model variables
# take priority over VOLY_MODELS. Executor IDs are uppercased and non-alphanumeric
# characters become underscores, so a custom `my-agent` executor uses the same
# `VOLY_MODELS_<EXECUTOR>` pattern. If no env list is present, the API uses the runtime
# agent registry / telemetry model catalog. An explicitly empty variable returns
# an empty list.

VOLY_CF_CONTAINERS_URL=http://127.0.0.1:8791
VOLY_CF_CONTAINERS_TOKEN=
VOLY_CF_CONTAINERS_MODE=probe
VOLY_CF_CONTAINERS_REPO=
# Optional CF Containers executor (PoC). See docs/backend/executors.md.

VOLY_CLOUD_ENABLED=true
VOLY_CLOUD_URL=http://127.0.0.1:7790
VOLY_CLOUD_TENANT_ID=...
VOLY_CLOUD_TOKEN=...
VOLY_CLOUD_USER_ID=...
VOLY_CLOUD_DEVICE_ID=...
# VOLY Cloud link (voly/cloud_link.py): report finished local runs into the
# org's shared history (control plane POST .../runs/report, device-bound
# tenant edge JWT). Metadata only — task text capped at 500 chars, cost,
# files touched; never file contents. Env overrides the `cloud:` yaml
# section; best-effort delivery, failures never break the run.
# Prefer `voly cloud login --url <cp>` (browser confirm) over putting a
# password on the laptop — that writes `.voly/cloud.json` with device_id.

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
# Recommended — browser confirm (dashboard session), no password on the laptop:
voly cloud login --url https://cloud.voly.codes
voly cloud status
voly cloud sync [--since 30] [--limit 200]   # upload past .voly/events
voly cloud heartbeat --once                  # or leave running / use `voly ui`
voly cloud logout

# Legacy (scripts/CI only):
voly cloud login --url http://127.0.0.1:7790 --email you@example.com [--org slug]
```

`login` (default) starts a device-code session, opens `/link`, and polls until
you approve in the dashboard. The device-bound JWT is stored in
`.voly/cloud.json` (includes `device_id`). Heartbeats keep the agent **Online**
in the org dashboard; `sync` backfills runs that finished before linking.

> Ports for `voly serve` (9202) and `voly ui` (7788) are set via the `--port` flag, NOT via
> env variables. Sync of `docs ↔ .env.example ↔ code` is checked by the CI gate
> `scripts/check_env_doc_sync.py`.

---

## voly.yaml — key fields

```yaml
default_model: kimi-k3
default_agent: kimi
default_cwd: ""          # default path for executor (overrides VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare   # cloudflare | custom
  cloudflare_account_id: ""
  cloudflare_gateway_id: default
  request_timeout_seconds: 15       # stall / legacy single budget
  request_total_timeout_seconds: 60 # full response budget (slow live models)
  upstream: ""           # "omniroute" → delegate non-CF routing to external gateway
  upstream_model: ""     # "auto" = auto-combo OmniRoute; "" = passthrough caller's model
  upstream_fallback_direct: true  # if upstream unavailable — direct provider adapter
  byok_enabled: false    # provider keys from CF Secrets Store via gateway (VOLY_BYOK env override)
  byok_providers: []     # restrict BYOK to a subset; empty = all supported

# Hosted catalog/marketplace (opt-in): CF_WORKER_CATALOG_URL /
# CF_WORKER_MARKETPLACE_URL env vars — real official URLs are pre-filled
# (commented) in .env.example; `voly setup` offers to write them.
# Spend Worker: CF_WORKER_SPEND_URL + CF_WORKER_SPEND_TOKEN (must match the
# worker wrangler secret API_TOKEN — never reuse CLOUDFLARE_API_TOKEN).
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
  enabled: true          # code default is false; repo voly.yaml enables shadow gates
  mode: shadow           # off | shadow | active (hard gates)
  store_dir: .voly/plans
  max_step_retries: 1
  default_on_verify_fail: stop  # stop | retry | continue
  command_timeout_seconds: 120  # pip install -e . + pytest on greenfield projects can exceed 60s
  allow_skip: false
  executor_default: claude-code
  step_timeout_seconds: 300
  max_turns: 30
  a2a_attach: true                 # wire gates into multi-agent when enabled
  chat_require_output: true        # chat roles: output_nonempty acceptance
  executor_require_git_diff: false # opt-in git_diff_nonempty for executor roles (repo voly.yaml: true)
  executor_file_line_limit: 300    # changed text files above this fail verify
  architect_approved_file_line_limit: 500 # strict architect marker may raise cap
  tester_command: ""               # e.g. "pytest -q" for tester role
  # Extra basenames / path prefixes to skip in file_line_limit checks, on top of
  # built-in exclusions (package-lock.json, poetry.lock, node_modules/, …).
  file_line_limit_exclude_patterns: []

# Capability Registry (executor routing + EMA scores; see docs/backend/capability.md)
capability:
  enabled: true                   # false → static BILLING_FALLBACK_CHAIN; true → score-based
  worker_url: "${VOLY_CAPABILITY_WORKER_URL}"  # CF Worker at capability.voly.codes
  profiles_dir: ".voly/capability/profiles"   # local profile cache
  worker_timeout_s: 5.0           # HTTP timeout for /match and evidence POSTs

# Env overrides (always win over yaml when set):
#   VOLY_CAPABILITY_ENABLED=1|0
#   VOLY_CAPABILITY_WORKER_URL=https://capability.voly.codes

# Code reuse: GitHub search → clone → pack → pick → apply (see docs/backend/reuse.md)
reuse:
  enabled: true
  cache_dir: ".voly/reuse/cache"
  reports_dir: ".voly/reuse/reports"
  max_repos: 5
  min_stars: 20
  allowed_licenses: [mit, apache-2.0, bsd-2-clause, bsd-3-clause, isc, 0bsd, unlicense]
  deny_licenses: [gpl-2.0, gpl-3.0, agpl-3.0]
  pack_max_chars: 80000
  apply_dest: "vendor/reuse"
  auto: false                  # must be parsed (ReuseConfig.auto); repo voly.yaml sets true
  auto_max_repos: 3            # smaller limit in auto mode to keep latency low
  auto_max_age_seconds: 604800 # skip only if a fresh report has ≥1 license-allowed candidate
  # Requires GITHUB_TOKEN or GH_TOKEN for search rate limits.
  # CLI: voly reuse search|pack|pick|apply|run

a2a:
  enabled: true
  auto_dispatch: true          # auto multi-agent for complex tasks
  min_flags_for_dispatch: 2    # capability-flag threshold (code_gen/review/testing/deployment)
  execution_mode: local        # local (lead + sub-agents in-process) | federation (remote)
  lead_model: ""               # lead orchestrator model; empty → premium from healthy pool
  lead_mode: auto              # auto (LLM lead only for non-standard decompositions) |
                               # llm (always) | deterministic (never — role→tier map)
  federation_url: ""           # only for execution_mode=federation
  task_timeout_seconds: 600    # per-role timeout (hybrid executor); watchdog uses it as base
  architect_max_tokens: 4096   # plan-only architect chat budget
  # Empty executor_roles → developer, bugfixer, tester, devops
  executor_roles: []
  parallel_waves: true         # independent roles run in dependency waves; a wave's
                               # chat calls execute concurrently (executors stay serial)
  max_parallel_roles: 3        # thread cap for one wave's chat calls; 1 → sequential

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
config.default_cwd               # from voly.yaml default_cwd or VOLY_PROJECT_CWD
config.dspy.enabled              # bool
config.dspy.mode                 # "off" | "shadow" | "active"
config.dspy.datasets_dir         # path for saving (task, result) examples
config.plan.enabled              # bool — plan gates subsystem
config.plan.mode                 # "off" | "shadow" | "active"
config.plan.store_dir            # .voly/plans
config.cost_policy.max_task_cost_usd
config.ai_gateway.spend_limit_usd_per_day
config.capability.enabled        # bool — capability-aware fallback chain
config.capability.worker_url     # CF Worker URL (VOLY_CAPABILITY_WORKER_URL)
config.capability.profiles_dir   # local profile cache path
config.capability.worker_timeout_s  # HTTP timeout for capability Worker calls
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
| `a2a.executor_default` | Overrides the built-in per-role map when set to any value other than `"claude-code"`. Per-role env still wins. Built-in map: developer/tester/devops→`cursor`, bugfixer→`deepseek`. |
| `a2a.executor_roles` | Roles that prefer executor mode (empty → developer, bugfixer, tester, devops) |
| `a2a.architect_max_tokens` | Architect chat budget (default 4096) |
| `VOLY_A2A_EXECUTOR_<ROLE>` | Per-role executor override (highest priority). E.g. `VOLY_A2A_EXECUTOR_DEVELOPER=wrangler` |

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
