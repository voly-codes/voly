# Components — Frontend Reference

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

## PipelineStages.svelte

Pipeline stage visualization for text-only tasks:
```
INIT → ROUTE → RTK → SKILL → HEADROOM → DSPY → MODEL → DONE
```
Each stage is a colored badge. A failed stage is highlighted red.

---

## ActiveRuns.svelte

"In progress" block at the top of `TaskSidebar`: polls `/api/runs?active=1`
every 4s and lists runs that are still executing (including CLI-launched
ones) — task text, current role/executor, progress `done/total`, elapsed.
Click opens the live task card in `PipelineInspector` (via `tasksStore.selectLive`)
and expands a drill-down: task id, heartbeat age (red when >60s), role
chips (done/current), plan `step_statuses`, error. While the card is open,
poll patches progress in place. When the last active run finishes, the store
refreshes and the completed TaskEvent replaces the live card.

## TaskSidebar.svelte

List of previous tasks. Data from `GET /api/tasks` (SSE).
Click — loads the task into `PipelineInspector`.
In-flight rows from the Run drawer (`ui.activeRuns`) are clickable: resolve to
a server `/api/runs` record when possible and open the live card; otherwise
re-open the Run drawer.

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
