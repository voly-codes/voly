---
type: project guide
title: VOLY OpenWiki quickstart
description: Entry point for navigating VOLY's project-agnostic control plane. Routes coding agents to the smallest focused guide for orchestration, governed execution, integrations, plans, capability governance, and operations.
tags: [voly, control-plane, ai-agents, openwiki]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-19T12:16:57.591Z
sources:
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-e8e61d605125cac4d909755e
    resource: repo://docs/ARCHITECTURE.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-d5ea337baaf9428410f42e17
    resource: repo://voly/__init__.py
  - id: openwiki-source-4179cef67895cf94beb7d680
    resource: repo://voly/cli/main.py
generated: { by: "openwiki/0.5.2", at: "2026-09-19T12:16:57.591Z" }
---

# VOLY OpenWiki quickstart

VOLY is a Python control plane for AI coding agents, not a replacement agent. Callers provide a task and target project at runtime—normally `--cwd` or configured `cwd`; VOLY owns routing, orchestration, safety, cost controls, and records around that work. Keep the core project-agnostic: target-repository behavior belongs behind that runtime boundary, not in product-specific logic under `voly/`.

The essential split is deliberate:

- **Pipeline/chat work** runs through `Pipeline.run()` and uses `AIGateway.chat()` for model inference. Do not add a normal model-call path around that boundary.
- **Executor/file work** runs through `AgentRunner` and a file-capable backend in the supplied `cwd`. It has its own safety, fallback, work-report, and evidence lifecycle; an executor is not a chat provider.

Start with the [control-plane architecture](architecture/overview.md) for the cross-cutting topology, durable records, and invariants. Then use the focused guide below rather than treating this page as implementation reference.

## Start here by task

| Change area or question | Smallest focused page | Start from | Focused tests | Minimal validation |
|---|---|---|---|---|
| Need the caller-to-runtime topology, path boundaries, durable record ownership, or cross-cutting invariants | [Control-plane architecture](architecture/overview.md) | `voly/pipeline/`, `voly/runner/agent_runner.py`, `voly/telemetry.py` | `tests/test_protocol_contracts.py`, `tests/test_executor_safety.py` | `pytest tests/test_protocol_contracts.py -q` |
| Change decomposition, explicit or automatic A2A, dependency waves, hybrid roles, federation, episodes, or judging | [Pipeline, A2A, and hybrid orchestration](orchestration/a2a-and-pipeline.md) | `voly/pipeline/`, `voly/a2a/` | `tests/test_a2a_p0.py`, `tests/test_hybrid_a2a.py`, `tests/test_agentic_judge.py` | `pytest tests/test_a2a_p0.py -q` |
| Change executor safety, baseline/evidence collection, deterministic or LLM evaluation, plan gates, retries, resume, or review loops | [Verified execution, plans, evidence, and evaluation](workflows/verified-execution.md) | `voly/runner/`, `voly/evidence/`, `voly/evaluation/`, `voly/plan/`, `voly/workflow/` | `tests/test_evidence_foundation.py`, `tests/test_evaluation.py`, `tests/test_plan_runner.py`, `tests/test_review_until_clean.py` | `pytest tests/test_evaluation.py -q` |
| Change gateway middleware, providers/upstream behavior, BYOK, spend/cache/health semantics, Cloudflare Workers, or Python-to-worker payloads | [Model gateway and Cloudflare integration boundaries](integrations/gateway-and-cloudflare.md) | `voly/ai_gateway/`, `voly/cloudflare/`, `cf-workers/` | `tests/test_ai_gateway.py`, `tests/test_gateway_provider_health.py`, `tests/test_byok_credentials.py` | `pytest tests/test_ai_gateway.py -q` |
| Change the public Python `Agent`/`Workflow` API, SDK workflow compilation, tools, structured output, or MCP server operations | [Programmable SDK and MCP surfaces](integrations/sdk-and-mcp.md) | `voly/__init__.py`, `voly/sdk/`, `voly/mcp/`, `voly/web/` | `tests/test_sdk_agent.py`, `tests/test_sdk_workflow.py`, `tests/test_mcp.py` | `pytest tests/test_sdk_workflow.py -q` |
| Import, stage, evaluate, activate, retire, route with, or publish a capability pack | [Capability governance and evaluated packs](governance/capabilities.md) | `voly/capability/`, `cf-workers/` | `tests/test_capability_pack_import.py`, `tests/test_evaluated_capability_packs.py`, `tests/test_capability_remote_sync.py` | `pytest tests/test_capability_pack_import.py -q` |
| Change CLI/API/UI dispatch, configuration, runtime state, local exposure, file-executor fallback, or operational safety | [Entrypoints, configuration, and executor safety](operations/entrypoints-and-safety.md) | `voly/cli/main.py`, `voly/web/`, `voly/config/`, `voly/runner/` | `tests/test_cli_contracts.py`, `tests/test_web_api.py`, `tests/test_executor_safety.py` | `pytest tests/test_web_api.py -q` |

## Repository map

- `voly/` — the Python control plane: CLI, pipeline/A2A, model gateway, runners and executors, evidence/evaluation, plans/workflows, capability governance, SDK/MCP, configuration, and web service.
- `tests/` — pytest behavior, contract, and focused subsystem coverage. Run the focused test named above before broader validation.
- `ui/` — Svelte/Vite dashboard consumed by the optional local FastAPI web surface.
- `cf-workers/` — separately deployed Cloudflare Worker implementations and cross-runtime integration contracts.
- `cf-pipelines/` — Cloudflare pipeline/deployment support distinct from the Python runtime.
- `docs/` — detailed engineering documentation; `docs/ARCHITECTURE.md` and `docs/backend/` are important source companions.
- `voly.yaml` and `.env.example` — configuration examples and placeholders; never use live secrets as documentation inputs.
- `.voly/` — generated local runtime state such as runs, events, evidence, episodes, caches, evaluated capability state, and reports; it is not source.

## Change boundaries to preserve

1. **Target isolation:** pass and honor the caller-selected `cwd`; do not silently substitute the VOLY checkout or server working directory.
2. **Governed chat:** retain `AIGateway.chat()` as the normal model-call boundary so its policy and accounting behavior applies. File-capable executor work is the intentional separate path.
3. **Distinct records:** telemetry, executor evidence/evaluation, A2A episodes, and plan state are related but separately owned contracts; do not collapse them into a generic run payload.
4. **Evidence before authority:** imported packs remain untrusted and staged; measured activation and remote publication are controls separate from ordinary capability matching.
5. **Local operational posture:** the open-core web surface is localhost-oriented. Read the operations and gateway pages before changing exposure, credentials, or Cloudflare request formats.

## Baseline setup and checks

The package requires Python 3.10 or later. The console command is `voly`, mapped to `voly.cli.main:main`; optional extras enable integrations such as the UI, MCP, DSPy, and Cursor support. A practical local baseline is:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
voly status
pytest tests/test_dspy_runtime_smoke.py
```

Use the focused test from the routing table for a scoped change, then run `pytest tests/ -q` when the change crosses subsystem boundaries.
