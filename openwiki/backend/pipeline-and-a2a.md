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

This behavior is described in `docs/backend/pipeline.md` and in the top-level README.

## A2A orchestration

The repository supports both local and federated A2A flows.

### Local mode

In local mode, a lead orchestrator decomposes a task into roles such as architect, developer, tester, reviewer, and devops. It then assigns model tiers and skills, resolves those tiers to concrete provider/model combinations, and executes the sub-agents in dependency order through `AIGateway.chat()`.

### Federation mode

In federation mode, work is dispatched to remote agents through the A2A worker boundary.

## Telemetry and run state

The pipeline emits `TaskEvent` telemetry at the end of a run. Recent architecture changes added versioned public protocol expectations around telemetry, including `schema_version: 1` on the task event. The pipeline docs also explain a lightweight run-record and watchdog mechanism that keeps in-flight multi-agent runs visible even before final telemetry lands.

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
