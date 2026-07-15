# Configuration and operations

This page collects the runtime configuration, environment, packaging, generated artifacts, and testing guidance that future changes need to respect.

## Configuration files

### `voly.yaml`

Main runtime configuration. It defines model defaults, agent mappings, A2A, AG-UI, spend, registry, scanner, AI Gateway, cost policy, telemetry, DSPy, and **web auth**.

Important patterns in the checked-in template (`voly init` / `voly/config/_template.py`):

- model entries are provider-scoped and use environment variables for API keys
- `default_cwd` is the project root passed to agents and gateway cache scoping
- AI Gateway settings include cache (optional disk persist dir), rate limits, spend limits, fallback, and DLP
- telemetry points to `.voly/events` and optional pipeline/R2 backends
- DSPy can run in shadow or active mode
- `auth` defaults to **disabled** (localhost-only open API)

### Web UI auth

| Field / env | Role |
|---|---|
| `auth.enabled` / `VOLY_AUTH_ENABLED` | Enforce JWT on protected `/api/*` |
| `auth.jwt_secret` / `VOLY_JWT_SECRET` | HMAC secret (required when auth is on) |
| `auth.users` / `VOLY_AUTH_USERS` | `user:pass,user2:pass2` (MVP plaintext map) |
| `auth.cors_origins` / `VOLY_AUTH_CORS` | CORS allow-list; avoid `["*"]` when auth is on |

When auth is enabled and `cors_origins` is still `["*"]`, `create_app()` narrows CORS to localhost defaults (`7788` / `5173`). Public routes: `/api/auth/login`, `/api/auth/status`, `/api/status`, OpenAPI docs. Everything else under `/api/*` needs `Authorization: Bearer <token>`.

Canonical docs: `docs/backend/api.md`, `docs/backend/config.md`.

### `codeops.yaml`

Broader orchestration config at the repo root. Reinforces the project-agnostic theme and lists default agents, gateway settings, spend limits, and runtime services used by the codeops layer.

### `.env.example`

Non-secret sample environment file. Use it to learn which credentials and endpoints the runtime expects — do not commit live secrets. Includes optional `VOLY_AUTH_*` placeholders.

## Packaging (installability)

`pyproject.toml` → `[tool.setuptools] packages` must ship the real source tree for non-editable installs. Core packages that must be listed include:

- `voly.pipeline`, `voly.config`, `voly.cloudflare`
- `voly.web`, `voly.web.auth`, `voly.web.routes`
- `voly.spend`, `voly.runner`, …

`voly.workflow` is **not** packaged (no source files). Guarded by `tests/test_smoke.py::test_setuptools_packages_include_core`.

Optional extras:

- `voly[ui]` — FastAPI, uvicorn, **PyJWT**
- `voly[dspy]`, `voly[dev]`, `voly[cursor]`, …

## Marketplace and local fallback

Skill and plugin catalog paths fall back to local source data when `CF_WORKER_MARKETPLACE_URL` is unset or the remote worker is unavailable.

- `voly/web/routes/marketplace.py` — proxies plugins endpoints or falls back locally
- `voly/registry/external_catalog.py` — local external catalog snapshot from source trees
- `voly/registry/marketplace.py` — plugin list/detail/publish/bulk sync plus skills APIs

Treat the local catalog as a fallback; the worker is the canonical marketplace backend when remote publishing/sync matters.

### Seeding marketplace skills

```bash
voly skill seed                         # builtin_data.py
voly skill seed --path docs/marketplace/skills   # CF scenario drafts (skill-cf-*)
voly skill reindex --page-size 5 --timeout 180   # optional full Vectorize rebuild
```

`POST /skills` also fire-and-forgets Vectorize embeddings per skill. Pipeline stage `SKILL_SUGGEST` uses `SkillScout` (`voly/registry/scout.py`) to surface marketplace skills not installed locally.

Draft CF skills: `docs/marketplace/skills/skill-cf-containers.yaml`, `skill-cf-agent-memory.yaml`, `skill-cf-run-correlation.yaml`.

## Generated runtime state

Do not commit:

- `.voly/events/`
- `.voly/gateway_cache/`
- `.voly/dspy/datasets/`
- `.voly/dspy/programs/`
- `.voly/reports/`
- `.voly/runs/`
- `.venv/`
- `ui/node_modules/`
- `voly/web/static/` (built UI assets)

## Testing and quality gates

`pyproject.toml` / `pytest`:

- tests under `tests/`
- files match `test_*.py`

High-signal suites after control-plane changes:

| Area | Tests |
|---|---|
| Auth | `tests/test_web_auth.py` |
| Gateway spend | `tests/test_ai_gateway.py` (success-only record) |
| Failure paths | `tests/test_failure_paths.py` |
| Packaging | `tests/test_smoke.py::test_setuptools_packages_include_core` |
| Contracts | `tests/test_protocol_contracts.py` (TaskEvent v3 / correlation_id) |
| CF Containers | `tests/test_cf_containers_executor.py` |
| Skill seed / scout | `tests/test_skill_seed_path.py`, `tests/test_skill_scout_cf.py` |

Doc link CI: `scripts/check_doc_links.py`. Env/doc sync: `scripts/check_env_doc_sync.py`.

## Operational guidance

- Treat `AIGateway.chat()` and `TaskEvent` as public contracts.
- Charge spend **only on successful** gateway calls (no `error` in the result).
- Keep config templates, `.env.example`, and `docs/backend/config.md` in sync when adding providers, auth knobs, or remote URLs.
- Do not document or commit real secrets; only placeholders.
- When changing startup behavior, confirm CLI and FastAPI entrypoints still match this wiki and `docs/backend/api.md`.

## Useful source files

- `voly.yaml` / `voly/config/_template.py`
- `codeops.yaml`
- `.env.example`
- `pyproject.toml`
- `voly/config/_types.py` (`AuthConfig`, `VOLYConfig`)
- `voly/web/server.py`
- `tests/`
- `docs/backend/config.md`
- `docs/backend/api.md`
