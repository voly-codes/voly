# Spend Protocol (v2)

v2 adds idempotency (`event_id`), product attribution (`product`), model
version and token counts. v1 bodies are still accepted by v2 servers. The
v2 design is in [`docs/proposals/spend-protocol-v2.md`](../proposals/spend-protocol-v2.md).

HTTP interface for the spend accounting service. The core talks to it via
`voly/spend/client.py:SpendClient`; the server implementation can be anything —
the multi-tenant worker is maintained outside this repository; the single-user
reference worker lives in `cf-workers/` (Durable Objects); self-hosted and team (multi-tenant) implementations plug in via
the same protocol through `CF_WORKER_SPEND_URL` / `spend.remote_url`.

This is a **versioned public contract** of the core: request/response shapes
are frozen by contract tests (`tests/test_protocol_contracts.py`).
A change = bump the version here + update the snapshot in the test.

## Authentication

`Authorization: Bearer <token>` — token from `CF_WORKER_SPEND_TOKEN`
only (must match the worker wrangler secret `API_TOKEN`; do **not** reuse
`CLOUDFLARE_API_TOKEN`). All requests/responses are `application/json`.

## Endpoints

### `GET /health`

Availability check. Response: `{"status": "ok"}` (shape is not fixed;
HTTP 200 matters).

### `POST /spend/record`

Record spend for a task. Body:

```json
{
  "agent": "developer",
  "cost_usd": 0.25,
  "task_id": "uuid",
  "model": "claude-sonnet-4-6",
  "provider": "anthropic",
  "schema_version": 2,
  "event_id": "uuid",
  "product": "voly",
  "model_version": "claude-sonnet-4-6-20260101",
  "tokens_in": 1200,
  "tokens_out": 300
}
```

- The five v1 fields are required (empty strings allowed).
- `schema_version`, `event_id`, `product`, `model_version`, `tokens_in`,
  `tokens_out` are v2 fields. The v2 client always sends them. v1 servers and
  bodies without them are still valid.
- `event_id` is a UUID for one logical spend event. The client creates a new
  one per `record()` call. A retry of the same event must send the same
  `event_id`. A repeated `event_id` in the same tenant is stored once.
- `product` is a free string of at most 64 characters, set in config (`spend.product`).
- `model_version` is at most 128 characters. Token counts are integers >= 0.

Response: HTTP 200 with `{"ok": true, "duplicate": false}`, or
`"duplicate": true` when `event_id` was already stored. Clients may ignore
the body.

### `GET /spend/check?agent=<agent>&limit=<daily_limit>`

Check whether the agent's daily limit is exceeded. Response:

```json
{"ok": true, "spent": 1.23, "limit": 20.0}
```

`ok=false` → the caller stops the task with status
`spend_limited` (see `pipeline/stages_route.py:_stage_spend_check`).

### `GET /spend/summary?days=<n>`

Spend aggregate over n days. Response shape is up to the server
(reference: sums by agents/days); the core passes it to the UI as-is.

### `GET /spend/recent?limit=<n>`

Recent records: `{"entries": [ { ... }, ... ]}` — the core only reads the
`entries` key.

## Boundaries

- Organization/user identity is outside the protocol (token = tenant);
  multi-tenant implementations handle this on their side.
- Currency is USD, field `cost_usd`.
- Idempotency is per tenant and keyed by `event_id` (v2). Records without
  `event_id` are inserted every time, as in v1. Telemetry events remain the
  source of truth for reconciliation (see `TaskEvent` in `docs/backend/api.md`).
- Repository/project tags and outcome-aware aggregation are not part of v2.
  Their planned rollout is in
  [`docs/proposals/task-tags-and-trusted-outcomes.md`](../proposals/task-tags-and-trusted-outcomes.md).
  Adding them to `/spend/record` requires a further protocol-version bump and
  updated contract tests.
- Prompts, source paths, repository names and evidence content never enter
  the protocol.
