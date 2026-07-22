# Components — Frontend Reference

## VOLY pixel identity

`PixelGoose.svelte` is the reusable, CSS-token-colored brand mark used by the app header and agent graphs. Graph canvases use a crisp 16 px pixel grid, 3 px square frames, and hard offset shadows derived from `--voly-orange` and `--voly-ink`; keep these surfaces square and respect reduced-motion preferences.

The application shell uses the same system globally: warm paper surfaces, ink structural borders, orange selection/action states, square controls, and hard shadows. Semantic success/warning/error colors remain distinct. New top-level pages should consume the shared tokens in `app.css` instead of introducing cool neutral surfaces or rounded-card styling.

Structural borders use `--frame-strong`, not `--voly-ink`: in dark mode the ink token is intentionally light for artwork and text. Repeating pixel grids are reserved for graph canvases and branded empty states so operational data stays readable on solid surfaces.

---

## RunPanel.svelte

Main task run panel. Contains:
- `<EnvironmentBanner>` — readiness (keys / CLIs / cwd / cloud)
- `<RunParams>` — executor / cwd selection (with directory browse)
- `<RunOptions>` — tier-2 collapsible agent / model / max turns / dry run / repo URL
- `<RunAdvanced>` — tier-3 collapsible a2a mode / timeout / correlation ID
- textarea for task
- `<DiffPreview>` — dry-run unified diff (when `result.dry_run_diff` is set)
- Run button
- `<RunResult>` for output
- `<SkillSuggestModal>` — pre-run marketplace skill gate (Gate 1)
- `<TechSelectionModal>` / `<CategoryPickerModal>` — pre-run tech stack gate (Gate 2)

**Gate 1 — skills:** on Run / Ctrl+Enter, calls
`GET /api/marketplace/skills/suggest`. If missing skills are found, opens a modal
to Install / Install all / wait for install / then **Run with skills**, or
**Skip & run**. If suggest fails or returns `[]`, the flow continues to Gate 2.

**Gate 2 — tech stack:** for `pipeline` / `claude-code` / `cursor` executors,
calls `detectTech(task, cwd)` (`POST /api/tech/detect`). If frameworks are
detected, opens `TechSelectionModal`; if nothing is detected, opens
`CategoryPickerModal` (pick a category → `TechSelectionModal` with its entries).
The confirmed stack is sent as `tech_stack` in `POST /api/run` and shown as
chips in the running status bar. If detection fails, the run starts without a
stack. Skipping either modal starts the run.

**Executor order** (`pipeline` default first, then file-writing, text-only last):
```
pipeline → claude-code → wrangler → cf-containers → zen → cursor → opencode → deepseek → workers-ai → cloudflare-dynamic
```

**Props:** `onTaskComplete` (callback fired on the `done` SSE event).
Agents / models are fetched by the panel itself (`fetchAgents` / `fetchModels`)
and passed down to `RunOptions`.

**Run options state:** `max_turns` (default 40), `dry_run`, `repo_url`,
`a2a_mode`, `timeout_s` (default 120), `correlation_id`. Non-default values
are included in `POST /api/run` (`timeout_s` is sent as `timeout`).

**Events:** SSE stream from `POST /api/run` — types: `start`, `done`, `error`.
A `start` event carrying `hybrid_warning` is rendered as a visible amber
warning banner (e.g. "Hybrid code generation skipped (no cwd set)...").

**Auto-fill cwd:** on component mount, if `cwd` is empty, requests `GET /api/status` and fills in `default_cwd` (from `voly.yaml` or `VOLY_PROJECT_CWD`).

**Environment:** on mount (and when cwd changes) calls `GET /api/environment?cwd=…`,
passes `executors` map into `RunParams`, and shows tips via `EnvironmentBanner`.

---

## SkillSuggestModal.svelte

Modal shown before a run when marketplace has relevant skills not installed locally.

**Props:** `open` (bindable), `suggestions`, `installing` (bindable), `onRun`, `onSkip`.

**Actions:** Install / Install all (waits for each install), Run with skills, Skip & run.
Blocks closing while an install is in progress.

---

## TechSelectionModal.svelte

Pre-run tech gate: pin exact framework/library versions so agents don't guess
or auto-upgrade. Entries are grouped by category
(frontend / backend / language / build / testing / database / infra), each with
a version `<select>` (first option marked `latest`).

**Props:** `open` (bindable), `detected` (entries from `POST /api/tech/detect`
or a category pick), `onConfirm(selections)`, `onSkip`.

**Preflight:** on open, calls `techPreflight(names)`
(`POST /api/tech/preflight`) and shows an amber **not installed** badge on
entries whose runtime binary (python3, node, docker, …) is missing from
`PATH` — warns only, never blocks the run.

**Keys:** Escape = skip, Ctrl/Cmd+Enter = confirm.

---

## CategoryPickerModal.svelte

Fallback for Gate 2 when tech detection returns nothing (e.g. "create a 2D
tank game"). Loads `GET /api/tech/categories` and shows a card grid
(Web / Backend / Game / CLI / Data). Picking a category hands its pre-resolved
tech entries to `TechSelectionModal`; Skip starts the run without a stack.

**Props:** `open` (bindable), `onPick(entries)`, `onSkip`.

**Keys:** Escape = skip, Ctrl/Cmd+Enter = pick.

---

## EnvironmentBanner.svelte

Light readiness strip above run params. Props: `report`, `loading`, `onRefresh`.
Does not block Run. Expandable tips for `warn`/`error` checks; Recheck / Dismiss.

---

## RunParams.svelte

Tier-1 run parameters. Passes `$bindable` values to the parent.

```svelte
let {
  executor = $bindable('pipeline'),
  cwd = $bindable(''),
  task = '',
  executors = [],
  running = false,
  executorAvailability = {},  // from GET /api/environment
} = $props()
```

Executor `<option>` labels append `✓` or `— not installed` from `executorAvailability`.

**Working dir browse:** **Browse** calls `GET /api/browse?path=<cwd>` (empty cwd
lists server cwd). Shows a dropdown of returned directories; selecting one sets
`cwd`. Errors hide the dropdown silently.

**Executor hints** — `executorHints` map shows a hint under the selected
executor (all ids covered: `pipeline`, `claude-code`, `wrangler`,
`cf-containers`, `zen`, `cursor`, `opencode`, `deepseek`, `workers-ai`,
`cloudflare-dynamic`), e.g.:
- `pipeline`: "AI Gateway — cache, DLP, spend control (text only)"
- `claude-code`: "Claude Code CLI — reads/writes files · billing fallback → wrangler → zen"
- `cf-containers`: "Cloudflare Containers via sandbox-spike — needs VOLY_CF_CONTAINERS_URL + JWT"

**Working dir:** always visible (not hidden for pipeline) — smart dispatch needs cwd even for pipeline.
Hint: `cwd ? 'executor writes here' : 'leave empty for text-only'`

**Capability routing:** `<CapabilityPreview>` renders below the executor hint when the
local capability registry has profiles. Debounces task text (600ms) and calls
`POST /api/capability/match`. Shows best match score, optional **[Use]** to swap
executor, and up to two fallback chips.

Props include `task = ''` (from `RunPanel`).

---

## CapabilityPreview.svelte

Compact inline capability match bar under the executor select.

**Props:** `task`, `executor`, `dimension` (default `'backend'`), `onUse` callback.

**Behavior:** On mount, checks `GET /api/capability/profiles` — hidden when the
registry is empty. When `task` changes (600ms debounce), calls
`matchCapability(dimension, executor ? [executor] : undefined)`. Hidden while
loading or when the API returns no `recommended`. Shows best match with ⚡ icon,
**[Use]** when the recommendation differs from the current executor, and up to
two fallback score chips.

**Events:** `onUse(executor_id)` — parent sets the executor binding.

---

## RepoAnalyzeCard.svelte

Repository intelligence card for the Run options repo URL field.

**Props:** `repo_url` (bindable), `running` (disables controls when true).

**Behavior:** **[Analyze]** calls `analyzeRepo(repo_url)` (`POST /api/repo/analyze`).
Shows a spinner while loading. On success, displays languages, frameworks, license
(`spdx` + risk), security issue count, and maintainability score. On error, shows
a muted red message.

---

## RunOptions.svelte

Tier-2 collapsible panel (collapsed by default). Persists expand state in
`localStorage` key `voly_run_options_open`.

```svelte
let {
  agent = $bindable(''),
  model = $bindable(''),
  max_turns = $bindable(40),
  dry_run = $bindable(false),
  repo_url = $bindable(''),
  agents = [],
  models = [],
  running = false,
} = $props()
```

Toggle label: `Options ▸` / `Options ▾`. When expanded, a 3-column grid shows
agent selector (empty = auto), model selector (empty = auto), max turns
(1–100), dry-run checkbox, repo URL input, and `<RepoAnalyzeCard>` below the
repo URL field. All controls disabled when `running=true`.

---

## RunAdvanced.svelte

Tier-3 collapsible panel (strictly collapsed by default). Persists expand state
in `localStorage` key `voly_run_advanced_open`.

```svelte
let {
  a2a_mode = $bindable(''),
  timeout_s = $bindable(120),
  correlation_id = $bindable(''),
  running = false,
} = $props()
```

Toggle label: `Advanced ▸` / `Advanced ▾` (small, muted). When expanded:
`a2a_mode` text input (placeholder `auto`), `timeout_s` number input (60–600),
`correlation_id` text input (placeholder `leave blank = auto`). Disabled when
`running=true`.

---

## DiffPreview.svelte

Renders a dry-run unified diff from the `done` SSE payload.

**Props:** `diff` — unified diff string or `null` (renders nothing when empty).

**Parsing:** splits on `---` file headers; filename from `+++ b/…` (fallback
`--- a/…`). One collapsible section per file with a file-count badge in the
header.

**Colors (monospace):**

| Line prefix | Style |
|---|---|
| `+` (not `++`) | background `#1a3320`, text `#4ade80` |
| `-` (not `--`) | background `#3a1a1a`, text `#f87171` |
| `@@` | text `#9ca3af` |
| context | default text color |

Each file body scrolls independently (`max-height: 400px`).

---

## RunResult.svelte

The run report screen — shell that composes focused subcomponents for the
`done` SSE payload:

| Component | Renders |
|---|---|
| `RunResultHeader.svelte` | chips (agent/model/executor/status/dry-run/safety/fallback/corr) + stats |
| `BillingChainTimelog.svelte` | per-attempt billing chain (executor / model / status / duration) |
| `MultiAgentPanel.svelte` | A2A role rows + hybrid summary (executor/chat counts, files) |
| `SkillSuggestBanner.svelte` | marketplace skill install suggestions |
| `WorkReport` / `PxpipeArtifacts` | files report + artifacts (existing) |

Also in the shell: `safety_rolled_back` note, dry-run diff preview, tech stack
chips (`result.tech_stack`, above skills in the footer), a "New project created
at …" notice when a greenfield cwd was scaffolded (`result.greenfield` +
`result.project_dir`), injected skills, content, error.

---

## PipelineInspector.svelte

Selected-task card (from `tasksStore.selected`). Shell layout + composition:

| Piece | Role |
|---|---|
| `pipelineStageModel.js` | `buildPipelineStages` / `buildTokenBar` from TaskEvent |
| `InspectorAgentsList.svelte` | multi-agent role rows (duration, plan status, errors) |
| `InspectorBillingChain.svelte` | vertical billing-chain timeline |
| `InspectorMetaSections.svelte` | gateway / billing / DSPy / metadata extras |

Also uses existing `TaskHeader`, `PipelineStages`, `StatsOverview`, `WorkReport`.

**Report / Agent atlas tabs:** below `TaskHeader`, a tab bar switches the whole
inspector body between:
- **Report** (`activeTab === 'report'`) — the `inspector-body` described above,
  unchanged.
- **Agent atlas** (`activeTab === 'atlas'`) — renders `AgentAtlas.svelte`.

`activeTab` resets to `'report'` whenever `task.task_id` changes (an
`$effect`), so switching tasks never leaves a stale atlas tab open.

## PipelineStages.svelte

Pipeline stage visualization for text-only tasks:
```
INIT → ROUTE → RTK → SKILL → HEADROOM → DSPY → MODEL → DONE
```
Each stage is a colored badge. A failed stage is highlighted red.

---

## TaskSidebar.svelte

One unified list of completed and running tasks. Completed records arrive from
`GET /api/tasks`/SSE; root `RunRecord`s are merged into the same store every two
seconds and inserted immediately from `/api/run`'s `start` event. A running row
has one role/running label. Click loads the live record into
`PipelineInspector`; there is no separate "In progress" section.

The selected live task updates in place from RunTracker heartbeats. Its shared
`LiveAgentGraph` exposes agent assignment, skills, routing, files, plan stages
and status. When execution finishes, the TaskEvent with the same `task_id`
replaces the live shape without creating a second row.

**Collapse toggle:** header chevron button sets `ui.sidebarCollapsed = true`;
collapsed state renders a 22px strip with a single expand button (state lives
in `uiStore`, not local — survives navigation away from the tasks page).

---

## TaskHeader.svelte

Header of the task card inside `PipelineInspector`: task id, status badge
(`completed` / `partial` / `failed` / `running`), meta badges (agent, model,
provider, executor, type), top-level `task.error`, and live progress.

For multi-agent tasks (`task.a2a_dispatched` + `a2a_assignments`) it renders
`RoleStrip` so a `partial` status is explainable at a glance.

## RoleStrip.svelte

Props: `assignments` (the `a2a_assignments` array from the TaskEvent).
Compact per-role chips — green/red dot, role name, `duration_ms` — plus a red
error line for every failed role (truncated to ~90 chars, full text in the
`title` tooltip). Used by `TaskHeader`.

`PipelineInspector`'s multi-agent section also shows per-role `duration_ms`
and an error line under failed agent rows.

---

## WorkReport.svelte

Shows `work_report` from ExecutorResult:
- `files_created` — green
- `files_changed` — blue
- `files_deleted` — red
- `actions` — list of performed actions
- `summary` — brief description

---

## CostPanel.svelte

Shows cost_usd, input_tokens, output_tokens, automation_score.
Data from the `done` SSE event.

**Collapse toggle:** header chevron sets `ui.costPanelCollapsed = true`; same
collapsed-strip pattern as `TaskSidebar`.

---

## AgentAtlas.svelte

Hub-and-spoke view of the agents that worked a task: a dashed "Task" hub node
on top, one card ("spoke") per agent below, connected by a plain CSS
vertical-tick pattern (no layout library — the current a2a fan-out is small
enough that a real graph-layout engine, e.g. ELK.js as used by `system-atlas`,
isn't justified yet).

**Props:** `task` (a `TaskEvent`-shaped object; same shape `PipelineInspector`
already reads).

**Node source:**
- `task.a2a_dispatched && task.a2a_assignments.length` → one node per
  assignment (role, tier, mode, executor/provider/model, plan_status,
  files_touched, cache_hit, mem_hits, skills, duration_ms, cost_usd, error).
- otherwise → a single synthetic node built from the top-level task fields
  (`agent`/`executor`/`provider`/`model`/`report.files_*`/`gateway.cache_hit`),
  so single-agent tasks (the overwhelming majority locally — see below) still
  render a one-node atlas instead of an empty view.

Clicking a spoke toggles a detail panel below the graph: **Properties**
(executor/provider/model/tier/mode/plan) and **Metrics**
(duration/cost/cache/memory) columns, plus files-touched list, skill chips,
and the role's error text if it failed. Click the same node again to close.

Summary strip above the graph: role count, ok/failed counts, `task.cost_usd`,
`task.duration_ms` (read from the task directly, not summed from nodes, so it
stays correct regardless of how the roles overlapped in time).

`PipelineInspector` keeps this view for normal single-agent and A2A fan-out
runs. A task whose `workflow` is `review-until-clean` is routed to the directed
`WorkflowGraph` instead, because its developer/reviewer dependency is cyclic
and a hub-and-spoke diagram would be misleading.

## WorkflowGraph.svelte and WorkflowTimeline.svelte

Directed live/final view for the bounded review workflow. It renders the two
runtime roles and both causal edges: implementation flows Developer → Reviewer,
and blocking findings flow Reviewer → Developer on a repair lap. The active
node and edge are highlighted; the summary shows lap/max laps, latest verdict,
explicit stop reason, total duration, and total cost.

Final SSE results use `laps` for per-role executor/provider/model, duration,
cost, files touched, and errors. Live `/api/runs` records may not have completed
lap metrics yet, so unavailable values remain visibly empty rather than being
estimated. `WorkflowTimeline` lists every transition with lap and reason and
ends with the workflow stop reason. `RunResult.svelte` embeds the same compact
view for the immediate final SSE response.

`RunAdvanced.svelte` exposes the explicit workflow selector plus bounded
`max_rounds` (1–20) and `deadline_seconds` (60–3600). A review workflow requires
a working directory and ignores dry-run mode because its purpose is to perform
and verify real repairs.

## LiveAgentGraph.svelte

The default inspector canvas for a live parent run with `graph_nodes`. It is a
single, scrollable directed graph for the whole run—not one flow per agent.
Stable node ids are updated in place on every poll; an executor child never
becomes a second canvas.

`agentGraphModel.js` lays out dependency DAGs in columns and gives a cyclic
workflow a deterministic left-to-right fallback. Each node shows live status,
executor/provider/model route, duration, cost, touched-file count, and error.
The most recent causal transition (or the edge entering a running node) is
animated. Reduced-motion preferences disable the signal animation. Live graph
runs open directly on the Agent atlas tab; historical/single-agent tasks remain
report-first and retain `AgentAtlas.svelte`.

The canvas borrows a restrained subset of the public `voly_web` identity:
brand orange `#DD7454`, paper/ink color mixing, square pixel markers, crisp
two-pixel borders, and offset non-blurred shadows. The active dependency uses a
stepped orange pixel signal. Semantic success/failure colors remain unchanged,
and dark mode remaps the paper/ink tokens instead of forcing the landing page's
light palette onto the dashboard.

The same always-visible identity anchors are applied to `AppHeader`,
`TaskHeader`, the Report/Agent atlas tabs, `AgentAtlas`, and the final
`WorkflowGraph`. This ensures the VOLY styling is visible before a live run
starts; `LiveAgentGraph` is the animated extension of that shared language, not
the only branded surface.

---

## CFPage.svelte

Cloudflare Workers status + Spend Tracker summary (`cf/CFPage.svelte`).
`/api/cf/spend/summary` must send `CF_WORKER_SPEND_TOKEN`; when the token is
missing or returns 401, the page shows `spend.error` / `hint` instead of a
silent `$0.0000` total.

## ProviderKeysPanel.svelte

BYOK provider keys section on the CF page (`cf/ProviderKeysPanel.svelte`,
mounted at the bottom of `CFPage.svelte`). Masked (`type=password`) input +
provider select (anthropic / openai / google-ai-studio / deepseek), list of
stored key names with delete. Talks to `/api/providers/keys`; shows the
`byok_enabled` state and a setup hint when CF credentials are missing. The key
value is sent once on save and never rendered back.

---

## Other pages

| Component | Role |
|---|---|
| `cf/MarketplacePage.svelte` | Skill catalog: browse / search / install marketplace skills |
| `cf/PluginsPage.svelte` | Marketplace plugins list (`GET /api/marketplace/plugins`), search + configured/hint states |
| `dspy/DSPyPage.svelte` | DSPy programs and lifecycle (`/api/dspy/*`) |
| `telemetry/TelemetryPage.svelte` | Spend analytics: daily, by_agent, by_model |

---

## Shared components

| Component | Purpose |
|---|---|
| `StatusDot` | colored dot: green/amber (partial)/red/gray |
| `CopyButton` | copy text to clipboard |
| `InfoTooltip` | `?` button with tooltip |
| `Drawer` | slide-in side panel |
| `Modal` | dialog window |
| `Toast` | top notification |
| `Spinner` | loading indicator |
| `Skeleton` | loading skeleton |

---

## GatewayPage.svelte

AI Gateway dashboard (`GET /api/gateway/status` + provider health). Shell loads
data; UI is split into:

| Component | Role |
|---|---|
| `GatewayStatusBar.svelte` | enabled/disabled banner + refresh |
| `GatewayMetricCards.svelte` | cache / rate / spend / fallback / DLP / errors cards |
| `GatewayTotals.svelte` | requests / tokens / cost / rpm chips |
| `GatewayBreakdown.svelte` | by-provider / by-model bars + health bricks |

## AppHeader.svelte

Top navigation: logo, links to Tasks / Agents / Models / Spend.
Active section — `--accent-blue`.

---

## Adding a new executor to the UI

1. `RunPanel.svelte` — add to the executors array (file-writing before text-only)
2. `RunParams.svelte` — add `executorHints[id]` with a description
3. Update this file

Cloud-native executor already wired in: `cf-containers` (Cloudflare Containers /
sandbox-spike, requires `VOLY_CF_CONTAINERS_URL` + JWT).

## Correlation ID

- Open-core: `RunResult.svelte` shows a clickable `corr …` chip when SSE `done` includes `correlation_id` (copy to clipboard).
- Hosted dashboard: run detail page shows Correlation ID with copy control (`CopyCommand`).
