# Components — Frontend Reference

---

## RunPanel.svelte

Main task run panel. Contains:
- textarea for task
- `<RunParams>` — executor / agent / model / cwd selection
- Run button
- `<RunResult>` for output

**Executor order** (file-writing first, text-only last):
```
claude-code → wrangler → zen → cursor → opencode → pipeline → deepseek → workers-ai → cloudflare-dynamic
```

**Props:** `config`, `agents`, `models`

**Events:** SSE stream from `POST /api/run` — types: `start`, `done`, `error`.
A `start` event carrying `hybrid_warning` is rendered as a visible amber
warning banner (e.g. "Hybrid code generation skipped (no cwd set)...").

**Auto-fill cwd:** on component mount, if `cwd` is empty, requests `GET /api/status` and fills in `default_cwd` (from `voly.yaml` or `VOLY_PROJECT_CWD`).

---

## RunParams.svelte

Run parameters. Passes `$bindable` values to the parent.

```svelte
let {
  executor = $bindable('pipeline'),
  agent = $bindable(''),
  model = $bindable(''),
  cwd = $bindable(''),
  executors = [],
  running = false
} = $props()
```

**Executor hints** — hint under each executor:
- `pipeline`: "AI Gateway — cache, DLP, spend control (text only)"
- `claude-code`: "Claude Code CLI — reads/writes files · billing fallback → wrangler → zen"
- `wrangler`: "CF Workers AI via wrangler dev — writes files via LocalPatchApplier"
- `zen`: "OpenCode Zen — free tier, file-capable via opencode CLI"

**Working dir:** always visible (not hidden for pipeline) — smart dispatch needs cwd even for pipeline.
Hint: `cwd ? 'executor writes here' : 'leave empty for text-only'`

---

## RunResult.svelte

Renders the task result. Shows:
- success/error status
- `content` — agent output
- `billing_fallback` — if fallback occurred (e.g. "zen")
- cost_usd, duration_ms, num_turns
- WorkReport (files: created/changed/deleted)

---

## PipelineStages.svelte

Pipeline stage visualization for text-only tasks:
```
INIT → ROUTE → RTK → SKILL → HEADROOM → DSPY → MODEL → DONE
```
Each stage is a colored badge. A failed stage is highlighted red.

---

## TaskSidebar.svelte

List of previous tasks. Data from `GET /api/tasks` (SSE).
Click — loads the task into RunPanel.

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

## ProviderKeysPanel.svelte

BYOK provider keys section on the CF page (`cf/ProviderKeysPanel.svelte`,
mounted at the bottom of `CFPage.svelte`). Masked (`type=password`) input +
provider select (anthropic / openai / google-ai-studio / deepseek), list of
stored key names with delete. Talks to `/api/providers/keys`; shows the
`byok_enabled` state and a setup hint when CF credentials are missing. The key
value is sent once on save and never rendered back.

---

## Shared components

| Component | Purpose |
|---|---|
| `StatusDot` | colored dot: green/yellow/red/gray |
| `CopyButton` | copy text to clipboard |
| `InfoTooltip` | `?` button with tooltip |
| `Drawer` | slide-in side panel |
| `Modal` | dialog window |
| `Toast` | top notification |
| `Spinner` | loading indicator |
| `Skeleton` | loading skeleton |

---

## AppHeader.svelte

Top navigation: logo, links to Tasks / Agents / Models / Spend.
Active section — `--accent-blue`.

---

## Adding a new executor to the UI

1. `RunPanel.svelte` — add to the executors array (file-writing before text-only)
2. `RunParams.svelte` — add `executorHints[id]` with a description
3. Update this file
