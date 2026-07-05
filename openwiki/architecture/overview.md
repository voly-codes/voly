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

The repo treats several interfaces as versioned contracts and protects them with tests. The high-signal one documented in the source is `TaskEvent` telemetry, which carries `schema_version: 1` and is referenced from `voly/telemetry.py` and `docs/backend/api.md`. The architecture docs also call out the spend protocol and A2A federation as public contracts.

## What to watch when changing architecture

- Keep VOLY project-agnostic; avoid hardcoding target-project behavior into `voly/`.
- Route model calls through `AIGateway.chat()` so caching, DLP, limits, and telemetry stay centralized.
- Treat changes to telemetry or protocol shapes as versioned contract changes.
- Update the source docs in `docs/ARCHITECTURE.md`, `docs/backend/pipeline.md`, `docs/backend/ai-gateway.md`, and `docs/backend/api.md` alongside code changes.

## Useful source files

- `docs/ARCHITECTURE.md`
- `voly/pipeline/core.py`
- `voly/runner/agent_runner.py`
- `voly/ai_gateway/gateway.py`
- `voly/web/server.py`
- `voly/telemetry.py`
