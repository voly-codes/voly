---
type: quickstart guide
title: VOLY OpenWiki quickstart
description: A just-in-time routing map for safely changing VOLY's project-agnostic control plane, from runtime cwd and entrypoints to architecture, orchestration, governance, operations, and Headroom integration.
tags: [voly, quickstart, control-plane, architecture, operations]
verified:
  - by: openwiki/0.7.0
    at: 2026-10-05T16:47:01.790Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-7fba4442fec73d0a9c523e52
    resource: repo://tests/test_capability_pack_import.py
  - id: openwiki-source-81efd633b7a2af55b81ac9ad
    resource: repo://tests/test_quickstart.py
  - id: openwiki-source-c7fb76f9ac620f7a351abbfc
    resource: repo://voly/ai_gateway/gateway.py
  - id: openwiki-source-f949ba60b6b2c1f5a69f6d32
    resource: repo://voly/capability/pack_admission.py
  - id: openwiki-source-977fb78553c15ddb8fb9192d
    resource: repo://voly/cli/commands/quickstart.py
  - id: openwiki-source-3cbe083798ded0438463ec65
    resource: repo://voly/cli/commands/run_cmd.py
  - id: openwiki-source-4179cef67895cf94beb7d680
    resource: repo://voly/cli/main.py
  - id: openwiki-source-d54bc729a55eea0e5d42930a
    resource: repo://voly/headroom/proxy.py
  - id: openwiki-source-81cf2e05fbfbb0e0dd6b31a7
    resource: repo://voly/pipeline/stages_a2a.py
generated: { by: "openwiki/0.7.0", at: "2026-10-05T16:47:01.790Z" }
---

# VOLY OpenWiki quickstart

Use this page to choose the smallest relevant context for a change—not as required startup reading. Repository source and tests are authoritative; consult a linked guide when the task crosses an unfamiliar boundary or source inspection leaves a material uncertainty.

VOLY is a project-agnostic control plane around coding agents. The target project is runtime input (`--cwd` or configuration), so product-specific behavior must not be added below `voly/`. A `voly run` without `--executor` builds a `Pipeline`; an explicit executor calls `AgentRunner` with the selected working directory. These are deliberately different routes: governed chat-model work remains at `AIGateway.chat()`, while a file-capable executor is responsible for target-project changes.

## Choose the boundary first

| If the change involves… | Read this guide | Start in source | Focused test slice | First validation |
|---|---|---|---|---|
| Model calls, provider routing, DLP/cache/rate/spend controls, executor fallback, safety rollback, telemetry/evidence, Cloudflare, or UI/API trust boundaries | [Control-plane architecture](architecture/overview.md) | [`voly/ai_gateway/gateway.py`](../voly/ai_gateway/gateway.py), [`voly/runner/agent_runner.py`](../voly/runner/agent_runner.py), [`voly/executor/safety.py`](../voly/executor/safety.py), [`voly/telemetry.py`](../voly/telemetry.py) | [`tests/test_ai_gateway.py`](../tests/test_ai_gateway.py), [`tests/test_executor_safety.py`](../tests/test_executor_safety.py), [`tests/test_protocol_contracts.py`](../tests/test_protocol_contracts.py) | `pytest tests/test_ai_gateway.py -q` |
| Pipeline routing, explicit/federated A2A, dependency waves, hybrid chat/executor roles, plan gates, episodes, agentic judge, or bounded review workflow | [Pipeline, A2A, and workflow orchestration](orchestration/a2a-and-pipeline.md) | [`voly/pipeline/core.py`](../voly/pipeline/core.py), [`voly/pipeline/stages_a2a.py`](../voly/pipeline/stages_a2a.py), [`voly/a2a/multiagent.py`](../voly/a2a/multiagent.py), [`voly/a2a/hybrid.py`](../voly/a2a/hybrid.py) | [`tests/test_a2a_p0.py`](../tests/test_a2a_p0.py), [`tests/test_hybrid_a2a.py`](../tests/test_hybrid_a2a.py), [`tests/test_plan_a2a_bridge.py`](../tests/test_plan_a2a_bridge.py), [`tests/test_agentic_judge.py`](../tests/test_agentic_judge.py) | `pytest tests/test_hybrid_a2a.py -q` |
| Ordinary capability matching, external-pack discovery/admission/staging, evaluated-pack activation, evaluation, or remote snapshot sync | [Capability, evidence, and evaluation governance](governance/capabilities.md) | [`voly/capability/matcher.py`](../voly/capability/matcher.py), [`voly/capability/pack_admission.py`](../voly/capability/pack_admission.py), [`voly/capability/evaluated_packs.py`](../voly/capability/evaluated_packs.py), [`voly/capability/remote_sync.py`](../voly/capability/remote_sync.py) | [`tests/test_capability_matcher.py`](../tests/test_capability_matcher.py), [`tests/test_capability_pack_import.py`](../tests/test_capability_pack_import.py), [`tests/test_evaluated_capability_packs.py`](../tests/test_evaluated_capability_packs.py), [`tests/test_capability_remote_sync.py`](../tests/test_capability_remote_sync.py) | `pytest tests/test_capability_pack_import.py -q` |
| CLI/SDK/API/UI/MCP behavior, config discovery, target cwd propagation, local state, packaging, or exposure safety | [Entrypoints, configuration, and safe operation](operations/entrypoints-and-safety.md) | [`voly/cli/main.py`](../voly/cli/main.py), [`voly/cli/commands/run_cmd.py`](../voly/cli/commands/run_cmd.py), [`voly/web/server.py`](../voly/web/server.py), [`voly/config/`](../voly/config/) | [`tests/test_cli_contracts.py`](../tests/test_cli_contracts.py), [`tests/test_config.py`](../tests/test_config.py), [`tests/test_web_api.py`](../tests/test_web_api.py), [`tests/test_mcp_facade.py`](../tests/test_mcp_facade.py), [`tests/test_packaging.py`](../tests/test_packaging.py) | `pytest tests/test_web_api.py -q` |
| VOLY's local compression proxy, or the bundled Headroom project's agent hooks, manifests, PR template, or governance workflow | [Headroom integration, agent hooks, and PR governance](operations/headroom-integration-and-governance.md) | [`voly/headroom/proxy.py`](../voly/headroom/proxy.py), [`voly/pipeline/core.py`](../voly/pipeline/core.py), then the bundled Headroom paths named in that guide | [`tests/test_config.py`](../tests/test_config.py), [`tests/test_protocol_contracts.py`](../tests/test_protocol_contracts.py), plus the focused bundled-Headroom tests named in the guide | `pytest tests/test_config.py -q` |

## Working model

1. **Select the control surface.** The package installs `voly` as `voly.cli.main:main`; the CLI loads configuration and dispatches command groups. For a target repository, begin with `voly quickstart --check --cwd <target>`: it is a read-only readiness check and suggests an executor `--dry-run` command. `--yes` may create a missing target `voly.yaml` without secrets, but does not overwrite an existing configuration.
2. **Keep execution domains separate.** Make chat-model calls through `AIGateway.chat()` so gateway policy applies. Do not turn a chat provider into a file writer; file mutations go through the executor/`AgentRunner` path with its own `cwd`, reporting, fallback, and safety behavior.
3. **Follow the state owner.** Target-relative `.voly/` stores operational output such as events, runs, evidence, evaluations, episodes, caches, and reports. It is generated state, not a source change. Preserve public event, evidence, A2A, and snapshot shapes with their contract tests.
4. **Use the narrowest hermetic proof.** Do not substitute a live provider or agent run for tests. Integration and end-to-end work belongs in the designated external PulseBoard environment, not this checkout. Update the matching `docs/backend/` or `docs/frontend/` document whenever behavior changes.

## Non-negotiable change checks

- Carry caller-supplied `cwd` through dispatch; do not introduce a repository-specific default or product logic in `voly/`.
- Keep gateway policy and executor fallback independent. A gateway failure is not an instruction to write files, and executor billing fallback is not provider routing.
- Treat imported capability content as untrusted. Discovery/admission, inert staging, evidence-based evaluated activation, per-run evaluation, and remote publication are separate controls.
- Keep Headroom narrow: its local proxy may compress context before inference and returns original messages on compression failure; it does not own provider routing, task execution, or the bundled Headroom project's hooks and PR policy.
- Do not read, log, or commit live secrets. Keep `.env`, `.voly/`, build artifacts, and local caches out of ordinary commits; inspect `git status` before merging.

## What lives where

- [`voly/`](../voly/) is the Python control plane: CLI, gateway, pipeline/A2A, executors, capability governance, telemetry, and web/MCP surfaces.
- [`tests/`](../tests/) defines behavioral and compatibility guarantees; start with the row's focused slice before widening validation.
- [`ui/`](../ui/) is the Svelte/Vite dashboard; [`cf-workers/`](../cf-workers/) contains optional deployable Cloudflare boundaries.
- [`docs/`](../docs/) is the detailed engineering documentation that must move with behavior changes. The OpenWiki pages above are navigation, not a competing source of truth.

For a new task, read only the matching guide and the cited source/test slice. Escalate to an adjacent guide when the change crosses its boundary—for example, hybrid A2A work that writes files needs both orchestration and architecture/safety context.
