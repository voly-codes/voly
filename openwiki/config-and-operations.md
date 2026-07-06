# Configuration and operations

This page collects the runtime configuration, environment, generated artifacts, and testing guidance that future changes need to respect.

## Configuration files

### `voly.yaml`
This is the main runtime configuration file. It defines model defaults, agent mappings, A2A, AG-UI, spend, registry, scanner, AI Gateway, cost policy, telemetry, and DSPy settings.

Important patterns in the checked-in template:

- model entries are provider-scoped and use environment variables for API keys
- `default_cwd` is the project root passed to agents and gateway cache scoping
- AI Gateway settings include cache, rate limits, spend limits, fallback, and DLP flags
- telemetry points to `.voly/events` and optional pipeline/R2 backends
- DSPy can run in shadow or active mode

### `codeops.yaml`
This repository also has a broader orchestration config file at the root. It reinforces the same project-agnostic theme and includes the default agents, gateway settings, spend limits, and runtime services used by the codeops layer.

### `.env.example`
The repository includes a non-secret sample environment file. Treat it as the place to learn which credentials and endpoints the runtime expects, without reading or committing live secrets.

## Marketplace and local fallback

The recent marketplace work adds both skill and plugin catalog paths that fall back to local source data when `CF_WORKER_MARKETPLACE_URL` is not set or the remote worker is unavailable.

- `voly/web/routes/marketplace.py` proxies `/api/marketplace/plugins` and `/api/marketplace/plugins/sync` to the remote worker when configured, and falls back to local catalog data otherwise.
- `voly/registry/external_catalog.py` builds a local external catalog snapshot from source trees, so the UI can still show plugins even without the worker.
- `voly/registry/marketplace.py` now includes plugin list, detail, publish, and bulk sync calls alongside the existing skill APIs.

Treat the local catalog as a fallback and the worker as the canonical marketplace backend when remote publishing or syncing matters.

## Generated runtime state

The source tree and docs make it clear that several directories are runtime artifacts and should not be committed:

- `.voly/events/`
- `.voly/dspy/datasets/`
- `.voly/dspy/programs/`
- `.voly/reports/`
- `.venv/`
- `ui/node_modules/`

## Testing and quality gates

`pyproject.toml` shows the main Python test configuration:

- tests live under `tests/`
- files match `test_*.py`
- `pytest` uses verbose short-traceback defaults

The repo also contains extensive contract and integration tests for CLI commands, A2A, gateway behavior, telemetry, pipeline behavior, and provider-specific edge cases. These tests are the best guardrails when changing orchestration logic or public contracts.

## Operational guidance

- Treat `AIGateway.chat()` and `TaskEvent` as public contracts.
- Keep config templates in sync with code paths and docs when adding providers, executors, or remote service URLs.
- Be careful not to document or commit real secrets; only describe the expected placeholders.
- When changing startup behavior, confirm the CLI and FastAPI entrypoints still match the documented flow.

## Useful source files

- `voly.yaml`
- `codeops.yaml`
- `.env.example`
- `pyproject.toml`
- `tests/`
- `docs/backend/config.md`
