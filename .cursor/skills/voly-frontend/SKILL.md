---
name: voly-frontend
description: Guide for working on VOLY Svelte 5 UI — components, API client, styling. Use this skill for any frontend changes in ui/.
---

# VOLY Frontend Development Skill

## Before writing any code — read

| Меняешь | Прочитай |
|---|---|
| Компоненты / структура | `docs/frontend/overview.md` + `docs/frontend/components.md` |
| API вызовы / SSE | `docs/frontend/api-client.md` |
| Новый executor в UI | `docs/frontend/components.md` → "Добавить новый executor" |

## Svelte 5 rules (этот проект использует runes)

```svelte
<!-- ПРАВИЛЬНО — Svelte 5 -->
let { value = $bindable('') } = $props()
let count = $state(0)
let doubled = $derived(count * 2)

<!-- НЕПРАВИЛЬНО — Svelte 4, не использовать -->
export let value = ''
import { createEventDispatcher } from 'svelte'
```

## Styling rules

- Только CSS custom properties из `app.css` — не хардкодить цвета
- `var(--bg-surface)`, `var(--text-primary)`, `var(--border-default)`, `var(--accent-blue)`
- Размеры в px (не rem/em) — проект использует px
- `<style>` блок в каждом компоненте — локальные стили

## Component rules

- Файлы > 200 строк → разбить на подкомпоненты
- Нет business logic в компонентах — только UI
- API вызовы только в top-level компонентах (RunPanel, TaskSidebar)
- Shared компоненты — в `lib/components/shared/`

## Dev flow

```bash
cd ui
npm run dev     # Vite dev server на :5173
# В другом терминале:
voly serve   # backend на :7860
```

Vite проксирует `/api/*` → `localhost:7860` (см. `vite.config.js`).

## Build

```bash
cd ui && npm run build
# Output: voly/web/static/assets/ — НЕ коммитить
```

## Adding executor to UI

1. `RunPanel.svelte` — добавить `{ id: 'my-exec', label: 'My Executor' }` в `executors` массив
   - File-writing executors идут ПЕРЕД text-only
2. `RunParams.svelte` — добавить в `executorHints`:
   ```js
   'my-exec': 'Описание что делает executor'
   ```
3. Обновить `docs/frontend/components.md`

## Documentation requirement (MANDATORY)

После любого изменения:

| Что изменил | Обнови |
|---|---|
| Компонент (добавил/изменил API) | `docs/frontend/components.md` |
| API вызов / SSE формат | `docs/frontend/api-client.md` |
| Структура проекта / стек | `docs/frontend/overview.md` |

## Completion report

После завершения задачи создай отчёт: `/voly-report`
