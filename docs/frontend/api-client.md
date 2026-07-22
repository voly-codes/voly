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
    max_turns: 30,
    tech_stack: []  // confirmed entries from the tech gate (may be empty)
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

## GET /api/environment

Local readiness (provider keys, CLI on `PATH`, cwd, optional cloud link).

```javascript
import { fetchEnvironment } from '../api/client.js'

const report = await fetchEnvironment('/path/to/project')
// { ready, summary, checks[], executors{}, providers_configured[], default_cwd }
```

Used by `EnvironmentBanner` + executor badges in `RunParams`. See `docs/backend/api.md`.

---

## GET /api/registry/agents

```javascript
const { agents } = await fetch('/api/registry/agents').then(r => r.json())
// agents: ["developer", "reviewer", "architect", "bugfixer", ...]
```

The backend sources this ordered list from comma-separated `VOLY_ROLES` when
configured, otherwise from the runtime agent registry.

---

## GET /api/registry/models

```javascript
import { fetchModels } from '../api/client.js'

const { models } = await fetchModels('pipeline')
// GET /api/registry/models?executor=pipeline
// models: ["claude-sonnet-4-6", "gpt-4o", ...]  (filtered per executor)
```

The backend first checks `VOLY_MODELS_<EXECUTOR>` (for example,
`VOLY_MODELS_CLOUDFLARE_DYNAMIC`), then shared `VOLY_MODELS`, then its runtime
model catalog. Values are comma-separated.

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

## In-flight runs

```javascript
import { fetchRuns, fetchRun } from '../api/client.js'
const { runs, active } = await fetchRuns(true)   // active only
const rec = await fetchRun(taskId)               // single RunRecord
await cancelRun(taskId)                          // cooperative workflow cancel
```

Polled by `ActiveRuns.svelte` (4s) — no SSE; records update via RunTracker
heartbeats on disk.

`GET /api/runs` returns only root records by default. Pass
`include_children=1` for diagnostics; child executor records carry
`parent_task_id`. Root records expose `graph_nodes` and `graph_edges`, which are
updated in place and rendered as one `LiveAgentGraph` while agents work.

Workflow records additionally expose `workflow`, `lap`, `max_laps`,
`active_role`, `latest_verdict`, `stop_reason`, `cancel_requested`, and a
causal `timeline`. Completed records also have `workflow_metrics` for rollout
analysis. `liveTaskFromRun()` carries these fields into the selected
task shape so `PipelineInspector` can render the directed graph. Cancellation
uses `POST /api/runs/{task_id}/cancel` and is available only for an active
workflow record.

To start the bounded review loop, `RunPanel` adds these fields to `POST /api/run`:

```javascript
{
  workflow: 'review-until-clean',
  max_rounds: 3,
  deadline_seconds: 900,
  cwd: '/absolute/project/path'
}
```

The final SSE event includes `workflow`, `stop_reason`, aggregate cost/duration,
and `laps`. Each lap separates `developer_cost_usd` and `reviewer_cost_usd` so
the graph does not infer or double-count per-role spend.

---

## Run report fields in `done`

Besides `content`/`cost_usd`/`usage`, the executor path returns `report`
(WorkReport: `files_changed/created/deleted`, `summary`, `actions`) and, when
the safety policy acted, `dry_run`, `dry_run_diff`, `safety_violation`,
`safety_rolled_back`. The multi-agent path returns `a2a_assignments` and a
`hybrid` summary. `RunResult.svelte` renders all of them.

Single-model and local multi-agent paths may also include `skill_suggestions`
(marketplace skills not installed locally) — shown as a post-run install banner
in `RunResult.svelte`.

Both paths echo `tech_stack` (the confirmed stack from the tech gate, rendered
as chips in the result footer) and `greenfield` — `true` when the cwd did not
exist and was scaffolded (mkdir + `git init` + stack-aware `.gitignore` +
initial commit); then `project_dir` carries the created path and
`RunResult.svelte` shows a "New project created at …" notice.

---

## Marketplace skills (pre-run gate)

```javascript
import { suggestSkills, installSkill } from './api/client.js'

// Before POST /api/run — RunPanel skill gate
const { suggestions, configured } = await suggestSkills(task, 5)
// GET /api/marketplace/skills/suggest?task=…&limit=5

await installSkill(skillId)
// POST /api/marketplace/skills/{id}/install
```

If `suggestions.length > 0`, `SkillSuggestModal` opens: install (wait) → Run,
or Skip & run. Suggest failures do not block the run.

---

## Tech stack gate (pre-run)

```javascript
import { detectTech, techPreflight, fetchTechCategories } from './api/client.js'

// Gate 2 in RunPanel (pipeline / claude-code / cursor executors)
const { detected } = await detectTech(task, cwd)
// POST /api/tech/detect → detected: [{ name, label, category, version, versions, notes }]

// TechSelectionModal: which runtimes exist as system binaries (python3, node, docker…)
const { available } = await techPreflight(['python', 'node'])
// POST /api/tech/preflight → { available: { python: true, node: false } }

// CategoryPickerModal: fallback when nothing was detected
const { categories } = await fetchTechCategories()
// GET /api/tech/categories → [{ id, label, description, entries[] }]
```

The confirmed selection is sent as `tech_stack` in `POST /api/run`; the backend
prepends a "use these exact versions" constraint block to the task and echoes
`tech_stack` in the `done` event. `GET /api/tech/registry` exposes the full
registry (used by external consumers / the CF Worker mirror, not the UI).
All tech-gate failures are non-blocking — the run proceeds without a stack.

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

## Other endpoints used by pages

| `client.js` helper | Endpoint | Used by |
|---|---|---|
| `fetchTasks` / `fetchTask` / `fetchSummary` | `GET /api/tasks`, `/api/tasks/{id}`, `/api/tasks/stats/summary` | `tasksStore`, `TaskSidebar` |
| `fetchSkills` | `GET /api/registry/skills` | registry views |
| `fetchInstalledSkills` / `fetchMarketplaceSkills` / `searchMarketplace` | `GET /api/marketplace/skills/*` | `MarketplacePage` |
| `fetchMarketplacePlugins` / `publishMarketplacePlugins` | `GET /api/marketplace/plugins`, `POST …/plugins/sync` | `PluginsPage` |
| `fetchGatewayStatus` / `fetchProviderHealth` | `GET /api/gateway/status`, `/api/providers/health` | `GatewayPage` |
| `fetchTelemetry` | `GET /api/telemetry/summary?days=…` | `TelemetryPage` |
| `fetchCFWorkersStatus` / `fetchCFSpend` | `GET /api/cf/workers/status`, `/api/cf/spend/summary` | `CFPage` |
| `fetchDSPyStatus` | `GET /api/dspy/status` | `DSPyPage` |

---

## CORS / proxy

In development Vite proxies `/api/*` to `http://localhost:7788`:
```javascript
// vite.config.js
proxy: { '/api': 'http://localhost:7788' }
```

In production FastAPI serves SPA and API on the same port (7788).
