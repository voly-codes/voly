---
type: task-routing guide
title: VOLY OpenWiki quickstart
description: Just-in-time routing guide for safely changing VOLY's control-plane runtime, governance, workflows, operations, evidence, and Cloudflare integrations. Use it to find the relevant subsystem page, public boundary, and focused regression tests before editing source.
tags: [voly, quickstart, task-routing, control-plane, safe-changes]
verified:
  - by: openwiki/0.6.1
    at: 2026-10-02T14:26:27.558Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-c8404e37a09f142b3345cdfc
    resource: repo://tests/test_a2a_p0.py
  - id: openwiki-source-577486bf9067d6da1e261023
    resource: repo://tests/test_executor_safety.py
  - id: openwiki-source-ba2a4a06650e64c79b3cf0da
    resource: repo://tests/test_sdk_workflow.py
  - id: openwiki-source-d5ea337baaf9428410f42e17
    resource: repo://voly/__init__.py
  - id: openwiki-source-db4cb5d4e446f7a34f970ef1
    resource: repo://voly/a2a/federation.py
  - id: openwiki-source-c7fb76f9ac620f7a351abbfc
    resource: repo://voly/ai_gateway/gateway.py
  - id: openwiki-source-1c5d86dae1c5021617e4fda8
    resource: repo://voly/capability/evaluated_packs.py
  - id: openwiki-source-9f57af7e08b2624e063c98ed
    resource: repo://voly/capability/matcher.py
  - id: openwiki-source-b724bfb90c3e800cd18ddfeb
    resource: repo://voly/capability/remote_sync.py
  - id: openwiki-source-1f0bed3fba1ff3cdced6b2eb
    resource: repo://voly/capability/routing.py
  - id: openwiki-source-4179cef67895cf94beb7d680
    resource: repo://voly/cli/main.py
  - id: openwiki-source-5bb528d83605544231c81d05
    resource: repo://voly/memory/store.py
  - id: openwiki-source-aafa145a3c26922a5cc7f5e7
    resource: repo://voly/pipeline/core.py
  - id: openwiki-source-eab7650692ea2fcc8fde0182
    resource: repo://voly/plan/runner.py
  - id: openwiki-source-3c206cdc55bd443f89e25262
    resource: repo://voly/plan/store.py
  - id: openwiki-source-3d420928eb6fa472bc699511
    resource: repo://voly/runner/agent_runner.py
  - id: openwiki-source-6c694f0854e3fda69e671ef8
    resource: repo://voly/runner/executor_factory.py
  - id: openwiki-source-9d5245197292fe86e38c083e
    resource: repo://voly/sdk/workflow.py
generated: { by: "openwiki/0.6.1", at: "2026-10-02T14:26:27.558Z" }
---

# VOLY OpenWiki quickstart

VOLY is a project-agnostic control plane around AI engineering agents. It has two intentionally distinct execution boundaries: `Pipeline` performs governed inference and orchestration, while `AgentRunner` invokes file-capable executors in an explicitly selected target-project `cwd`. The package’s public Python facade exports `VOLYConfig`, `Pipeline`, `AgentRouter`, `Agent`, and `Workflow`; the installed `voly` command is a Click command group.

This wiki is **just-in-time routing context**, not a substitute for source review. Start with the [control-plane architecture](architecture/overview.md), then use the table to open the smallest page that owns the behavior being changed. Verify the cited implementation and focused tests before relying on a page's summary.

## Safe-change route

1. Identify whether the change affects inference/orchestration, file execution, durable workflow state, evidence, capability governance, an entrypoint, or a remote boundary.
2. Read the matching page below and follow its source/test links into the implementation.
3. Preserve the target-project boundary: executor writes require a deliberate `cwd`; do not introduce product-specific paths under `voly/`.
4. Keep model calls behind `AIGateway.chat()` when gateway policy is required. Do not conflate model-provider fallback with the separate executor billing/availability chain.
5. Run the focused tests first, then the narrowest additional test that proves the edited behavior. Never use live credentials or a real target repository as a test fixture.

## Task-routing map

| Planned page — use it when changing… | Public entry point(s) to trace | Focused source boundary | Focused tests / first command |
|---|---|---|---|
| [Control-plane architecture](architecture/overview.md) — inference versus file execution, gateway/executor fallback, correlation, or durable record contracts | `from voly import Pipeline, Agent, Workflow`; `voly run` | [`Pipeline`](../voly/pipeline/core.py), [`AIGateway`](../voly/ai_gateway/gateway.py), [`AgentRunner`](../voly/runner/agent_runner.py), [`TaskEvent`](../voly/telemetry.py) | [`test_ai_gateway.py`](../tests/test_ai_gateway.py), [`test_failure_paths.py`](../tests/test_failure_paths.py), [`test_protocol_contracts.py`](../tests/test_protocol_contracts.py) — `pytest tests/test_failure_paths.py -q` |
| [Capability governance and evaluated packs](governance/capabilities.md) — matching, external-pack intake, evidence gates, activation, or snapshot publication | `voly capability match`; `voly capability pack`; `voly capability evaluated` | [`matcher.py`](../voly/capability/matcher.py), [`pack_admission.py`](../voly/capability/pack_admission.py), [`evaluated_packs.py`](../voly/capability/evaluated_packs.py), [`remote_sync.py`](../voly/capability/remote_sync.py) | [`test_capability_pack_import.py`](../tests/test_capability_pack_import.py), [`test_evaluated_capability_packs.py`](../tests/test_evaluated_capability_packs.py), [`test_capability_remote_sync.py`](../tests/test_capability_remote_sync.py) — `pytest tests/test_evaluated_capability_packs.py -q` |
| [Cloudflare and remote-service integrations](integrations/cloudflare-and-remote-services.md) — federation, remote capability snapshots, memory, spend, telemetry, catalog/marketplace, AI Gateway, or BYOK | `voly a2a`; `voly capability evaluated sync`; configured remote clients | [`federation.py`](../voly/a2a/federation.py), [`remote_sync.py`](../voly/capability/remote_sync.py), [`memory`](../voly/memory/), [`spend`](../voly/spend/), [`gateway.py`](../voly/ai_gateway/gateway.py) | [`test_a2a_federation.py`](../tests/test_a2a_federation.py), [`test_memory_client.py`](../tests/test_memory_client.py), [`test_spend_client.py`](../tests/test_spend_client.py), [`test_byok_credentials.py`](../tests/test_byok_credentials.py) — `pytest tests/test_a2a_federation.py -q` |
| [Entrypoints, configuration, and filesystem safety](operations/entrypoints-and-safety.md) — CLI, FastAPI/Svelte, MCP, SDK entry, configuration lookup, `cwd`, executor safety, or write rollback | `voly`; `voly ui`; `voly mcp serve`; `voly.web.server:create_app()`; `Agent.run()` | [`main.py`](../voly/cli/main.py), [`server.py`](../voly/web/server.py), [`run.py`](../voly/web/routes/run.py), [`agent_runner.py`](../voly/runner/agent_runner.py) | [`test_executor_safety.py`](../tests/test_executor_safety.py), [`test_cli_contracts.py`](../tests/test_cli_contracts.py), [`test_web_api.py`](../tests/test_web_api.py), [`test_mcp_facade.py`](../tests/test_mcp_facade.py) — `pytest tests/test_executor_safety.py -q` |
| [Run evidence, evaluation, and observability](operations/evidence-evaluation-and-telemetry.md) — baselines, evaluation policies/judges, TaskEvent privacy/accounting, RunRecord lifecycle, or remote analytics consent | `voly evidence`; `voly eval`; `voly telemetry`; evidence/runs API routes | [`evidence`](../voly/evidence/), [`evaluation`](../voly/evaluation/), [`telemetry.py`](../voly/telemetry.py), [`runs.py`](../voly/web/routes/runs.py) | [`test_evidence_foundation.py`](../tests/test_evidence_foundation.py), [`test_evaluation.py`](../tests/test_evaluation.py), [`test_retry_cost.py`](../tests/test_retry_cost.py), [`test_runs_api.py`](../tests/test_runs_api.py), [`test_telemetry.py`](../tests/test_telemetry.py) — `pytest tests/test_evaluation.py -q` |
| [Pipeline and A2A orchestration](orchestration/a2a-and-pipeline.md) — dispatch, decomposition, role scheduling, hybrid execution, federation, episodes, or agentic judging | `Pipeline.run()`; `voly run`; `POST /api/run` | [`core.py`](../voly/pipeline/core.py), [`stages_a2a.py`](../voly/pipeline/stages_a2a.py), [`multiagent_run.py`](../voly/a2a/multiagent_run.py), [`agentic_judge.py`](../voly/a2a/agentic_judge.py) | [`test_a2a_p0.py`](../tests/test_a2a_p0.py), [`test_hybrid_a2a.py`](../tests/test_hybrid_a2a.py), [`test_agentic_judge.py`](../tests/test_agentic_judge.py) — `pytest tests/test_a2a_p0.py -q` |
| [Durable plans, workflows, and the public Agent SDK](workflows/plans-and-sdk.md) — plan state/gates, workflow compilation, approval/resume/cancel, SDK agents, or workflow REST/SSE | `from voly import Agent, Workflow`; `voly workflow`; `/api/workflows` | [`runner.py`](../voly/plan/runner.py), [`engine.py`](../voly/plan/engine.py), [`workflow.py`](../voly/sdk/workflow.py), [`workflows.py`](../voly/web/routes/workflows.py) | [`test_sdk_agent.py`](../tests/test_sdk_agent.py), [`test_sdk_workflow.py`](../tests/test_sdk_workflow.py), [`test_plan_concurrency.py`](../tests/test_plan_concurrency.py), [`test_plan_approval.py`](../tests/test_plan_approval.py), [`test_workflows_api.py`](../tests/test_workflows_api.py) — `pytest tests/test_sdk_workflow.py -q` |

## Boundaries worth preserving

- **Inference is not filesystem execution.** `Pipeline` can orchestrate hybrid work, but executor roles use `AgentRunner` and its separate safety, fallback, work-report, evidence, and cost behavior.
- **External capability content is untrusted.** Discovery/admission, inert staging, evaluated activation, ordinary routing, and remote snapshot publication are separate controls; any unavailable or inapplicable evaluated route must retain native fallback.
- **Plans own durable workflow state.** SDK `Workflow` compiles to a `Plan` and delegates execution to `PlanRunner`; new entrypoints should not create a second scheduler or approval state machine.
- **Operational records have different authority and privacy.** A terminal `TaskEvent`, in-flight `RunRecord`, local `EvidenceRecord`/evaluation, A2A episode, plan, and capability experiment answer different questions. Remote analytics is consent-gated and must use its allowlisted export rather than a full local record.
- **Remote services remain integration boundaries.** Configure service-specific URLs/tokens and preserve local fallback/authority when a Worker or upstream service is absent or fails.

## Repository orientation

- [`voly/`](../voly/) contains the Python control plane; [`tests/`](../tests/) is the behavior/compatibility suite.
- [`ui/`](../ui/) is the Svelte dashboard; [`cf-workers/`](../cf-workers/) contains Worker implementations behind optional remote integrations.
- [`pyproject.toml`](../pyproject.toml) declares the `voly` console script and optional `ui`/`mcp` dependencies.
- Local runtime output such as `.voly/events`, `.voly/runs`, `.voly/evidence`, `.voly/plans`, and `.voly/episodes` is state produced by runs, not source to edit.

For broad orientation read the [architecture overview](architecture/overview.md). For an actual change, start from the table row that owns the relevant contract and let source plus focused tests decide the implementation.
