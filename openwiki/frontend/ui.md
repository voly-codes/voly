# Frontend UI

VOLY's frontend lives in `ui/` and is a Svelte application that visualizes task execution, gateway state, telemetry, Cloudflare-related surfaces, DSPy state, and the marketplace browser. Recent work added a separate plugins tab plus localized English strings for the main dashboards.

## What the UI shows

The main README and component names indicate the UI is organized around these panels:

- task submission and run results
- pipeline inspection and stage progression
- gateway status, spend, cache, and routing state
- telemetry and cost analytics
- DSPy lifecycle and model/program state
- Cloudflare and marketplace surfaces

## App structure

Relevant source files include:

- `ui/src/App.svelte` — top-level app wiring
- `ui/src/lib/components/layout/AppHeader.svelte` — navigation shell
- `ui/src/lib/components/tasks/*` — task execution, results, and inspector panels
- `ui/src/lib/components/gateway/GatewayPage.svelte` — gateway dashboard
- `ui/src/lib/components/telemetry/TelemetryPage.svelte` — telemetry dashboard
- `ui/src/lib/components/dspy/DSPyPage.svelte` — DSPy dashboard
- `ui/src/lib/components/cf/*` — Cloudflare-focused pages, including the skills marketplace and plugins tab
- `ui/src/lib/api/client.js` — browser-side API client

The UI also has i18n files in `ui/src/lib/i18n/` in the current working tree, which suggests localization is being added or updated.

## Runtime shape

The frontend is served in two ways:

- during development via the Vite dev server (`localhost:5173`, proxies API to `:7788`)
- in bundled form through the FastAPI app when built assets are present (`voly ui` on `:7788`)

## Auth and the browser

Backend JWT auth is optional (see [Backend entrypoints](../backend/entrypoints.md)). When `auth.enabled` is true, API calls need a Bearer token from `POST /api/auth/login`. CORS is restricted to configured origins (localhost defaults if misconfigured as `*`). UI work that talks to protected routes must send the token via the API client once login UX is wired.

## What to watch when changing the UI

- Keep UI components aligned with the SSE and JSON shapes returned by the backend.
- Update the API client and component props together.
- Make sure new surfaces are wired into the main navigation, not left as orphaned components.
- Marketplace updates usually touch both `MarketplacePage.svelte` and `PluginsPage.svelte`; verify their API paths stay in sync with `voly/web/routes/marketplace.py` and `voly/registry/marketplace.py`.
- If localization is being extended, keep the translation files and consuming components in sync.
- If auth is enabled in a deployment, confirm the client handles 401 and login flow.

## Useful source files

- `ui/src/App.svelte`
- `ui/src/lib/api/client.js`
- `ui/src/lib/components/*`
- `ui/src/lib/stores/*`
- `docs/frontend/overview.md`
- `README.md`

