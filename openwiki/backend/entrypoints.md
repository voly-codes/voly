# Backend entrypoints

This page covers the main ways VOLY is started and exposed to users and other services.

## CLI entrypoint

`voly/cli/main.py` defines the top-level Click group and registers the command families used across the repository: platform/infra commands, registry and catalog commands, runner commands, telemetry commands, and the primary user-facing commands such as `init`, `setup`, `serve`, `ui`, `run`, and `status`.

The README and CLI module together show that the CLI is the primary control surface for local development and automation.

## FastAPI app

`voly/web/server.py` creates the FastAPI app used by `voly ui`. It wires CORS, static file serving for the bundled frontend, and API routers for tasks, runs, registry, marketplace, Cloudflare integration, gateway status, DSPy, and telemetry.

A few implementation details matter for future changes:

- `.env` is loaded from the repository root at startup if present.
- The app resolves an events directory for task/run state.
- The static frontend is mounted at `/` when built assets exist.

## Operational entrypoints

The repository also exposes several operational commands in the CLI surface:

- `voly serve` for the CF-native pipeline runner / worker-oriented flow
- `voly ui` for the combined API + UI app
- `voly run` for task execution through either the pipeline or an executor
- `voly status` and related commands for inspecting runtime state

## API surface

`docs/backend/api.md` is the canonical source for endpoint-level behavior. The most important route for orchestration is `POST /api/run`, which streams SSE events back to the caller.

## What to watch when changing entrypoints

- Keep the CLI command registrations and tests in sync.
- Keep the web app routers aligned with the frontend expectations.
- Update API docs when endpoints, event shapes, or startup behavior change.
- Be careful with `.env` loading and repository-root-relative paths; those are part of the local development contract.

## Useful source files

- `voly/cli/main.py`
- `voly/web/server.py`
- `voly/web/routes/*`
- `docs/backend/api.md`
- `README.md`
