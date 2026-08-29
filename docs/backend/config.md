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

# Explicit evaluated-pack snapshot sync — cf-workers/capability/
VOLY_CAPABILITY_WORKER_URL=https://capability.voly.codes
VOLY_CAPABILITY_SYNC_TOKEN=<worker EVALUATED_SYNC_TOKEN secret>
```

> **Token setup**: each worker reads `API_TOKEN` from its own wrangler secrets
> (Dashboard → Worker → Settings → Variables & Secrets, or `wrangler secret put API_TOKEN`).
> The value in `.env` must match. Never reuse `CLOUDFLARE_API_TOKEN` for worker auth —
> that is the account-level token with broad permissions.

The capability sync token is separate from startup profile synchronization.
It is read only for the explicit `voly capability evaluated sync` command and
must match the Worker's `EVALUATED_SYNC_TOKEN` secret. It is never written to
the snapshot, receipt, logs, `voly.yaml`, or D1.

### GitHub (reuse pipeline)

```env
GITHUB_TOKEN=ghp_...   # or GH_TOKEN — voly reuse search / pack (GitHub REST)
```

### VOLY control

```env
VOLY_PROJECT_CWD=/path/to/target/project
# default cwd for executors (or default_cwd in voly.yaml).

On Windows, npm CLIs are commonly exposed as `.cmd` wrappers. Environment
readiness detects `wrangler.cmd` on PATH and the repo-local
`cf-workers/agent/node_modules/.bin/wrangler.cmd`; install it with
`npm ci --prefix cf-workers/agent`.

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

VOLY_WORKFLOW_SDK_ENABLED=true
VOLY_WORKFLOW_SDK_MAX_PARALLEL_NODES=3
# Bounded parallel chat waves for PlanRunner/Workflow (Phase 3 of
# docs/proposals/agent-workflow-sdk.md). Executor-mode steps always run
# one at a time regardless of this setting — they share the Plan's cwd.

VOLY_SENSING_ENABLED=false
VOLY_SENSING_MODE=shadow
# Layer C business-signal polling. Disabled by default. In shadow mode,
# `voly sensing poll` stores Signals only and never creates a Plan or runs an Executor.

VOLY_RUN_POOL_WORKERS=16
# Thread pool size for POST /api/run (web/routes/run.py). Executor calls are
# I/O-bound subprocess waits, not CPU-bound, so a larger pool is cheap and
# reduces invisible queuing under concurrent requests.

VOLY_JSON_LOGS=1
# JSON-lines logs with correlation_id (web server). See docs/backend/api.md.

VOLY_EVENTS_DIR=/path/to/project/.voly/events
# Which events directory `voly mcp serve` reads runs and tasks from. Unset, it
# resolves the first existing .voly/events in cwd, then ~/.voly/events — the
# same order the web server uses. Set it when the MCP server is started from a
# different directory than the project it should report on.
# See docs/backend/mcp.md.

VOLY_ROLES=architect,developer,tester,reviewer
VOLY_MODELS=shared-model-a,shared-model-b
VOLY_MODELS_PIPELINE=claude-sonnet-4-6,gpt-4o
VOLY_MODELS_CLAUDE_CODE=claude-sonnet-4-6,claude-opus-4-8
VOLY_MODELS_CURSOR=composer-2.5
VOLY_MODELS_OPENCODE=kimi-k3,deepseek-v4-flash
VOLY_MODELS_ZEN=deepseek-v4-flash,gpt-5.6-luna,qwen3.6-plus,gpt-5.6-terra,claude-sonnet-5,gpt-5.6-sol,deepseek-v4-flash-free,mimo-v2.5-free
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
# VOLY Cloud device link (voly/cloud_link.py). Linking authenticates this
# device and enables heartbeats, but does NOT consent to run analytics.
# Prefer `voly cloud login --url <cp>` (browser confirm) over putting a
# password on the laptop — that writes `.voly/cloud.json` with device_id.

VOLY_CLOUD_ANALYTICS_ENABLED=false
# Explicit opt-in for all remote run analytics: linked Cloud run history,
# CF Pipeline and R2. Defaults false even when endpoints/credentials exist.
# Remote payloads exclude raw task/result/error text, repository paths,
# file contents, baseline excerpts/commands/notes and feedback comments.

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

### Business-signal sensing (experimental)

```yaml
sensing:
  enabled: false
  mode: shadow                 # off | shadow | active
  store_dir: .voly/signals
  min_urgency_for_decision: medium
  connectors:
    - name: rss
      feeds: ["https://example.com/feed.xml"]
      poll_interval_seconds: 900
```

Only explicit CLI polling ships in the connector phase:
`voly sensing poll --connector rss` and `voly sensing list`. There is no
background scheduler. RSS responses are bounded to 2 MiB and use a 15-second
timeout; duplicate entries are rejected by a persisted connector-derived hash.
When `dspy.enabled: true`, shadow polling also runs the registered
`signal-analyst` program and stores validated `<signal_id>.options.json` files.
`active` is accepted as staged configuration but does not create Decisions
until the Decision phase lands.

### Business executors

```yaml
business_executors:
  enabled: false
  allow: [http_call, notify]
  http:
    allowed_hosts: [api.partner.example]
    allowed_methods: [POST, PATCH]
    timeout_seconds: 15
    max_response_bytes: 1048576
```

`VOLY_BUSINESS_EXECUTORS_ENABLED` overrides the master switch. Empty host or
action allowlists deny every request. The HTTP executor accepts only explicit
JSON action specs with HTTPS, an allowlisted host/method and an idempotency key.
`notify` is the single v1 notification transport: an HTTPS webhook using the
same host allowlist, timeout, response bound, SSRF checks and idempotency rule.

### `voly cloud` — device link CLI

```bash
# Recommended — browser confirm (dashboard session), no password on the laptop:
voly cloud login --url https://cloud.voly.codes
voly cloud status
voly cloud analytics status|enable|disable
voly cloud sync [--since 30] [--limit 200]   # upload past .voly/events
voly cloud heartbeat --once                  # or leave running / use `voly ui`
voly cloud logout

# Legacy (scripts/CI only):
voly cloud login --url http://127.0.0.1:7790 --email you@example.com [--org slug]
```

`login` (default) starts a device-code session, opens `/link`, and polls until
you approve in the dashboard. The device-bound JWT is stored in
`.voly/cloud.json` (includes `device_id`). Heartbeats keep the agent **Online**
in the org dashboard. Analytics remains disabled after login until
`voly cloud analytics enable`, `cloud_analytics.enabled: true`, or
`VOLY_CLOUD_ANALYTICS_ENABLED=true`. Once opted in, `sync` backfills sanitized
runs that finished before linking.

> Ports for `voly serve` (9202) and `voly ui` (7788) are set via the `--port` flag, NOT via
> env variables. Sync of `docs ↔ .env.example ↔ code` is checked by the CI gate
> `scripts/check_env_doc_sync.py`.

---

## voly.yaml — key fields

### Evidence Foundation

```yaml
evidence:
  enabled: false
  store_dir: ".voly/evidence"
  baseline_enabled: true
  baseline_auto_commands: true
  baseline_commands: {}
  baseline_timeout_seconds: 120
  output_max_chars: 2000
  eval_policy_id: executor-basic
  eval_policy_version: "1"
```

`VOLY_EVIDENCE_ENABLED=1|0` overrides `enabled`. When enabled, file-capable
executor runs capture a build/test/lint baseline before edits and write a local
EvidenceRecord after execution. Review inferred commands before enabling this
for a large repository. See [evidence.md](evidence.md).

### Deterministic evaluation

```yaml
evaluation:
  enabled: false
  policy_id: auto
  command_timeout_seconds: 120
  llm_judge:
    mode: off
    model: ""
    provider: ""
    max_input_chars: 6000
    max_tokens: 1200
    threshold: 0.75
```

`VOLY_EVALUATION_ENABLED=1|0` overrides `enabled`. Evaluation requires local
Evidence Foundation, selects a versioned policy before execution, and replays
the exact baseline command vectors after the executor and safety stage. It is
record-only in this increment and does not change routing or the visible
executor result. `auto` selects specialized documentation, testing and security
policies from deterministic task classification; an explicit `policy_id` can
select `executor-basic`, `documentation-basic`, `testing-basic`, or
`security-basic`. See [evaluation.md](evaluation.md).

`llm_judge.mode` is `off`, `shadow`, or `required`. Both active modes send a
bounded copy of task and executor-output text through `AIGateway.chat()` to the
configured model/provider; repository source and file paths are not included.
Because that text may still be sensitive, the default is `off`. Environment
override: `VOLY_LLM_JUDGE_MODE`.

### Cloud analytics consent

```yaml
cloud_analytics:
  enabled: false
```

This is a separate fail-closed gate from `telemetry.enabled`, `cloud.enabled`,
configured Pipeline URLs and R2 credentials. Local `.voly/events` and
`.voly/evidence` continue to work while it is false; no run analytics POST/PUT
is attempted. When true, every destination receives a strict metadata
allowlist rather than serialized local records.

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

# Bounded parallel chat waves + durable resume for PlanRunner (Phase 3 of
# docs/proposals/agent-workflow-sdk.md; see docs/backend/sdk.md).
workflow_sdk:
  enabled: true              # false forces strict single-step-at-a-time regardless of Plan shape
  max_parallel_nodes: 3      # a wave is bounded to this many concurrent mode=chat steps; 1 = sequential
  checkpoint: true           # reserved — PlanRunner always persists after every step/wave already
  stale_running_seconds: 900 # a step stuck in `running` this long is recovered to `failed` on resume()

# Env overrides:
#   VOLY_WORKFLOW_SDK_ENABLED=1|0
#   VOLY_WORKFLOW_SDK_MAX_PARALLEL_NODES=<int>

# Capability Registry (executor routing + EMA scores; see docs/backend/capability.md)
capability:
  enabled: true                   # false → static BILLING_FALLBACK_CHAIN; true → score-based
  worker_url: "${VOLY_CAPABILITY_WORKER_URL}"  # CF Worker at capability.voly.codes
  profiles_dir: ".voly/capability/profiles"   # local profile cache
  worker_timeout_s: 5.0           # HTTP timeout for /match and evidence POSTs
  routing_policy: balanced        # balanced | quality_first | budget_first
  evaluated_enabled: false
  evaluated_dir: ".voly/capability/evaluated"

# Env overrides (always win over yaml when set):
#   VOLY_CAPABILITY_ENABLED=1|0
#   VOLY_CAPABILITY_WORKER_URL=https://capability.voly.codes
#   VOLY_CAPABILITY_ROUTING_POLICY=balanced|quality_first|budget_first

# Repository intelligence (see docs/backend/intelligence.md)
intelligence:
  auto: false                  # true → parse github.com URL from task when --repo unset
  max_cache_age_days: 7
  max_cache_size_mb: 500
  max_repo_size_mb: 500

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

# Offline research-first pilot; shadow output never changes routing.
research:
  enabled: false
  mode: shadow
  reports_dir: ".voly/research/reports"
  max_candidates: 8
  max_duration_ms: 1000

# Evidence-gated instincts; Phase 6 selection is shadow-only.
learning:
  enabled: false
  mode: shadow
  store_path: ".voly/learning/instincts.json"
  min_skill_confidence: 0.7

# Harness-neutral hooks; imported manifests remain disabled until approved.
hooks:
  enabled: false
  registry_path: ".voly/hooks/manifests.json"
  state_path: ".voly/hooks/idempotency.json"
  evidence_log: ".voly/hooks/evidence.jsonl"
  telemetry_log: ".voly/hooks/telemetry.jsonl"

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
  # (token needs Agent Memory permissions).
  agent_memory_account_id: "${CF_ACCOUNT_ID}"
  agent_memory_namespace: voly-prod
  agent_memory_profile_mode: project  # project | explicit
  # Used only in explicit mode. Do not share `default` across projects/tenants.
  agent_memory_profile: default
  # After each successful Pipeline/A2A model checkpoint, send one bounded
  # user/assistant pair to Agent Memory /ingest instead of duplicating /remember.
  agent_memory_checkpoint_ingest: true
  agent_memory_checkpoint_max_bytes: 32000
  strategic_compaction: false
  strategic_path: .voly/strategic-memory.jsonl
  retrieval_token_budget: 600
  retrieval_per_class_limit: 3

agents:
  cursor:
    executor: cursor
    model: claude-sonnet-4-6
  zen:
    executor: zen
    model: auto
```

### Cloudflare Agent Memory

`backend: agent_memory` keeps the local SQLite write and mirrors new entries to
Cloudflare through the Agent Memory HTTP API. Retrieval is remote-first and
falls back to local FTS when the service is unavailable or returns no memory.

Create the configured namespace once:

```bash
npx wrangler agent-memory namespace create voly-prod
# or print the command derived from voly.yaml:
voly memory agent-memory-setup
```

`namespace` separates an application/environment or memory layer. `profile`
is the isolation boundary for a project, user, team, tenant, agent, or other
entity. The default `agent_memory_profile_mode: project` derives a stable
`project-<directory>-<path-hash>` profile from the resolved `cwd`. Without
`cwd` it fails closed: no remote or local project-memory retrieval/store occurs.
The local SQLite fallback is filtered by the same profile, so a remote outage
cannot expose another project's rows.

Use `agent_memory_profile_mode: explicit` only when the caller intentionally
shares a profile (for example a team or organization). In that mode
`agent_memory_profile` is used verbatim and must fit Cloudflare's 100-character
profile-name limit.

```bash
export CF_ACCOUNT_ID=...
export CLOUDFLARE_API_TOKEN=...  # token with Agent Memory permissions
voly memory status --cwd /path/to/project
voly memory search "project architecture decisions" --cwd /path/to/project
voly memory ingest conversation.json --session-id run-123 --cwd /path/to/project
voly memory summary --session-id run-123 --cwd /path/to/project
```

`conversation.json` is either a JSON message list or
`{"sessionId":"...","messages":[...]}`. VOLY caps manual ingestion at 1 MB
and 500 messages. Automatic checkpoint ingestion runs after successful Pipeline
results and successful non-cache A2A role results. It stores the local fallback first,
then sends a bounded user/assistant pair under the task ID as Cloudflare
`sessionId`; a remote failure never fails the task. Cloudflare manages remote
retention. Deletion remains explicit through its memory, session, or profile
lifecycle API; VOLY does not silently delete remote history.

The API guardrails are enforced client-side: at most 500 messages per ingest,
32 KiB per message, and 64 bytes per session ID. Lower
`agent_memory_checkpoint_max_bytes` when prompts may contain large generated
artifacts. `strategic_compaction: true` continues to use the local typed
strategic store rather than Agent Memory. User/org multi-profile retrieval is a
separate rollout step.

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
config.evidence.enabled             # local EvidenceRecord + pre-run baseline
config.evidence.store_dir           # local generated evidence directory
config.evidence.baseline_auto_commands  # discover build/test/lint commands
config.evidence.baseline_commands   # explicit name → command overrides
config.cloud_analytics.enabled      # explicit remote-analytics consent
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
voly quickstart --check --cwd /path/to/repo  # offline, read-only readiness probe
voly quickstart --cwd /path/to/repo          # optionally create missing voly.yaml
voly quickstart --yes --cwd /path/to/repo    # non-interactive config creation
voly init              # interactively creates voly.yaml
voly setup             # checks all required keys
voly config            # shows current config
voly status            # health check of all components
```

`voly quickstart` is the preferred first-run path. It validates the repository,
inspects an existing config, detects local file-capable executors, and prints an
exact first `voly run ... --dry-run` command. `--check` and `--json` are
deterministic diagnostics: they do not write files, install packages, launch an
executor, or contact the capability registry. A missing config is not a blocker;
an invalid existing config and the absence of every supported executor are blockers.

---

## .env.example

Canonical list of all env vars — `.env.example` at the project root.
When adding a new provider — update `.env.example` and this file.
