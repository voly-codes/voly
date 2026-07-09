# OpenWiki quickstart

VOLY is a Python-based **self-hosted** AI control plane for routing tasks to file-capable CLI agents, coordinating multi-agent workflows, enforcing spend and rate limits, and recording telemetry for a web UI and API. The repository also includes Cloudflare Workers, a Svelte frontend, CLI tooling, and an optional DSPy optimization layer.

Start with these source files:

- `README.md` — product overview (English primary)
- `README_ru.md` — Russian overview
- `CLAUDE.md` — project rules that guide future changes
- `pyproject.toml` — package structure and optional dependencies (`voly[ui]` includes PyJWT)
- `voly.yaml` and `codeops.yaml` — runtime configuration defaults
- `voly/cli/main.py` — CLI entrypoint
- `voly/web/server.py` — FastAPI app (CORS + optional JWT middleware)
- `voly/pipeline/core.py` — main orchestration path
- `voly/runner/agent_runner.py` — file-writing executor runs
- `voly/ai_gateway/gateway.py` — model routing, caching, spend, and fallback

## What this repository does

VOLY has two main execution paths:

1. **Pipeline path** — text-only reasoning, routing, memory lookup, skill injection, optional DSPy, and final LLM calls through `AIGateway.chat()`.
2. **Executor path** — file-capable agents that actually modify a target project, with billing fallback across executors when one provider runs out of budget:

   `claude-code → wrangler → opencode → zen`

The project is intentionally **project-agnostic**: the target codebase is supplied at runtime through `--cwd` or configuration, rather than being hardcoded into the source tree.

## Security model (self-host)

By default the Web UI API is **open on localhost** (auth disabled) and logs a startup warning. Before exposing the UI/API on a network, enable JWT:

```bash
export VOLY_AUTH_ENABLED=true
export VOLY_JWT_SECRET='long-random-secret-at-least-32-chars'
export VOLY_AUTH_USERS='admin:change-me'
```

See [Configuration and operations](config-and-operations.md) and `docs/backend/api.md`.

## Major domains

- **Architecture and control flow** — pipeline, A2A orchestration, and executor path
- **Gateway and cost control** — routing, caching, DLP, spend (success-only recording), upstream delegation
- **CLI and web entrypoints** — command surface and HTTP API (optional JWT)
- **UI** — Svelte app for runs, gateway, telemetry, DSPy, marketplace
- **Marketplace and catalog** — skills/plugins with local fallback when the remote worker is down
- **Configuration and operations** — runtime config, env vars, packaging, generated artifacts, tests

## Wiki map

- [Architecture overview](architecture/overview.md)
- [Backend entrypoints](backend/entrypoints.md)
- [Gateway and executors](backend/gateway-and-executors.md)
- [Pipeline and A2A](backend/pipeline-and-a2a.md)
- [Frontend UI](frontend/ui.md)
- [Configuration and operations](config-and-operations.md)

## Where to go next

If you are changing orchestration behavior, read the architecture and pipeline pages first.  
If you are changing model routing, spend, or fallback, read the gateway and executors page.  
If you are changing the API, CLI, or auth surface, read the entrypoints page.  
If you are changing the UI, start with the frontend page and then inspect `ui/src/lib/components/*`.

## Source map

- `voly/cli/main.py` — CLI command registration
- `voly/web/server.py` — FastAPI app, CORS, JWT middleware wiring
- `voly/web/auth/*` — JWT create/verify, middleware, login dependencies
- `voly/web/routes/*` — API routes (including `auth.py`)
- `voly/pipeline/core.py` — pipeline orchestration and cache scoping
- `voly/runner/agent_runner.py` — executor chain, DSPy planning, work reports
- `voly/ai_gateway/gateway.py` — middleware stack, spend-on-success, upstream delegation
- `ui/src/lib/components/*` — dashboard sections and panels
- `tests/` — behavioral and contract tests (including `tests/test_web_auth.py`)
