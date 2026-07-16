# API Routes — Backend Reference

FastAPI server: `voly/web/server.py`. Start: `voly ui` (port 7788).

---

## Auth

**Open-core has no authentication** — the API is open and intended for
localhost use only. All `/api/*` routes are unprotected and CORS is `["*"]`.

Authentication (local JWT + SSO), team dashboards, org spend governance, and
the hosted control plane are commercial **Team-tier** features that live in
the closed **voly-cloud** distribution, not in this open-core repo. Do not add
auth/SSO or other commercial code here — see `CONTRIBUTING.md`.

## POST /api/run

Start a task. Returns an SSE stream.

```typescript
// Request
{
  task: string,
  agent?: string,      // "" = auto-route
  model?: string,      // "" = auto
  executor?: string,   // "pipeline" | "claude-code" | "wrangler" | "zen" | ...
  cwd?: string,        // target project path (overrides config.default_cwd)
  max_turns?: number,  // default 30
  timeout?: number,    // default 300 — total executor deadline (s), incl. internal model fallback
  a2a_delegate?: bool, // delegate to A2A federation
  dry_run?: bool       // run executor, then roll back all file changes (diff preview in result)
}

// SSE events
data: {"type": "start", "task": "...", "executor": "claude-code", "correlation_id": "..."}
data: {"type": "heartbeat"}
data: {"type": "done", "success": true, "content": "...", "billing_fallback": "zen", "correlation_id": "..."}
data: {"type": "error", "error": "..."}
```

Pass `X-Correlation-ID` (or `X-Request-ID`) on the request to pin the id across
API → runner → CF Workers. The response also echoes `X-Correlation-ID`.
Set `VOLY_JSON_LOGS=1` for one-JSON-object-per-line logs with `correlation_id`.

On executor failure, the `done` event also carries structured diagnostics (raw
`error` is preserved for backward compatibility):

```typescript
{
  success: false,
  error: string,           // raw executor error
  error_message: string,   // human-readable prefix + detail
  error_class: string,     // billing | not_available | timeout | auth | unrecognized | ...
  error_hint?: string,     // next-step hint when known
}
```

The blocking `pipeline`/executor call runs in a `ThreadPoolExecutor`
(`_THREAD_POOL` in `run.py`, sized by `VOLY_RUN_POOL_WORKERS`, default 16 —
executor calls are I/O-bound subprocess waits, not CPU-bound, so a larger
pool doesn't cost much). While waiting, the stream emits a `heartbeat` event
every 15s (`_RUN_HEARTBEAT_SECONDS`) so proxies/browsers don't idle out the
connection during a long queue wait or a long-running task, and checks
`request.is_disconnected()` on each wait cycle — if the client is gone, the
generator returns immediately instead of holding the SSE connection open.
The underlying call keeps running in its worker thread either way (Python
can't force-cancel a blocking `subprocess.run()`), but no further stream
writes are attempted on a dead connection.

When the executor safety policy acts, `done` additionally carries `dry_run`,
`dry_run_diff` (truncated preview), `safety_violation` and
`safety_rolled_back` (see `docs/backend/executors.md` § Safety policy).

For the multi-agent (A2A local) path, `start` also carries `a2a: true`,
`hybrid: bool`, resolved `cwd`, and — when `a2a.hybrid_code_gen` is on but no
`cwd` resolved — `hybrid_warning: "hybrid_skipped_no_cwd"`. `done` includes a
`hybrid` summary (`executor_roles`, `chat_roles`, `files_touched`) and per-role
`a2a_assignments` with `mode` / `executor` / `files_touched`.
`hybrid_warning` is surfaced to the user as a visible warning banner by
`RunPanel.svelte` (see `docs/frontend/api-client.md`).

**Smart dispatch:** if `executor="pipeline"` and the task requires code gen,
it is automatically promoted to `executor="claude-code"` with `cwd` from `config.default_cwd`
or the `VOLY_PROJECT_CWD` env var.

Logs: `[DISPATCH] pipeline → claude-code`, `[CHAIN:START]`, `[CHAIN:BILLING_FALLBACK]`

---

## GET /api/environment

Local readiness for the Web UI / onboarding. Does **not** call remote provider
APIs — only env key presence, `PATH` binaries, cwd, and optional cloud link.

```typescript
// Query
?cwd=/path/to/project   // optional — overrides config default_cwd for the cwd check

// Response
{
  ready: boolean,
  summary: string,
  providers_configured: string[],
  default_cwd: string,
  executors: {
    "pipeline": { available: true, kind: "gateway", detail: "..." },
    "claude-code": { available: boolean, kind: "cli", binary: "claude", path?: string, detail: string, hint?: string },
    // …
  },
  checks: [
    { id: string, label: string, status: "ok"|"warn"|"error"|"skip", detail: string, hint: string, group: string }
  ]
}
```

`ready` is true when at least one provider API key **or** one file-capable CLI
is available. Missing cwd is a warning, not a hard fail. Cloud link is optional
(`status: skip` when unlinked).

Shared implementation: `voly/environment.py` (`collect_environment_report`).
Also printed under `[Environment]` in `voly status`.

---

## GET /api/tasks

Task list from `.voly/events/`. SSE stream of updates.

```typescript
// SSE events (/api/tasks/stream)
data: {"type": "init", "tasks": [...]}   // first scan: snapshot of existing tasks (no "new" badges)
data: {"type": "new", "tasks": [...]}    // tasks that appeared after the snapshot
data: {"type": "heartbeat"}              // every 5s when nothing changed
```

## GET /api/tasks/{task_id}/artifacts/{name}

Serve local task artifacts. Currently used for `pxpipe` rendered PNGs saved
under `.voly/pxpipe/images/<task_id>/`.

```typescript
// TaskEvent.artifacts[]
{
  kind: "pxpipe_image",
  media_type: "image/png",
  name: "2026-07-13T..._req001_model_p01.png",
  bytes: 12345,
  url: "/api/tasks/<task_id>/artifacts/<name>"
}
```

The route only serves `.png` files inside the task artifact directory.

---

## GET /api/runs · GET /api/runs/{task_id}

In-flight run records (`.voly/runs/`, RunTracker heartbeats) — tasks that are
**still executing**, including ones launched from the CLI. `?active=1` filters
to `status=running`; each record carries `task`, `current_role`, `roles`,
`done_roles/total_roles`, `step_statuses` (plan mirror), `elapsed_seconds`,
`age_seconds` (heartbeat freshness). Executor runs heartbeat every ~10s from
`AgentRunner`; multi-agent runs after every role.

Note: the CLI writes records relative to its own cwd — runs launched from a
different directory than the server's project keep their records in that
project's `.voly/runs` (same rule as TaskEvents).

---

## GET /api/status

Server state, configuration, versions.

```json
{
  "version": "0.1.0",
  "tasks_count": 12,
  "events_dir": "/path/to/.voly/events",
  "default_cwd": "/home/user/project",
  "cf": { ... }
}
```

`default_cwd` — path from `voly.yaml` (`default_cwd`) or env `VOLY_PROJECT_CWD`. Empty string if unset. Used by the UI (RunPanel) to auto-fill the cwd field on load.

---

## GET /api/registry/agents

List of registered agents from `voly/registry/`.

---

## GET /api/registry/skills

List of skills from `voly/catalog/`.

---

## GET /api/models

List of available models (from config + providers).

---

## GET /api/ai-gateway/status

AI Gateway state: providers, spend, rate limits.

---

## GET /api/spend/status

Current daily spend by agents/providers.

---

## /api/providers/keys — BYOK provider keys (localhost-only)

Manage AI provider keys stored in **CF Secrets Store** (BYOK,
`docs/backend/ai-gateway.md` § BYOK). All three endpoints reject non-localhost
clients with 403. Key values are write-only: never logged, never returned.
Requires `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` (Secrets Store Edit).

| Method | Path | Body / params | Result |
|---|---|---|---|
| GET | `/api/providers/keys` | — | `{configured, byok_enabled, keys: [{name, provider, alias}]}` |
| POST | `/api/providers/keys` | `{provider, key, alias?}` | `{ok, name}` — creates `{gateway_id}_{slug}_{alias}` secret with `ai_gateway` scope |
| DELETE | `/api/providers/keys/{provider}?alias=` | — | `{ok}` |

`provider` must be BYOK-eligible (`anthropic`, `openai`, `google-ai-studio`,
`deepseek`) — others get 400.

---

## POST /api/telemetry

Write telemetry from external sources.

### TaskEvent contract (schema_version: 3)

`TaskEvent` (`voly/telemetry.py`) is the public versioned task event format;
it is consumed by external readers (CF Pipelines ingest, R2, dashboards).
Each event carries `schema_version` (currently `3`). The v3 field set is frozen
by the contract test `tests/test_protocol_contracts.py` — changing the schema
requires bumping `TASK_EVENT_SCHEMA_VERSION`, updating this section, and the
snapshot in the test. Key field groups: identification (`task_id`, `agent`, `executor`,
`status`, `schema_version`, `correlation_id`), cost (`cost_usd`, `retry_count`,
`retry_cost_usd`, `tokens`), diagnostics (`error`, `error_class`,
`chain_timelog`), local artifacts (`artifacts`), A2A (`a2a_*`), DSPy (`dspy_*`).

`correlation_id` links API requests, runner TaskEvents, and Cloudflare Worker
calls (forwarded as `X-Correlation-ID`) so Workers Logs custom fields can be
filtered together with VOLY events. Clients may send `X-Correlation-ID` or
`X-Request-ID`; otherwise the API generates a UUID.

Related contract: spend protocol — `docs/backend/spend-protocol.md`.

---

## CF Worker endpoints (`cf-workers/agent/`)

Separate Worker for CF-native tasks. Start: `wrangler dev`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Availability check + pipeline/A2A callback status |
| `/infer` | POST | CF AI Gateway inference → FILE blocks for LocalPatchApplier |
| `/agents/:name/run` | POST | Run a task + A2A callback (`task_id` optional) |
| `/mcp` | * | MCP tools (`run_task`) |

**A2A callback:** `completeA2ATask()` POSTs `/tasks/:id/complete` to the federation worker via
service binding `A2A_FEDERATION` (HTTP fetch to `*.workers.dev` yields CF error 1042).

## CF Worker endpoints (`cf-workers/a2a/`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Federation + queue status |
| `POST /tasks` | POST | Create a task (`async: true` → queue dispatch) |
| `GET /tasks/:id` | GET | Task status |
| `POST /tasks/:id/complete` | POST | Callback from agent worker (Bearer `API_TOKEN`) |
| queue consumer | — | Dispatch via service binding `AGENT_WORKER` |

**`POST /infer`** — primary endpoint for WranglerExecutor:
```typescript
// Request
{ task: string, context?: string, model?: string, system?: string, max_tokens?: number }
// Response
{ success: bool, content: string, model: string, provider: string, input_tokens?, output_tokens? }
```
