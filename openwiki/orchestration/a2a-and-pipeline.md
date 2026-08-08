---
type: Orchestration Guide
title: Pipeline and A2A orchestration
description: Describes VOLY's pipeline dispatch rules, local and federated A2A flows, hybrid execution, episodes, and the bounded read-only agentic judge.
tags: [voly, pipeline, a2a, multi-agent, hybrid, evaluation]
---

# Pipeline and A2A orchestration

`Pipeline.run()` is VOLY’s inference/orchestration entrypoint. It coordinates routing, context stages, optional A2A dispatch, and terminal telemetry; it does not itself make every task a filesystem-writing task. The [architecture overview](../architecture/overview.md) defines the separate executor and gateway boundaries that this orchestration composes.

## Dispatch semantics

VOLY has two A2A entry modes with different meanings:

1. **Explicit delegation** creates one protocol task and calls `route_and_delegate()`. If it is completed or working, pipeline returns the corresponding A2A result; otherwise ordinary pipeline handling continues.
2. **Automatic multi-agent dispatch** runs after task routing only when A2A is enabled, the request is not nested, and analysis has enough capability flags (code generation, review, testing, deployment) or `complexity == "high"`. The decomposer must produce at least two subtasks.

Do not collapse these pathways into one behavior: the former is task/protocol delegation, whereas the latter selects local dependency-wave orchestration by default. The recursion guard (`delegate_to_a2a=False`, `VOLY_A2A_NESTED`, and parent context) prevents federated subtasks from decomposing forever.

## Local multi-agent flow

With `a2a.execution_mode: local`, `TaskDecomposer` builds dependency-linked role subtasks; `LeadOrchestrator` assigns tiers, models/providers, skills, and possibly an execution mode. `run_local()` schedules roles in dependency waves:

- Chat roles can run concurrently within configured limits.
- Executor roles are serial and protected by a shared-`cwd` lock, avoiding concurrent repository mutation.
- Later roles receive compact prior summaries labelled **untrusted context**; relevant roles also receive file/diff evidence.
- A gateway `spend_limited` result stops later scheduling rather than spending more calls.

Hybrid mode requires a project `cwd`. Implement roles (by default developer, bugfixer, tester, and devops) can call `AgentRunner`, while planning/review roles stay on gateway chat. A successful code-generation executor role with no reported or detected change is treated as failed rather than accepted as a plausible narrative. This **dispatches into** the architecture’s executor path and inherits its billing fallback and run evidence; see [architecture overview](../architecture/overview.md).

Capability-aware lead assignment can consult the executor matcher using repository/task features. Optional evaluated capability packs sit above that matcher and retain native fallback; their admission and activation policy is documented in [capability governance](../governance/capabilities.md).

## Federated flow

When execution mode is not local, the pipeline uses `A2AOrchestrator.dispatch_parallel()`, polls outstanding tasks to the configured deadline, merges returned output, and persists an `A2AReport`. Federation treats the run as complete only when every dispatched task completed; otherwise status is partial or failed. The remote boundary is an A2A worker protocol, while local source and tests remain the authority for behavioral changes.

## Episodes and programmable environments

A completed local flow is adapted into a `MultiAgentEpisode` and atomically persisted at `<cwd>/.voly/episodes/<task_id>.json`. It includes environment/status, agent traces, artifacts, decisions, metrics, and costs. An episode is an orchestration record—not a replacement for executor EvidenceRecord or evaluation report.

`voly/a2a/environments.py` also defines reusable role-independent patterns (`PipelineEnv`, solver/judge, parallel solutions, debate, iterative repair). Current production local dispatch is adapted as the pipeline environment, so extending a generic environment does not automatically change the production scheduler.

## Read-only agentic judge

For local A2A work with `cwd`, an agentic judge is appended only when `evaluation.llm_judge.mode` is `shadow` or `required`. It receives the task, acceptance criteria, episode trace, and parent trace identifiers. Its workspace allows only `list_files`, `read_file`, `search_text`, and `git_diff`; it path-confines accesses, excludes `.git` and `.voly` in searches/listing, has no write or shell operation, limits output, and caps its interaction loop.

The judge reports `pass`, `fail`, or `uncertain` plus five stable 0–1 metrics. Shadow mode records its trace/verdict without changing the run. Required mode can downgrade an otherwise successful run. Therefore judge parsing, tool definitions, and provider availability are production-affecting changes—not merely observability work.

## Change checklist

- Test auto-dispatch and explicit delegation separately.
- Preserve nested-task guards and dependency-wave/cwd locking semantics.
- Test both chat and executor roles when changing hybrid behavior, including no-`cwd` fallback.
- Keep episode schema evolution separate from TaskEvent and evidence contracts.
- For judge changes, test workspace confinement, strict result parsing, and both `shadow` and `required` outcome semantics.

**Useful sources:** `voly/pipeline/{core.py,stages_a2a.py}`, `voly/a2a/{decomposer.py,lead.py,multiagent_run.py,hybrid.py,episode.py,environments.py,agentic_judge.py}`, `docs/backend/{pipeline.md,a2a.md}`, `tests/test_a2a_*.py`, `tests/test_hybrid_a2a.py`, `tests/test_agentic_judge.py`.
