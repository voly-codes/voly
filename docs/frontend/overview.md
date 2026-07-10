# Frontend Overview

VOLY UI — Svelte 5 SPA in `ui/`. FastAPI serves it from `voly/web/static/`
(built assets). In development — Vite dev server on `localhost:5173`.

---

## Stack

- **Svelte 5** — components with `$state()`, `$derived()`, `$props()`, `{#each}`, `{#if}`
- **Vite** — dev server + build (`ui/vite.config.js`)
- **Lucide Svelte** — icons (`ui/src/lib/icons.js`)
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
    App.svelte                          # root component, routing
    app.css                             # CSS variables + global styles
    main.js                             # entry point
    lib/
      components/
        layout/
          AppHeader.svelte              # top bar with navigation
        shared/
          CopyButton.svelte
          StatusDot.svelte
          InfoTooltip.svelte
          Drawer.svelte
          Modal.svelte
          Toast.svelte
          Spinner.svelte
          Skeleton.svelte
        tasks/
          RunPanel.svelte               # main task run panel
          RunParams.svelte              # params: executor, agent, model, cwd
          RunResult.svelte              # task result output
          TaskHeader.svelte
          TaskSidebar.svelte
          PipelineStages.svelte         # pipeline stage visualization
          PipelineInspector.svelte
          PipelineEmptyState.svelte
          CostPanel.svelte
          StatsOverview.svelte
          WorkReport.svelte
          ExtrasSection.svelte
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

<!-- event dispatch -->
function handleRun() { dispatch('run', { task, executor }) }
```

**Do not use:** `export let`, `createEventDispatcher` (Svelte 4 patterns) — Svelte 5 runes everywhere.
