# Frontend Overview

UI для VOLY — Svelte 5 SPA в `ui/`. FastAPI сервирует его из `voly/web/static/`
(built assets). В development — Vite dev server на `localhost:5173`.

---

## Стек

- **Svelte 5** — компоненты с `$state()`, `$derived()`, `$props()`, `{#each}`, `{#if}`
- **Vite** — dev server + build (`ui/vite.config.js`)
- **Lucide Svelte** — иконки (`ui/src/lib/icons.js`)
- CSS custom properties — design tokens в `ui/src/app.css`

---

## Структура

```
ui/
  src/
    App.svelte                          # корневой компонент, routing
    app.css                             # CSS переменные + глобальные стили
    main.js                             # точка входа
    lib/
      components/
        layout/
          AppHeader.svelte              # топ-бар с навигацией
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
          RunPanel.svelte               # главная панель запуска задачи
          RunParams.svelte              # параметры: executor, agent, model, cwd
          RunResult.svelte              # вывод результата задачи
          TaskHeader.svelte
          TaskSidebar.svelte
          PipelineStages.svelte         # визуализация стадий pipeline
          PipelineInspector.svelte
          PipelineEmptyState.svelte
          CostPanel.svelte
          StatsOverview.svelte
          WorkReport.svelte
          ExtrasSection.svelte
```

---

## Dev запуск

```bash
cd ui
npm install
npm run dev       # http://localhost:5173
```

Требует запущенного backend: `voly serve` (порт 7860).

---

## Build для production

```bash
cd ui && npm run build
# → voly/web/static/assets/  (не коммитить — генерируется)
```

FastAPI сервирует `voly/web/static/` как static files.

---

## CSS переменные (design tokens)

Все цвета, размеры, радиусы — в `ui/src/app.css`:

```css
--bg-base, --bg-surface, --bg-inset
--text-primary, --text-muted
--border-default, --border-muted
--accent-blue, --accent-green, --accent-red
--radius-sm, --radius-md
```

Тёмная тема по умолчанию. Светлая — через `body.light`.

---

## Svelte 5 паттерны в этом проекте

```svelte
<!-- props с $props() -->
let { executor = $bindable('pipeline'), running = false } = $props()

<!-- state -->
let result = $state(null)

<!-- derived -->
let isRunning = $derived(result?.type === 'running')

<!-- event dispatch -->
function handleRun() { dispatch('run', { task, executor }) }
```

**Не использовать:** `export let`, `createEventDispatcher` (Svelte 4 паттерны) — везде Svelte 5 runes.
