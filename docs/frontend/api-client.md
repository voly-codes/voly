# API Client — Frontend Reference

UI общается с backend через SSE (Server-Sent Events) и REST.

---

## POST /api/run — SSE поток

Основной endpoint для запуска задач.

```javascript
const response = await fetch('/api/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    task,
    executor,   // "pipeline" | "claude-code" | "wrangler" | "zen" | ...
    agent,      // "" = auto
    model,      // "" = auto
    cwd,        // путь к целевому проекту (можно оставить пустым)
    max_turns: 30
  })
})

const reader = response.body.getReader()
// parse SSE events: "data: {...}\n\n"
```

**SSE events:**

```javascript
// Начало
{ type: "start", task: "...", executor: "claude-code" }

// Успех
{
  type: "done",
  success: true,
  content: "...",           // вывод агента
  executor: "zen",          // может отличаться от запрошенного (billing fallback)
  billing_fallback: "zen",  // если был fallback
  cost_usd: 0.012,
  duration_ms: 8500,
  num_turns: 5,
  // для pipeline executor:
  agent: "developer",
  model: "claude-sonnet-4-6",
  provider: "anthropic",
  dspy_used: false,
  stage: "DONE"
}

// Ошибка
{ type: "error", error: "claude-code: credit balance is too low" }
```

---

## GET /api/tasks — SSE поток обновлений

```javascript
const es = new EventSource('/api/tasks')
es.onmessage = (e) => {
  const data = JSON.parse(e.data)
  if (data.type === 'init') { tasks = data.tasks }
  if (data.type === 'update') { /* обновить конкретную задачу */ }
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

## Обработка billing_fallback в UI

Если `done.billing_fallback` присутствует — показать бейдж:

```svelte
{#if result?.billing_fallback}
  <span class="badge warning">
    Fallback: {result.billing_fallback}
  </span>
{/if}
```

---

## CORS / proxy

В development Vite проксирует `/api/*` на `http://localhost:7788`:
```javascript
// vite.config.js
proxy: { '/api': 'http://localhost:7788' }
```

В production FastAPI сервирует SPA и API на одном порту (7788).
