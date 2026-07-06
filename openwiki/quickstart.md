# OpenWiki quickstart

VOLY is a Python-based AI control plane for routing tasks to file-capable CLI agents, coordinating multi-agent workflows, enforcing spend and rate limits, and recording telemetry for a web UI and API. The repository also includes Cloudflare Workers, a Svelte frontend, CLI tooling, and an optional DSPy optimization layer.

Start with these source files:
- `README.md` for the product overview and user-facing setup flow
- `CLAUDE.md` for the project rules that guide future changes
- `pyproject.toml` for package structure and optional dependencies
- `voly.yaml` and `codeops.yaml` for runtime configuration defaults
- `voly/cli/main.py` for the CLI entrypoint
- `voly/web/server.py` for the FastAPI app
- `voly/pipeline/core.py` for the main orchestration path
- `voly/runner/agent_runner.py` for file-writing executor runs
- `voly/ai_gateway/gateway.py` for model routing, caching, and fallback

## What this repository does

VOLY has two main execution paths:

1. **Pipeline path** — text-only reasoning, routing, memory lookup, skill injection, optional DSPy, and final LLM calls through `AIGateway.chat()`.
2. **Executor path** — file-capable agents that actually modify a target project, with billing fallback across executors when one provider runs out of budget.

The project is intentionally **project-agnostic**: the target codebase is supplied at runtime through `--cwd` or configuration, rather than being hardcoded into the source tree.

## Major domains

- **Architecture and control flow** — how the pipeline, A2A orchestration, and executor path fit together.
- **Gateway and cost control** — routing across model providers, caching, DLP, spend limits, and upstream delegation.
- **CLI and web entrypoints** — the command surface and HTTP API that drive the system.
- **UI** — the Svelte app that visualizes runs, gateway status, telemetry, and DSPy state.
- **Marketplace and catalog flows** — skills browsing, plugin publishing/sync, and local fallback behavior when the remote marketplace is unavailable.
- **Configuration and operations** — runtime config, environment variables, generated artifacts, and testing expectations.

## Wiki map

- [Architecture overview](architecture/overview.md)
- [Backend entrypoints](backend/entrypoints.md)
- [Gateway and executors](backend/gateway-and-executors.md)
- [Pipeline and A2A](backend/pipeline-and-a2a.md)
- [Frontend UI](frontend/ui.md)
- [Configuration and operations](config-and-operations.md)

## Where to go next

If you are changing orchestration behavior, read the architecture and pipeline pages first.
If you are changing model routing or fallback behavior, read the gateway and executors page.
If you are changing the API or CLI surface, read the entrypoints page.
If you are changing the UI, start with the frontend page and then inspect the relevant `ui/src/lib/components/*` files.

## Source map

- `voly/cli/main.py` — CLI command registration
- `voly/web/server.py` — FastAPI app construction and router wiring
- `voly/pipeline/core.py` — main pipeline orchestration and cache scoping
- `voly/runner/agent_runner.py` — executor chain, DSPy planning, and work reports
- `voly/ai_gateway/gateway.py` — middleware stack, upstream delegation, and fallback logic
- `voly/web/routes/*` — API route implementations
- `ui/src/lib/components/*` — dashboard sections and panels
- `tests/` — behavioral and contract tests that protect the public interfaces
