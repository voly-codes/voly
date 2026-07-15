# Gateway and executors

This page explains how VOLY talks to models and how it executes file-writing work.

## AI Gateway

`voly/ai_gateway/gateway.py` is the central model-routing layer. Its `chat()` method applies the middleware stack in this order:

1. DLP checks
2. Cache lookup
3. Rate limiting
4. Spend limiting (pre-call budget check)
5. Routing
6. Provider execution
7. Empty-content guard
8. **Spend recording** (post-call, success only)

The gateway can either call Cloudflare AI Gateway for CF-native providers or delegate to direct adapters. It also supports an upstream delegation mode (layer-A make-vs-delegate): a single upstream such as OmniRoute can own provider selection, with direct adapters retained as fallback.

### Spend accounting

After a provider call:

- **Success** (`error` absent): `spend_limit.record(...)` runs. Prefer usage-based cost when token usage is present; otherwise use the pre-call estimate.
- **Failure** (provider error, empty-content failure after fallbacks, etc.): spend is **not** recorded, so failed calls do not inflate the daily budget or trigger false `spend_limited` blocks.

Pre-call `spend_limit.check(estimated_cost)` still gates whether the call is attempted at all.

### Other gateway behaviors

- Cache keys can be scoped to project state (risk R1 — `cache_scope` / project fingerprint)
- Empty HTTP 200 responses become synthetic errors and enter model fallback
- Metrics track requests, cache hits, and fallbacks
- The gateway is the canonical place to add provider support and cost rates (`_COST_RATES` in `voly/telemetry.py`)

Canonical detail: `docs/backend/ai-gateway.md`.

## Executors

`voly/runner/agent_runner.py` is the file-capable execution path. It resolves executors, optionally refines the task with DSPy, executes the backend, and applies **billing fallback** when an executor signals a billing error.

The fallback chain in code (`BILLING_FALLBACK_CHAIN`) is:

`claude-code → wrangler → opencode → zen`

Only file-writing executors belong on that chain. Text-only providers such as `deepseek` and `mimo` are excluded.

### Cloudflare Containers (`cf-containers`)

Opt-in cloud-native executor (`voly/executor/cf_containers.py`). It talks HTTP to the hosted/local sandbox Worker (`GET /health`, `POST /runs`) — typically `voly-cloud/cf-workers/sandbox-spike`.

Env: `VOLY_CF_CONTAINERS_URL`, `VOLY_CF_CONTAINERS_TOKEN`, `VOLY_CF_CONTAINERS_MODE` (`probe` | `claude-code`).

Not on the billing fallback chain. UI picker label: **CF Containers (sandbox)**. Stub mode (`FORCE_STUB=1`) validates JWT without Docker; real Containers need Workers Paid + Docker (local Containers `wrangler dev` is unsupported on Windows — deploy or WSL).

Canonical detail: `docs/backend/executors.md`. Marketplace draft skill: `docs/marketplace/skills/skill-cf-containers.yaml`.

### Executor diagnostics

Failed runs surface structured fields (`error`, `error_class`, `error_hint`) via `format_executor_failure()` / `executor_failure_details()` in CLI, SSE `done`, and telemetry.

### File patching

`voly/executor/patch.py` is used by the Wrangler path to apply FILE blocks or unified diffs to the target project. It is intentionally defensive about path traversal.

## Why this split exists

Model routing is separated from file writes so the pipeline gets centralized caching, DLP, and spend controls, while executors remain responsible for touching the target project's filesystem.

## What to watch when changing gateway or executors

- Update gateway docs and config docs when provider names, spend behavior, or fallback change.
- Keep billing-error classification aligned with executor tests.
- Preserve the rule that text-only providers are not file-writing executors.
- When adding a provider, update gateway routing, cost accounting, and configuration defaults together.
- Do not charge spend on error responses.

## Useful source files

- `voly/ai_gateway/gateway.py`
- `voly/ai_gateway/error_classifier.py`
- `voly/ai_gateway/models.py` (`SpendLimit`)
- `voly/runner/agent_runner.py`
- `voly/executor/base.py`
- `voly/executor/cf_containers.py`
- `voly/executor/patch.py`
- `docs/backend/ai-gateway.md`
- `docs/backend/executors.md`
- `tests/test_ai_gateway.py`
- `tests/test_cf_containers_executor.py`
- `tests/test_failure_paths.py`
