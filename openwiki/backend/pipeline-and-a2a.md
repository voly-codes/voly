# Pipeline and A2A

This page covers the orchestration path for text-only work and the local multi-agent decomposition path used for more complex tasks.

## Pipeline responsibilities

`voly/pipeline/core.py` is the main orchestrator for the text-only path. It wires the router, memory store, RTK manager, gateway, DSPy runner, A2A orchestrator, and telemetry emission into a staged pipeline.

The documented stage order is:

`INIT → RESEARCH_SHADOW (optional) → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE → MEMORY_RETRIEVE → RTK_FILTER → SKILL_SUGGEST → SKILL_INJECT → HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL → MEMORY_STORE → AGUI_DONE → DONE/ERROR`

`RESEARCH_SHADOW` is a local-only research-first pilot. It reads project
source/docs and an existing reuse report, writes a typed `reuse | adapt | build`
recommendation to `.voly/research/reports/`, and does not change routing.

`SKILL_SUGGEST` (non-blocking) queries the marketplace via `SkillScout` for skills relevant to the task that are not installed locally; suggestions land in SSE `done.skill_suggestions`.

The pipeline exists to assemble context and route the work; it is not the file-writing runtime.

When strategic memory compaction is enabled, `MEMORY_RETRIEVE` injects typed
decisions, facts, failed attempts, questions, and next actions rather than raw
session transcripts. Retrieval is isolated by project/organization/global
scope, bounded by token and per-class budgets, and ignores expired records.
Private observations are never included by `voly memory export`.

Continuous learning is a separate local shadow loop. Atomic instincts collect
test, review, retry, rollback and explicit human evidence. Confidence cannot
increase from an observation alone, approval is manual, and learned actions
cannot enter active prompts or override policy/security gates. Cross-project
promotion requires positive evidence from at least two projects.

Lifecycle hooks use a harness-neutral event contract and an allowlisted adapter.
Every manifest declares permissions, timeout, idempotency and fail policy.
Imported hooks remain disabled until explicit approval. Automatic attempts,
including failures and duplicates, are mirrored into local evidence and
telemetry logs without mutating executor run state.

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

The pipeline emits `TaskEvent` telemetry at the end of a run. Versioned public protocol expectations include `schema_version: 3` with `correlation_id` on the task event (see [Architecture overview](../architecture/overview.md)). The pipeline docs also explain a lightweight run-record and watchdog mechanism that keeps in-flight multi-agent runs visible even before final telemetry lands.

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
