---
type: Project Guide
title: VOLY OpenWiki quickstart
description: Entry point for understanding VOLY, a self-hosted AI-agent control plane for project-agnostic execution, orchestration, governance, and observability.
tags: [voly, control-plane, ai-agents, openwiki]
---

# VOLY OpenWiki quickstart

VOLY is a Python **control plane for AI coding agents**, rather than another agent. A caller supplies a task and target project (`--cwd` or configuration); VOLY chooses and coordinates model or file-capable execution, applies safety and cost controls, and emits run evidence and telemetry. The open-core repository includes the CLI, FastAPI API, Svelte UI, Cloudflare-worker integrations, and tests.

The product distinction is two execution paths:

- The **pipeline path** assembles context and handles inference through `AIGateway.chat()`.
- The **executor path** uses `AgentRunner` and a file-capable backend to modify the supplied target project. Its fallback behavior, repository baseline, and work report are distinct from model-gateway routing.

[Architecture overview](architecture/overview.md) explains why this split exists and which contracts hold the pieces together. Complex pipeline tasks can become local or federated multi-agent work; [pipeline and A2A orchestration](orchestration/a2a-and-pipeline.md) explains that lifecycle. Capability selection and external-pack governance are deliberately separate from normal routing and live in [capability governance](governance/capabilities.md). [Operations, entrypoints, and safety](operations/entrypoints-and-safety.md) maps the commands, web surface, configuration, local state, and checks.

## Start here by task

| Change area or user intent | Relevant wiki page | Exact source entry points | Important symbols or types | Focused tests | Minimal validation command |
|---|---|---|---|---|---|
| Understand product boundaries, telemetry, or model versus filesystem work | [Architecture overview](architecture/overview.md) | `voly/ai_gateway/gateway.py`, `voly/runner/agent_runner.py`, `voly/telemetry.py` | `AIGateway.chat()`, `AgentRunner`, `TaskEvent` | `tests/test_ai_gateway.py`, `tests/test_executor_safety.py` | `pytest tests/test_ai_gateway.py -q` |
| Change task decomposition, A2A, hybrid roles, or the agentic judge | [Pipeline and A2A orchestration](orchestration/a2a-and-pipeline.md) | `voly/pipeline/stages_a2a.py`, `voly/a2a/multiagent_run.py`, `voly/a2a/agentic_judge.py` | `Pipeline.run()`, `LeadOrchestrator`, `A2AOrchestrator.dispatch_parallel()` | `tests/test_a2a_p0.py`, `tests/test_hybrid_a2a.py`, `tests/test_agentic_judge.py` | `pytest tests/test_a2a_p0.py -q` |
| Change model middleware, provider behavior, spending, or executor fallback | [Architecture overview](architecture/overview.md) | `voly/ai_gateway/gateway.py`, `voly/runner/agent_runner.py` | `AIGateway.chat()`, `AgentRunner` | `tests/test_ai_gateway.py`, `tests/test_gateway_provider_health.py`, `tests/test_executor_cwd_and_a2a_call.py` | `pytest tests/test_ai_gateway.py -q` |
| Import, evaluate, activate, or publish capability packs | [Capability governance](governance/capabilities.md) | `voly/capability/evaluated_packs.py`, `voly/capability/pack_admission.py`, `voly/capability/remote_sync.py` | `ExecutorMatcher`, evaluated router | `tests/test_capability_pack_import.py`, `tests/test_evaluated_capability_packs.py`, `tests/test_capability_remote_sync.py` | `pytest tests/test_capability_pack_import.py -q` |
| Change CLI/API/UI/configuration or run verification | [Operations, entrypoints, and safety](operations/entrypoints-and-safety.md) | `voly/cli/main.py`, `voly/web/server.py`, `ui/src/App.svelte`, `voly/config/` | `main`, `create_app()` | `tests/test_cli_contracts.py`, `tests/test_web_api.py` | `pytest tests/test_web_api.py -q` |

## Repository map

- `voly/` — Python package: pipeline, A2A, gateway, executors, capability system, CLI, web API, telemetry, and supporting domains.
- `ui/` — Svelte 5/Vite dashboard, bundled by the FastAPI server when build assets exist.
- `cf-workers/` — Cloudflare workers, including the capability service and A2A integration boundary.
- `docs/` — primary detailed engineering documentation. In particular, `docs/ARCHITECTURE.md` and `docs/backend/` are authoritative companions to this synthesis.
- `tests/` — pytest behavior and contract suite; source of truth for many compatibility guarantees.
- `.voly/` — ignored runtime output such as runs, events, evidence, episodes, caches, evaluated-pack state, and reports. It is not source.

## Ground rules for changes

1. Keep VOLY project-agnostic: target repository behavior belongs behind runtime `cwd`, not in product-specific logic under `voly/`.
2. Preserve `AIGateway.chat()` as the model-call boundary; file-capable executors are intentionally separate.
3. Treat public event, evidence, federation, and snapshot formats as contracts. Change docs and tests with shape changes.
4. Treat imported capabilities as untrusted inputs. Discovery/staging, measured activation, and remote publication are separate controls.
5. Do not read or commit live secrets. Use `.env.example` and configuration docs only for placeholder-based setup.

## Backlog

- **Memory, DSPy, research, reuse, and learning** — `voly/{memory,dspy,research,reuse,learning}/`; deferred because their independent behaviors exceed this initial map's five-page scope.
- **Cloudflare-worker internals** — `cf-workers/`; deferred beyond the A2A and capability boundaries documented here because worker-specific deployment and storage designs need their own focused pass.
- **Detailed frontend component/API map** — `ui/src/` and `voly/web/routes/`; deferred because the initial operations page documents the integration boundary rather than each dashboard feature.
