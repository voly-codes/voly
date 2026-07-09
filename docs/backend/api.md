# API Routes — Backend Reference

FastAPI server: `voly/web/server.py`. Start: `voly ui` (port 7788).

---

## Auth (JWT)

By default **auth is disabled** — the API is open (localhost only). For network
access, enable JWT:

```yaml
# voly.yaml
auth:
  enabled: true
  jwt_secret: "${VOLY_JWT_SECRET}"
  users:
    admin: "change-me"
  cors_origins:
    - "http://localhost:7788"
    - "http://localhost:5173"
```

Env: `VOLY_AUTH_ENABLED=true`, `VOLY_JWT_SECRET=…`, `VOLY_AUTH_USERS=admin:pass`.

When auth is enabled, all `/api/*` except public routes require
`Authorization: Bearer <token>`.

| Public | Protected |
|---|---|
| `POST /api/auth/login` | `POST /api/run` |
| `GET /api/auth/status` | `GET /api/tasks` |
| `GET /api/status` | registry / marketplace / … |
| `/api/docs`, openapi | |

```bash
# login
curl -s -X POST http://127.0.0.1:7788/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me"}'
# → {"access_token":"…","token_type":"bearer","expires_in":3600}

# protected call
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7788/api/tasks
```

With `auth.enabled` + `cors_origins: ["*"]`, the server automatically narrows CORS
to localhost origins (see `voly/web/server.py`).

---

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
data: {"type": "done", "success": true, "content": "...", "billing_fallback": "zen"}
data: {"type": "error", "error": "..."}
```

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
