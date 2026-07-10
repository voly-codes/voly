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

## /api/providers/keys — BYOK provider keys (localhost-only)

Manage AI provider keys stored in **CF Secrets Store** (BYOK,
`docs/proposals/byok-cf-secrets.md`). All three endpoints reject non-localhost
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
