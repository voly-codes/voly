# API Client — Frontend Reference

The UI talks to the backend via SSE (Server-Sent Events) and REST.

---

## POST /api/run — SSE stream

Main endpoint for running tasks.

```javascript
const response = await fetch('/api/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    task,
    executor,   // "pipeline" | "claude-code" | "wrangler" | "zen" | ...
    agent,      // "" = auto
    model,      // "" = auto
    cwd,        // path to target project (may be left empty)
    max_turns: 30
  })
})

const reader = response.body.getReader()
// parse SSE events: "data: {...}\n\n"
```

**SSE events:**

```javascript
// Start
{ type: "start", task: "...", executor: "claude-code" }
// Multi-agent dispatch may add a hybrid_warning when hybrid code-gen was
// requested but skipped (e.g. no cwd set) — RunPanel.svelte surfaces this
// as a visible warning banner ("Hybrid code generation skipped...").
{ type: "start", task: "...", executor: "pipeline", a2a: true, hybrid: false,
  cwd: "", hybrid_warning: "hybrid_skipped_no_cwd" }

// Success
{
  type: "done",
  success: true,
  content: "...",           // agent output
  executor: "zen",          // may differ from requested (billing fallback)
  billing_fallback: "zen",  // if fallback occurred
  cost_usd: 0.012,
  duration_ms: 8500,
  num_turns: 5,
  // for pipeline executor:
  agent: "developer",
  model: "claude-sonnet-4-6",
  provider: "anthropic",
  dspy_used: false,
  stage: "DONE"
}

// Error
{ type: "error", error: "claude-code: credit balance is too low" }
```

---

## GET /api/tasks/stream — SSE update stream

`taskStream()` in `client.js` opens a plain `EventSource` to the stream (the
open-core UI has no authentication — auth is a closed Team-tier feature in
voly-cloud). It is `async` to keep a stable signature across distributions.

```javascript
const es = await taskStream()
es.onmessage = (e) => {
  const data = JSON.parse(e.data)
  if (data.type === 'new') { /* merge data.tasks */ }
  if (data.type === 'heartbeat') { /* keep-alive, no-op */ }
}
```

**Polling fallback:** `tasksStore.svelte.ts` (`startStream`) counts consecutive
`onerror` events. The browser's `EventSource` auto-reconnects on its own, but
after 3 straight failures the store stops waiting on it, closes the
connection, and falls back to polling `refresh()` (`GET /api/tasks` +
`/api/tasks/stats/summary` + `/api/status`) every 10s so the task list
doesn't go silently stale. Any successful `onopen`/`onmessage` resets the
failure counter and cancels polling.

---

## GET /api/status

```javascript
const status = await fetch('/api/status').then(r => r.json())
// { version, config: {...}, gateway_ok: true, ... }
```

---

## GET /api/registry/agents

```javascript
const { agents } = await fetch('/api/registry/agents').then(r => r.json())
// agents: ["developer", "reviewer", "architect", "bugfixer", ...]
```

---

## GET /api/models

```javascript
const { models } = await fetch('/api/models').then(r => r.json())
// models: ["claude-sonnet-4-6", "gpt-4o", ...]
```

---

## Provider keys (BYOK)

```javascript
import { fetchProviderKeys, createProviderKey, deleteProviderKey } from '../api/client.js'

const { configured, byok_enabled, keys } = await fetchProviderKeys()
await createProviderKey('anthropic', 'sk-ant-…')          // → {ok, name}
await deleteProviderKey('anthropic')                       // alias 'default'
```

The key value goes straight to the backend → CF Secrets Store and is never
returned by any endpoint. Localhost-only API (403 otherwise).

---

## Run report fields in `done`

Besides `content`/`cost_usd`/`usage`, the executor path returns `report`
(WorkReport: `files_changed/created/deleted`, `summary`, `actions`) and, when
the safety policy acted, `dry_run`, `dry_run_diff`, `safety_violation`,
`safety_rolled_back`. The multi-agent path returns `a2a_assignments` and a
`hybrid` summary. `RunResult.svelte` renders all of them.

---

## Handling billing_fallback in the UI

If `done.billing_fallback` is present — show a badge:

```svelte
{#if result?.billing_fallback}
  <span class="badge warning">
    Fallback: {result.billing_fallback}
  </span>
{/if}
```

---

## CORS / proxy

In development Vite proxies `/api/*` to `http://localhost:7788`:
```javascript
// vite.config.js
proxy: { '/api': 'http://localhost:7788' }
```

In production FastAPI serves SPA and API on the same port (7788).
