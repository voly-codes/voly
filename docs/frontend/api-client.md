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

`taskStream()` in `client.js` is `async`: when auth is on, it first calls
`POST /api/tasks/stream-token` (normal Bearer header) to mint a short-lived
stream ticket, then opens the `EventSource` with that ticket in the query
string — the caller's real access token never appears in the URL.

```javascript
const es = await taskStream()
es.onmessage = (e) => {
  const data = JSON.parse(e.data)
  if (data.type === 'new') { /* merge data.tasks */ }
  if (data.type === 'heartbeat') { /* keep-alive, no-op */ }
}
```

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
