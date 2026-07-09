# Backend entrypoints

This page covers the main ways VOLY is started and exposed to users and other services.

## CLI entrypoint

`voly/cli/main.py` defines the top-level Click group and registers command families: platform/infra, registry/catalog, runner, telemetry, and primary user commands such as `init`, `setup`, `serve`, `ui`, `run`, and `status`.

The CLI is the primary control surface for local development and automation.

## FastAPI app

`voly/web/server.py` creates the FastAPI app used by `voly ui`. It wires:

- **CORS** — origins from `auth.cors_origins`; when JWT auth is on and origins are still `["*"]`, localhost defaults are applied
- **JWT middleware** (`JWTAuthMiddleware`) — enforces Bearer tokens on protected `/api/*` when `auth.enabled` and `jwt_secret` are set
- **API routers** — auth, tasks/run, registry, marketplace, Cloudflare, gateway, DSPy, telemetry
- **Static UI** — built assets under `voly/web/static/` mounted at `/` when present

Implementation details that matter for future changes:

- `.env` is loaded from the repository root at startup if present
- Events directory is resolved for task/run state
- Startup logs a **warning** when auth is disabled (open API / localhost-only mode)
- Middleware order: CORS outermost, then JWT (so preflight and 401s get CORS headers)

### Auth routes

| Endpoint | Access | Role |
|---|---|---|
| `POST /api/auth/login` | public | username/password → JWT |
| `GET /api/auth/status` | public | whether JWT is enforced |
| `GET /api/status` | public | server health / config snapshot |
| Other `/api/*` | protected when auth on | require `Authorization: Bearer …` |

**UI:** sign-in modal + header when `auth.enabled`; token in `localStorage`;
API client attaches Bearer. SSE streams use `?access_token=` (GET only).

Code: `voly/web/routes/auth.py`, `voly/web/auth/*`, `ui/src/lib/api/client.js`,
`ui/src/lib/stores/authStore.svelte.ts`. Tests: `tests/test_web_auth.py`.

## Operational entrypoints

- `voly serve` — CF-native pipeline runner / worker-oriented flow (`:9202` by default)
- `voly ui` — combined API + UI app (`:7788` by default)
- `voly run` — task execution through pipeline or an executor
- `voly status` and related commands — runtime inspection

Ports are CLI flags (`--port`), not env vars.

## API surface

`docs/backend/api.md` is the canonical endpoint reference. The most important orchestration route is `POST /api/run` (SSE stream). Smart dispatch and A2A behavior are described there and in the pipeline wiki page.

## What to watch when changing entrypoints

- Keep CLI command registrations and tests in sync
- Keep web routers aligned with the frontend API client
- Update API docs when endpoints, auth behavior, event shapes, or startup change
- Be careful with `.env` loading and repository-root-relative paths
- Never ship network-exposed UI without auth enabled

## Useful source files

- `voly/cli/main.py`
- `voly/web/server.py`
- `voly/web/auth/middleware.py`
- `voly/web/auth/jwt.py`
- `voly/web/routes/*`
- `docs/backend/api.md`
- `README.md`
