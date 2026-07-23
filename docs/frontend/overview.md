# Frontend Overview

VOLY UI — Svelte 5 SPA in `ui/`. FastAPI serves it from `voly/web/static/`
(built assets). In development — Vite dev server on `localhost:5173`.

---

## Stack

- **Svelte 5** — components with `$state()`, `$derived()`, `$props()`, `{#each}`, `{#if}`
- **Vite** — dev server + build (`ui/vite.config.js`)
- **Lucide Svelte** — icons (`ui/src/lib/icons.ts`, imported as `../../icons.js`)
- CSS custom properties — design tokens in `ui/src/app.css`
- **i18n** — English default + Russian (`ui/src/lib/i18n/`), switcher in header, `localStorage` key `voly-lang`

### Languages

| Locale | Role | Catalog |
|---|---|---|
| `en` | **default** | `ui/src/lib/i18n/en/*.js` |
| `ru` | optional | `ui/src/lib/i18n/ru/*.js` |

```js
import { i18n, t } from './lib/i18n/localeStore.svelte.ts'
t('nav.tasks')           // "Tasks" | "Задачи"
i18n.set('ru')           // switch
i18n.locale              // 'en' | 'ru'
```

---

## Structure

```
ui/
  src/
    App.svelte                          # root component, hash routing
    app.css                             # CSS variables + global styles
    main.js                             # entry point
    lib/
      api/
        client.js                       # all REST/SSE calls (see api-client.md)
      icons.ts                          # Lucide icon re-exports
      i18n/                             # en/ (default) + ru/ catalogs, localeStore
      stores/                           # routerStore, tasksStore, themeStore, toastStore, uiStore
      utils/                            # format.js, keyboard.js, liveTask.js
      components/
        layout/
          AppHeader.svelte              # top bar with navigation
        shared/
          CopyButton / StatusDot / InfoTooltip / Drawer /
          Modal / Toast / Spinner / Skeleton
        tasks/
          RunPanel.svelte               # main task run panel + pre-run gates
          RunParams.svelte              # params: executor, agent, model, cwd
          EnvironmentBanner.svelte      # readiness strip (keys / CLIs / cwd)
          SkillSuggestModal.svelte      # Gate 1: marketplace skill suggestions
          TechSelectionModal.svelte     # Gate 2: pin tech versions + runtime preflight
          CategoryPickerModal.svelte    # Gate 2 fallback: pick project category
          RunResult.svelte              # result shell (+ RunResultHeader / BillingChainTimelog /
                                        #   MultiAgentPanel / SkillSuggestBanner / PxpipeArtifacts)
          TaskHeader.svelte             # task card header (+ RoleStrip)
          TaskSidebar.svelte
          PipelineStages.svelte         # pipeline stage visualization
          PipelineInspector.svelte      # shell (+ InspectorAgentsList / InspectorBillingChain /
                                        #   InspectorMetaSections + pipelineStageModel.js)
          PipelineEmptyState.svelte
          CostPanel.svelte
          StatsOverview.svelte
          WorkReport.svelte
          ExtrasSection.svelte          # collapsible section wrapper
        gateway/
          GatewayPage.svelte            # status shell (+ GatewayStatusBar / GatewayMetricCards /
                                        #   GatewayTotals / GatewayBreakdown)
        cf/
          CFPage.svelte                 # CF workers + spend (+ ProviderKeysPanel)
          MarketplacePage.svelte        # skill catalog
          PluginsPage.svelte            # marketplace plugins
        dspy/
          DSPyPage.svelte
        telemetry/
          TelemetryPage.svelte
```

---

## Dev startup

```bash
cd ui
npm install
npm run dev       # http://localhost:5173
```

Requires a running backend: `voly ui` (port 7788).

---

## Production build

```bash
cd ui && npm run build
# → voly/web/static/assets/  (do not commit — generated)
```

FastAPI serves `voly/web/static/` as static files.

---

## CSS variables (design tokens)

All colors, sizes, radii — in `ui/src/app.css`:

```css
--bg-base, --bg-surface, --bg-inset
--text-primary, --text-muted
--border-default, --border-muted
--accent-blue, --accent-green, --accent-red
--radius-sm, --radius-md
```

Dark theme by default. Light — via `body.light`.

---

## Svelte 5 patterns in this project

```svelte
<!-- props with $props() -->
let { executor = $bindable('pipeline'), running = false } = $props()

<!-- state -->
let result = $state(null)

<!-- derived -->
let isRunning = $derived(result?.type === 'running')

<!-- events via callback props (no createEventDispatcher) -->
let { onConfirm = undefined } = $props()
function confirm() { onConfirm?.(selections) }
```

**Do not use:** `export let`, `createEventDispatcher` (Svelte 4 patterns) — Svelte 5 runes everywhere.
