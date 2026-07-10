# API Routes — Backend Reference

FastAPI server: `voly/web/server.py`. Start: `voly ui` (port 7788).

---

## Auth

By default **auth is off** — the API is open (localhost only).

### Open-core (default when locking self-host): local JWT

Single-user lock without external IdP — part of the open core:

```yaml
auth:
  enabled: true
  provider: local
  jwt_secret: "${VOLY_JWT_SECRET}"
  users:
    admin: "change-me"
```

Env: `VOLY_AUTH_ENABLED=true`, `VOLY_AUTH_PROVIDER=local` (or omit), `VOLY_JWT_SECRET`,
`VOLY_AUTH_USERS`.

```bash
curl -s -X POST http://127.0.0.1:7788/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me"}'
```

### Optional SSO (`provider: clerk`)

SSO (Clerk and similar) is **not** the open-core default. It is an optional
integration aimed at team/hosted deployments and may move to a separate Team
package (`voly-team`). Core tests and examples use **local** JWT or auth off.

Providers are pluggable (`voly.web.auth.providers`): built-ins `local` and
`clerk`; external packages register via entry point group `voly.auth_providers`.

```yaml
auth:
  enabled: true
  provider: clerk
  clerk_publishable_key: "${CLERK_PUBLISHABLE_KEY}"
  clerk_issuer: "${CLERK_ISSUER}"
```

Env: `VOLY_AUTH_PROVIDER=clerk`, `CLERK_PUBLISHABLE_KEY`, `CLERK_ISSUER`
(JWKS derived as `{issuer}/.well-known/jwks.json` if `CLERK_JWKS_URL` unset).

Backend verifies session JWTs (RS256 / JWKS). UI loads `@clerk/clerk-js` only when
status reports `provider: clerk`. `POST /api/auth/login` is disabled in Clerk mode.

### Protected routes

When auth is enforced, all `/api/*` except public routes need `Authorization: Bearer`.

| Public | Protected |
|---|---|
| `POST /api/auth/login` (local only) | `POST /api/run` |
| `GET /api/auth/status` | `GET /api/tasks` |
| `GET /api/status` | registry / marketplace / … |
| `/api/docs`, openapi | |

Web UI stores the token in `localStorage` (`voly_access_token`). CORS `["*"]`
is narrowed when auth is on.

**Stream tickets:** `GET /api/tasks/stream` is the *only* route that accepts
`?access_token=` (EventSource cannot set an Authorization header). The UI
first calls `POST /api/tasks/stream-token` (normal `Authorization: Bearer`)
to mint a short-lived (60s), stream-scoped ticket via
`AuthProvider.issue_stream_ticket()`, and puts *that* — never the caller's
real access token — in the stream URL. `local` provider mints a distinct
JWT `type: "stream"` ticket that `verify_stream_ticket()` requires (a
regular access token is rejected on this path, and vice versa). Providers
that can't mint tokens they didn't issue (e.g. `clerk`) return `None` from
`issue_stream_ticket()`, and the UI falls back to the existing access token.

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
  a2a_delegate?: bool  // delegate to A2A federation
}

// SSE events
data: {"type": "start", "task": "...", "executor": "claude-code"}
data: {"type": "heartbeat"}
data: {"type": "done", "success": true, "content": "...", "billing_fallback": "zen"}
data: {"type": "error", "error": "..."}
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

## GET /api/tasks

Task list from `.voly/events/`. SSE stream of updates.

```typescript
// SSE events
data: {"type": "init", "tasks": [...]}
data: {"type": "update", "task": {...}}
```

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

## POST /api/telemetry

Write telemetry from external sources.

### TaskEvent contract (schema_version: 1)

`TaskEvent` (`voly/telemetry.py`) is the public versioned task event format;
it is consumed by external readers (CF Pipelines ingest, R2, dashboards).
Each event carries `schema_version` (currently `1`). The v1 field set is frozen
by the contract test `tests/test_protocol_contracts.py` — changing the schema
requires bumping `TASK_EVENT_SCHEMA_VERSION`, updating this section, and the
snapshot in the test. Key field groups: identification (`task_id`, `agent`, `executor`,
`status`, `schema_version`), cost (`cost_usd`, `retry_count`,
`retry_cost_usd`, `tokens`), diagnostics (`error`, `error_class`,
`chain_timelog`), A2A (`a2a_*`), DSPy (`dspy_*`).

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
