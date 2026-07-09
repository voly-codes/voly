# Spend Protocol (v1)

HTTP interface for the spend accounting service. The core talks to it via
`voly/spend/client.py:SpendClient`; the server implementation can be anything —
the reference single-user worker lives in `cf-workers/` (Durable
Objects); self-hosted and team (multi-tenant) implementations plug in via
the same protocol through `CF_WORKER_SPEND_URL` / `spend.remote_url`.

This is a **versioned public contract** of the core: request/response shapes
are frozen by contract tests (`tests/test_protocol_contracts.py`).
A change = bump the version here + update the snapshot in the test.

## Authentication

`Authorization: Bearer <token>` — token from `CF_WORKER_SPEND_TOKEN`
(fallback `CLOUDFLARE_API_TOKEN`). All requests/responses are `application/json`.

## Endpoints

### `GET /health`

Availability check. Response: `{"status": "ok"}` (shape is not fixed;
HTTP 200 matters).

### `POST /spend/record`

Record spend for a task. Body (all fields required; empty strings
allowed):

```json
{
  "agent": "developer",
  "cost_usd": 0.25,
  "task_id": "uuid",
  "model": "claude-sonnet-4-6",
  "provider": "anthropic"
}
```

Response: HTTP 200; body is ignored.

### `GET /spend/check?agent=<agent>&limit=<daily_limit>`

Check whether the agent's daily limit is exceeded. Response:

```json
{"ok": true, "spent": 1.23, "limit": 20.0}
```

`ok=false` → the caller stops the task with status
`spend_limited` (see `pipeline/stages.py:_stage_spend_check`).

### `GET /spend/summary?days=<n>`

Spend aggregate over n days. Response shape is up to the server
(reference: sums by agents/days); the core passes it to the UI as-is.

### `GET /spend/recent?limit=<n>`

Recent records: `{"entries": [ { ... }, ... ]}` — the core only reads the
`entries` key.

## v1 boundaries

- Organization/user identity is outside the protocol (token = tenant);
  multi-tenant implementations handle this on their side.
- Currency is USD, field `cost_usd`.
- Retries/idempotency of `record` are not specified (telemetry events are
  the source of truth for reconciliation; see `TaskEvent` in `docs/backend/api.md`).
