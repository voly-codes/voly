# Frontend UI

VOLY's frontend lives in `ui/` and is a Svelte application that visualizes task execution, gateway state, telemetry, Cloudflare-related surfaces, and DSPy state.

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
- `ui/src/lib/components/cf/*` — Cloudflare-focused pages
- `ui/src/lib/api/client.js` — browser-side API client

The UI also has i18n files in `ui/src/lib/i18n/` in the current working tree, which suggests localization is being added or updated.

## Runtime shape

The frontend is served in two ways:

- during development via the Vite dev server
- in bundled form through the FastAPI app when built assets are present

## What to watch when changing the UI

- Keep UI components aligned with the SSE and JSON shapes returned by the backend.
- Update the API client and component props together.
- Make sure new surfaces are wired into the main navigation, not left as orphaned components.
- If localization is being extended, keep the translation files and consuming components in sync.

## Useful source files

- `ui/src/App.svelte`
- `ui/src/lib/api/client.js`
- `ui/src/lib/components/*`
- `ui/src/lib/stores/*`
- `README.md`
