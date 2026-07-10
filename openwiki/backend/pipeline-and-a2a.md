# Pipeline and A2A

This page covers the orchestration path for text-only work and the local multi-agent decomposition path used for more complex tasks.

## Pipeline responsibilities

`voly/pipeline/core.py` is the main orchestrator for the text-only path. It wires the router, memory store, RTK manager, gateway, DSPy runner, A2A orchestrator, and telemetry emission into a staged pipeline.

The documented stage order is:

`INIT → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE → MEMORY_RETRIEVE → RTK_FILTER → SKILL_INJECT → HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL → MEMORY_STORE → AGUI_DONE → DONE/ERROR`

The pipeline exists to assemble context and route the work; it is not the file-writing runtime.

## Smart dispatch

The web API uses a smart-dispatch rule for `POST /api/run` when `executor=pipeline`:

- simple code-generation work can be promoted to `claude-code`
- complex multi-component work stays in the pipeline and is sent through the multi-agent path
- text-only requests remain single-model calls

SSE `start` for multi-agent includes `a2a: true`, `hybrid: bool`, and resolved `cwd`
(plus `hybrid_warning: "hybrid_skipped_no_cwd"` when hybrid is on but no `cwd` resolved).
SSE `done` may include `hybrid` summary (`executor_roles`, `chat_roles`, `files_touched`)
and per-role `a2a_assignments` with `mode` / `executor` / `files_touched`.

This behavior is described in `docs/backend/pipeline.md`,
`docs/proposals/hybrid-multiagent-executor.md`, and the top-level README.

### Hybrid multi-agent (files)

When `a2a.hybrid_code_gen` is true and a project `cwd` is available (request body,
`default_cwd`, or `VOLY_PROJECT_CWD`):

- **implement roles** (`developer`, `bugfixer`, `tester` by default) run via
  `AgentRunner` + billing fallback chain and can write files under `cwd`
- **plan/review roles** stay on `AIGateway.chat()`
- the lead orchestrator may override the mode per role with an optional
  `execution: "chat" | "executor"` field (invalid values fall back to the role map)
- without `cwd`, all roles remain chat-only — executors never run without an
  explicit project path, even with `hybrid_require_cwd: false`

UI multi-agent panels show mode badges (`chat` / `executor`) and file counts.

## A2A orchestration

The repository supports both local and federated A2A flows.

### Local mode

In local mode, a lead orchestrator decomposes a task into roles such as architect, developer, tester, reviewer, and devops. It then assigns model tiers and skills, resolves those tiers to concrete provider/model combinations, and executes the sub-agents in dependency order through `AIGateway.chat()`.

### Federation mode

In federation mode, work is dispatched to remote agents through the A2A worker boundary.

## Telemetry and run state

The pipeline emits `TaskEvent` telemetry at the end of a run. Versioned public protocol expectations include `schema_version: 1` on the task event. The pipeline docs also explain a lightweight run-record and watchdog mechanism that keeps in-flight multi-agent runs visible even before final telemetry lands.

Multi-agent sub-calls go through `AIGateway.chat()`, so they inherit gateway **spend-on-success** accounting and can stop early when `spend_limited` is returned (remaining roles marked without further provider calls).

## What to watch when changing pipeline or A2A

- Keep stage names and stage ordering aligned with the implementation.
- Preserve the rule that complex A2A work stays in the pipeline rather than being promoted away.
- Update the telemetry contract docs when event fields change.
- Treat A2A, task telemetry, and smart-dispatch changes as cross-cutting; they affect the API, pipeline, and UI.

## Useful source files

- `voly/pipeline/core.py`
- `voly/pipeline/stages.py`
- `voly/a2a/multiagent.py`
- `voly/a2a/federation.py`
- `voly/telemetry.py`
- `docs/backend/pipeline.md`
- `docs/backend/a2a.md`
- `docs/backend/api.md`
