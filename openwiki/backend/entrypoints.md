# Backend entrypoints

This page covers the main ways VOLY is started and exposed to users and other services.

## CLI entrypoint

`voly/cli/main.py` defines the top-level Click group and registers command families: platform/infra, registry/catalog, runner, telemetry, and primary user commands such as `init`, `setup`, `serve`, `ui`, `run`, and `status`.

The CLI is the primary control surface for local development and automation.

Evaluated capability packs add an opt-in route:
`task → role → capability → executor → model`. Active imported capabilities
must have measured evidence. Paired experiments change one capability at a
time and track quality, cost, latency, retries, rollback and corrections.
Packs without measurable value are retired and fall back to native VOLY.

### External capability-pack discovery

`voly capability import ecc --source <checkout> --dry-run` inventories supported
ECC agents, skills, rules, hook manifests, MCP configurations, and legacy
command shims. `--json-output` returns the same report as a stable JSON object.

This entrypoint is intentionally discovery-only: `--dry-run` is mandatory, no
source component is copied or activated, imported code is not loaded, hooks and
commands are not executed, and MCP servers are not started. Resolved component
paths must remain below the selected source root. The implementation lives in
`voly/capability/packs.py`; static admission in
`voly/capability/pack_admission.py` adds normalized findings, inferred
permissions, MCP shape validation, and an `allow | quarantine` decision. High
and critical risks quarantine the pack, but discovery still never activates
it. CLI wiring lives in
`voly/cli/commands/capability_cmd.py`.

`voly capability pack` manages inert staged copies:

- `install ecc --source <checkout>` — admission plus atomic staging;
- `list` / `show` — inspect installed manifests;
- `verify <pack-id>` — check manifest and component hashes;
- `remove <pack-id> [--yes]` — delete exactly one staged pack.

Staging copies only admitted components. Quarantined content remains represented
by provenance and hashes but is not copied. No component is activated.

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

**Open-core auth:** `local` (HS256 + password) or auth disabled. Status endpoint
exposes `provider`. **Optional SSO (`clerk`)** is non-default / Team-oriented
and may move out of core later (see `CONTRIBUTING.md`).

**UI:** sign-in modal (local form; Clerk only if status.provider=clerk); token in
`localStorage`; API client attaches Bearer. SSE uses `?access_token=` (GET only).

Code: `voly/web/routes/auth.py`, `voly/web/auth/{jwt,middleware}.py` (+ optional
`clerk.py`), `ui/src/lib/api/client.js`, `ui/src/lib/stores/authStore.svelte.ts`.
Tests: `tests/test_web_auth.py` (core suite does not need Clerk network).

## Operational entrypoints

- `voly serve` — CF-native pipeline runner / worker-oriented flow (`:9202` by default)
- `voly ui` — combined API + UI app (`:7788` by default)
- `voly run` — task execution through pipeline or an executor
- `voly status` and related commands — runtime inspection

Ports are CLI flags (`--port`), not env vars.

## API surface

`docs/backend/api.md` is the canonical endpoint reference. The most important orchestration route is `POST /api/run` (SSE stream). Smart dispatch and A2A behavior are described there and in the pipeline wiki page.

Local Evidence Foundation records are available through
`GET /api/evidence/{task_id}` and explicit feedback through
`POST /api/evidence/{task_id}/feedback`. CLI equivalents are
`voly evidence show` and `voly evidence feedback`. These surfaces contain
local repository observations and comments and must not be exposed beyond the
server's localhost boundary.

Controlled regression suites use `voly eval validate <dataset.json>` and
`voly eval run <dataset.json> [--case <id>]`. The first command validates the
strict versioned schema and fixture boundary. The second replays exact argv in
temporary fixture copies, writes a local `.voly/eval-runs/*.json` report, and
exits non-zero when any expectation fails. It does not call a model provider.

`voly eval calibrate` aggregates completed LLM-judge decisions against their
latest explicit human feedback. It writes a local report with per-lineage
confusion matrices and uncertainty intervals; it never mutates evidence,
thresholds, or routing.

SSE `start` / `done` include `correlation_id` (TaskEvent schema v3). Incoming `X-Correlation-ID` is accepted; otherwise one is generated (`voly/correlation.py`).

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
