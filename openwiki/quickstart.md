---
type: task-routing guide
title: VOLY OpenWiki quickstart
description: A compact routing guide from VOLY's control-plane overview to the runtime, workflow, governance, operations, and Cloudflare domains that own a change. It identifies source and focused-test starting points for safe investigation.
tags: [voly, control-plane, task-routing, workflows, cloudflare]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-06T11:56:59.124Z
sources:
  - id: openwiki-source-49dac69e7cd89725e140534d
    resource: repo://cf-workers/a2a/src/index.ts
  - id: openwiki-source-bca312966fcb71696d24c76b
    resource: repo://cf-workers/capability/src/index.ts
  - id: openwiki-source-0c6a0e412756246a751a9110
    resource: repo://cf-workers/memory/src/index.ts
  - id: openwiki-source-ff3788c0373ac1633e148b1d
    resource: repo://cf-workers/spend/src/index.ts
  - id: openwiki-source-97e7ae32b8000e9858c739cf
    resource: repo://cf-workers/telemetry/src/index.ts
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-81efd633b7a2af55b81ac9ad
    resource: repo://tests/test_quickstart.py
  - id: openwiki-source-ba2a4a06650e64c79b3cf0da
    resource: repo://tests/test_sdk_workflow.py
  - id: openwiki-source-76023a3fd121eb38b84b1207
    resource: repo://voly.yaml
  - id: openwiki-source-d5ea337baaf9428410f42e17
    resource: repo://voly/__init__.py
  - id: openwiki-source-977fb78553c15ddb8fb9192d
    resource: repo://voly/cli/commands/quickstart.py
  - id: openwiki-source-39cd68eedf8803d03d89bf6e
    resource: repo://voly/config/_types.py
  - id: openwiki-source-eab7650692ea2fcc8fde0182
    resource: repo://voly/plan/runner.py
  - id: openwiki-source-3c206cdc55bd443f89e25262
    resource: repo://voly/plan/store.py
  - id: openwiki-source-9d5245197292fe86e38c083e
    resource: repo://voly/sdk/workflow.py
generated: { by: "openwiki/0.5.0", at: "2026-09-06T11:56:59.124Z" }
---

# VOLY OpenWiki quickstart

VOLY is a Python control plane around AI-agent execution: its public package exposes the pipeline and router alongside the durable `Agent`/`Workflow` SDK, and the `voly` console script enters the Click CLI. Start with the [control-plane architecture](architecture/overview.md) for the model-gateway versus file-executor boundary, then use this page to choose the owner of the behavior you intend to change.

## Route the task

| If the change concerns… | Go to | Start investigation at | Focused tests / first check |
|---|---|---|---|
| Gateway calls, providers, spend/cost controls, executor fallback, telemetry, or the fundamental chat-versus-file-execution split | [Control-plane architecture](architecture/overview.md) | `voly/ai_gateway/`, `voly/runner/agent_runner.py`, `voly/telemetry.py` | `pytest tests/test_ai_gateway.py tests/test_executor_safety.py -q` |
| Pipeline dispatch, decomposition, local/hybrid roles, A2A federation, episode records, or the read-only judge | [Pipeline and A2A orchestration](orchestration/a2a-and-pipeline.md) | `voly/pipeline/`, `voly/a2a/` | `pytest tests/test_a2a_p0.py tests/test_hybrid_a2a.py tests/test_agentic_judge.py -q` |
| A Python graph built with `Agent`, `Workflow`, or a preset; dependency validation; plan persistence; approvals; verification; cancellation; or resume | [Durable plans and Python workflow SDK](orchestration/durable-workflows.md) | `voly/sdk/{agent,workflow,presets}.py`, `voly/plan/{engine,runner,store,approval}.py` | `pytest tests/test_sdk_workflow.py tests/test_sdk_presets.py tests/test_plan_approval.py tests/test_plan_concurrency.py -q` |
| Importing, staging, evaluating, activating, retiring, matching, or publishing a capability pack/profile | [Capability governance](governance/capabilities.md) | `voly/capability/`, `cf-workers/capability/` | `pytest tests/test_capability_pack_import.py tests/test_evaluated_capability_packs.py tests/test_capability_remote_sync.py -q` |
| CLI/API/UI entrypoints, `--cwd` isolation, configuration, executor safety, local artifacts, or operational verification | [Entrypoints, configuration, and safety](operations/entrypoints-and-safety.md) | `voly/cli/main.py`, `voly/cli/commands/quickstart.py`, `voly/config/`, `voly/web/` | `pytest tests/test_quickstart.py tests/test_cli_contracts.py tests/test_web_api.py -q` |
| Optional remote A2A, capability, memory, spend/AG-UI, telemetry, catalog, marketplace, or agent-worker services | [Cloudflare worker service boundaries](integrations/cloudflare-services.md) | `cf-workers/`, `voly/{a2a,memory,spend,agui}/`, `voly/web/routes/cf.py` | Begin with the relevant Python-client test, for example `pytest tests/test_a2a_federation.py tests/test_memory_client.py tests/test_spend_client.py -q` |

### Two adjacent but different orchestration surfaces

Use the pipeline/A2A page for a task submitted to VOLY and dynamically routed among its operational roles. Use the durable-workflows page when a caller explicitly declares a reusable graph in Python. The SDK is deliberately a builder over the existing plan runtime: `Workflow.compile()` makes a validated `Plan`, while `run()` and `resume()` delegate execution and persistence to `PlanRunner` and `PlanStore`. Its nodes may still be chat or executor agents, so it preserves the same underlying gateway/executor boundary rather than introducing a second agent runtime.

A declared workflow is durable state, not an in-memory promise: `PlanStore` atomically writes each plan document and propagates I/O errors. The runner validates the plan, saves it as running, and persists it while enforcing dependency gates. Independent **chat** nodes can run in bounded waves; executor nodes remain serial because they share the plan `cwd`. Approval checks park a step in `verifying` until an explicit external decision, and callers resume by the prior `plan_id`; cancellation is cooperative between waves or steps rather than an interruption of an in-flight call.

## Repository map: ownership, not an inventory

- `voly/` is the Python product. The important seams are `ai_gateway/` for governed model calls, `runner/` and `executor/` for file-capable execution, `pipeline/` and `a2a/` for automatic orchestration, `capability/` for governed selection, `plan/` for durable execution state, and `sdk/` for the public graph API.
- `cf-workers/` is a set of optional service deployments, not the local control plane. Its boundaries include A2A registry/task dispatch, capability profiles and evaluated snapshots, semantic memory, spend and AG-UI session state, telemetry ingest, plus catalog, marketplace, and agent services. Consult the Cloudflare page before coupling Python behavior to any worker storage or authentication contract.
- `tests/` is the behavioral contract suite. Prefer the narrow test group in the routing table before the full suite; `pyproject.toml` configures pytest to discover `tests/test_*.py`.
- `voly.yaml` is an example configuration surface. It shows local `.voly/` persistence locations and optional remote endpoints such as `CF_WORKER_MEMORY_URL`, `CF_WORKER_A2A_URL`, `CF_WORKER_AGUI_URL`, and `CF_WORKER_SPEND_URL`; do not treat those remote workers as mandatory for a local change.
- `ui/` and `voly/web/` meet at the API/dashboard boundary. Route a backend contract, server, or safety issue to Operations first; route remote service configuration/status to Cloudflare services.

## Safe first pass for a coding agent

1. Read the linked owner page and its focused tests before changing a cross-domain behavior. Follow callers and persisted formats, not only the named entry file.
2. For a target repository, run the read-only readiness check before a file-writing experiment:

   ```bash
   voly quickstart --check --cwd ~/my-project
   ```

   It reports missing/invalid configuration and absent supported executors, warns when the directory is not a Git repository, and only suggests a `--dry-run` command. Without `--check`, `--yes` may create a missing `voly.yaml`, but only after readiness blockers are clear.
3. Keep target-project behavior behind `--cwd` (or the corresponding configuration), preserve the model-gateway/file-executor separation, and treat event, plan, evidence, snapshot, and remote-worker payloads as contracts. Run the smallest affected test set, then expand when a boundary or serialized shape changed.

## Cloudflare boundary checklist

Cloudflare integrations are opt-in remote services configured by URLs and, where required, bearer tokens. They should not silently become a prerequisite for local workflows. Each worker enforces its own optional `API_TOKEN`: when configured, requests lacking the matching `Authorization: Bearer` value receive `401`.

The service names are not interchangeable:

- The A2A worker keeps agent cards and task state in D1 and can queue an asynchronous task for a named agent.
- The memory worker creates embeddings, indexes semantic metadata in Vectorize, keeps records in D1, and writes a JSON representation to R2.
- The spend worker fronts separate Durable Objects for aggregate spend and AG-UI sessions; AG-UI WebSocket routing is a session concern, not a general workflow executor.
- The telemetry worker ingests `TaskEvent`-shaped records, preserves the full event in R2, and maintains a D1 query index.
- The capability worker owns remote role/profile/match/leaderboard/evaluated routes. Catalog, marketplace, agent, and the reserved workflow deployment directories belong to the same integration domain but require their own source contract review.

For configuration or client failures, investigate the Python client and worker together; do not infer a storage schema from an environment variable alone.
