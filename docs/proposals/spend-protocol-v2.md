# Spend Protocol v2 (proposal)

Status: client side implemented in `voly` (`voly/spend/client.py`); server side in progress in the hosted spend worker. Protocol v2 is documented in [spend-protocol](../backend/spend-protocol.md).
Related: [spend-protocol v1](../backend/spend-protocol.md), [task tags and trusted outcomes](task-tags-and-trusted-outcomes.md).

## Problem

Spend Protocol v1 has four gaps that matter once spend is reported from several products:

1. **No idempotency.** `POST /spend/record` has no event identity. A client retry after a timeout inserts the same spend twice. v1 explicitly leaves retries unspecified.
2. **No product attribution.** The canonical worker cannot split spend between products.
3. **No model version or token counts.** Cost cannot be traced back to a model version, and tokens cannot be reported next to cost.
4. **No schema version in the body.** Servers cannot tell old and new clients apart except by guessing from field presence.

## Goals

- Make `record` idempotent for clients that send an `event_id`.
- Attribute each record to a product.
- Record model version and token counts.
- Stay backward compatible: a v1 client keeps working against a v2 server.

## Non-goals

- Tags (`repo`, `project`, `team`) — covered by [task tags and trusted outcomes](task-tags-and-trusted-outcomes.md).
- Prompts, source paths, repository names or evidence content. None of these enter the protocol.
- Outcome-aware aggregation.
- Changing the token-to-tenant rule. Tenant comes only from the bearer token.

## Request: `POST /spend/record`

Body. The five v1 fields keep their meaning and stay required for v1 compatibility.

| Field | Type | Version | Notes |
|---|---|---|---|
| `agent` | string | v1 | unchanged |
| `cost_usd` | number | v1 | unchanged |
| `task_id` | string | v1 | unchanged, empty string allowed |
| `model` | string | v1 | unchanged |
| `provider` | string | v1 | unchanged |
| `schema_version` | integer | v2 | `2` for v2 clients; absent means v1 |
| `event_id` | string | v2 | recommended; UUID generated once per logical spend event |
| `product` | string, max 64 | v2 | from a config value; free string |
| `model_version` | string, max 128 | v2 | model build or snapshot id, when the provider reports it |
| `tokens_in` | integer >= 0 | v2 | optional, 0 if unknown |
| `tokens_out` | integer >= 0 | v2 | optional, 0 if unknown |

### Idempotency

- If `event_id` is present and already stored for the same tenant, the server does not insert a second row. It returns HTTP 200 with `"duplicate": true`.
- The uniqueness scope is the tenant partition. Two tenants may use the same `event_id`.
- If `event_id` is absent, the server behaves as v1 and inserts the row.
- Retries reuse the same `event_id`. A new model call always gets a new one.

### Response

HTTP 200 with `{"ok": true, "duplicate": false}` for a new row, or `"duplicate": true` for a repeated `event_id`. v1 clients ignore the body, so the new field is safe.

## Server changes (`voly-cloud/cf-workers/spend`)

- Add columns `event_id`, `product`, `model_version`, `tokens_in`, `tokens_out` to the `spend` table. Apply the migration in the Durable Object constructor with `ALTER TABLE ... ADD COLUMN` and defaults, so existing rows stay valid.
- Add a unique index on `event_id` where it is not empty.
- `/spend/summary` and `/spend/recent` return the new columns. `/spend/summary` accepts an optional `product` filter.

## Client changes (`voly/voly/spend/client.py`)

- `record()` gets new keyword-only arguments with empty defaults. The existing positional signature does not change.
- `record()` creates `event_id` (UUID) for each call. `record_task_spend` calls `record()` once per task event. A caller that retries must pass the same `event_id` explicitly.
- `schema_version` is sent as `2` by the new client only.

## Privacy

- `product` comes from configuration, not from a request or a prompt.
- Tenant identity comes only from the bearer token.
- No prompt text, file path, repository name or evidence content is sent.

## Contract and tests

- Bump the protocol to v2 in `docs/backend/spend-protocol.md`.
- Update the frozen snapshot in `tests/test_protocol_contracts.py` (required by the v1 boundaries section).
- Add tests: v1 body accepted, v2 body accepted, repeated `event_id` gives one row, same `event_id` in another tenant gives a second row, migration keeps old rows.

## Plan

1. `voly`: client arguments, `event_id` in the gateway, contract tests, docs.
2. Server: migration, idempotent insert, summary filter, tests.
3. Smoke run: `voly run` once, retry the same record, check that `/spend/recent` shows one row with the right `product`.

## Open questions

- Should the server keep `event_id` indefinitely or prune it after N days?
