# Architecture overview

VOLY is a project-agnostic control plane for AI agents. It sits between a developer and the execution backends, and it is designed to keep orchestration logic separate from the target project that agents modify.

## Core architectural split

The repository consistently describes two layers:

- **Layer A — model gateway / routing / fallback**: model-provider routing, caching, DLP, rate limits, spend limits, and upstream delegation. This is intentionally treated as a mature integration boundary rather than the product's primary differentiator.
- **Layer B — orchestration of file-capable CLI agents**: agent execution, billing fallback across executors, multi-agent task decomposition, and project-level telemetry. This is the main product surface.

The canonical explanation lives in `docs/ARCHITECTURE.md`, and the implementation follows that split in `voly/ai_gateway/gateway.py` and `voly/runner/agent_runner.py`.

## The two execution paths

### 1) Pipeline path
The pipeline handles text-only reasoning and orchestration steps. In `voly/pipeline/core.py`, it coordinates stages such as routing, memory retrieval, RTK filtering, skill injection, optional DSPy, and the final `AIGateway.chat()` call.

### 2) Executor path
The executor path is for tasks that must write files. `voly/runner/agent_runner.py` resolves an executor, optionally refines the task with DSPy, executes the chosen backend, and then applies billing fallback when needed.

## Public contracts

The repo treats several interfaces as versioned contracts and protects them with tests. The high-signal ones are:

- **`TaskEvent` telemetry** — `schema_version: 3` with `correlation_id` (`voly/telemetry.py`, `voly/correlation.py`, `docs/backend/api.md`)
- **Spend protocol** — HTTP spend record/check (`docs/backend/spend-protocol.md`)
- **A2A federation** — task create/complete/callback contracts

`correlation_id` links open-core API/SSE, hosted control plane, and Cloudflare Worker logs (`X-Correlation-ID`). Set `VOLY_JSON_LOGS=1` for JSON logs that include it.

In-gateway spend accounting is separate from the remote spend protocol: `AIGateway.chat()` records daily budget usage **only on successful** model calls.

### Memory backends

`memory.backend` in config: `local` (SQLite), `hybrid` (local + CF memory Worker), or `agent_memory` (Cloudflare Agent Memory HTTP — private beta). Client: `voly/memory/agent_memory_client.py`. See `docs/backend/config.md`.

## Web surface (self-host)

The FastAPI app (`voly ui`) is part of the control plane, not a separate product. Default posture is **localhost-open** (auth off + startup warning). JWT auth, CORS hardening, and login live under `voly/web/auth/` and are documented in entrypoints + `docs/backend/api.md`.

## Packaging

Wheel/sdist must include core packages (`voly.pipeline`, `voly.config`, `voly.cloudflare`, `voly.web.auth`, `voly.web.routes`, …) via `pyproject.toml` — editable installs hide packaging holes. See [Configuration and operations](../config-and-operations.md).

## What to watch when changing architecture

- Keep VOLY project-agnostic; avoid hardcoding target-project behavior into `voly/`.
- Route model calls through `AIGateway.chat()` so caching, DLP, limits, and telemetry stay centralized.
- Do not charge spend on failed provider responses.
- Treat changes to telemetry or protocol shapes as versioned contract changes.
- Update `docs/ARCHITECTURE.md`, `docs/backend/pipeline.md`, `docs/backend/ai-gateway.md`, and `docs/backend/api.md` alongside code changes.

## Useful source files

- `docs/ARCHITECTURE.md`
- `voly/pipeline/core.py`
- `voly/runner/agent_runner.py`
- `voly/ai_gateway/gateway.py`
- `voly/web/server.py`
- `voly/web/auth/*`
- `voly/telemetry.py`
- `voly/correlation.py`
- `voly/memory/agent_memory_client.py`

