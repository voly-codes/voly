---
type: change-routing guide
title: VOLY OpenWiki quickstart
description: A compact routing guide for safely changing VOLY. Start from its public surfaces, choose the governed chat or file-capable execution path, then use the focused architecture, runtime, orchestration, governance, integration, operations, and testing pages.
tags: [voly, quickstart, change-routing, control-plane, testing]
verified:
  - by: openwiki/0.5.1
    at: 2026-09-12T11:58:19.578Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-81efd633b7a2af55b81ac9ad
    resource: repo://tests/test_quickstart.py
  - id: openwiki-source-d5ea337baaf9428410f42e17
    resource: repo://voly/__init__.py
  - id: openwiki-source-977fb78553c15ddb8fb9192d
    resource: repo://voly/cli/commands/quickstart.py
  - id: openwiki-source-3cbe083798ded0438463ec65
    resource: repo://voly/cli/commands/run_cmd.py
generated: { by: "openwiki/0.5.1", at: "2026-09-12T11:58:19.578Z" }
---

# VOLY OpenWiki quickstart

VOLY is a project-agnostic control plane for AI-agent work. The target repository is supplied at runtime through `cwd` (normally `--cwd`), rather than encoded as product-specific behavior under `voly/`. Its public Python surface exports configuration, the `Pipeline`, routing, and the `Agent`/`Workflow` SDK; the installed operational surface is the `voly` CLI.

**Use this page as a routing aid, not as a substitute for investigation.** Source code and tests are authoritative. Generated OpenWiki pages are optional just-in-time context: read the narrow linked page for the change, then follow its cited code and focused tests.

## Begin with the public surface

| If the change starts at… | Start with | Then inspect |
| --- | --- | --- |
| A Python import or SDK `Agent`/`Workflow` behavior | [Control-plane architecture](architecture/overview.md) | [Plans, approvals, and bounded workflows](orchestration/plans-and-workflows.md) for durable workflow/approval behavior; [gateway and FinOps](runtime/gateway-and-finops.md) for chat calls. |
| `voly` CLI, `voly.yaml`, environment/config discovery, hooks, `quickstart`, `serve`, or `ui` | [Entrypoints, configuration, and operational safety](operations/entrypoints-and-safety.md) | [Testing and compatibility](testing/verification-strategy.md) for command, packaging, and API checks. |
| Web UI, FastAPI/SSE, MCP, or Cloudflare service boundary | [Web, Cloudflare, and external integrations](integrations/cloudflare-and-web.md) | [Entrypoints and safety](operations/entrypoints-and-safety.md) for local exposure/configuration and [testing](testing/verification-strategy.md) for API/run-state coverage. |
| A prompt/model call, provider, cache, DLP, budget, BYOK, or gateway fallback | [Model gateway, provider routing, and FinOps](runtime/gateway-and-finops.md) | [Control-plane architecture](architecture/overview.md) for the model-versus-executor boundary. |
| A file-writing agent/executor, `--cwd`, diff, dry-run, rollback, timeout, or executor billing fallback | [File-capable executor run lifecycle](runtime/executor-runs.md) | [Entrypoints and safety](operations/entrypoints-and-safety.md) and [testing](testing/verification-strategy.md). |
| Pipeline dispatch, role decomposition, A2A, federation, hybrid work, dependency handoff, or judge | [Pipeline dispatch and A2A orchestration](orchestration/a2a-and-pipeline.md) | [Executor runs](runtime/executor-runs.md) for hybrid writer roles and [plans and workflows](orchestration/plans-and-workflows.md) for attached verification gates. |
| Plan states, acceptance criteria, approval, SDK compilation, resume/cancel, or the review loop | [Plans, approvals, and bounded workflows](orchestration/plans-and-workflows.md) | [Testing](testing/verification-strategy.md) for plan failure and compatibility cases. |
| Executor profiles, imported packs, evaluated routing, capability evidence, activation, or snapshot sync | [Capability registry and evaluated-pack governance](governance/capabilities.md) | [Evidence, evaluation, and durable run records](governance/evidence-and-evaluation.md) for distinct evidence and telemetry lifecycles. |
| Repository baseline, evaluation policy/judge, human feedback, golden replay, telemetry, privacy, or live run records | [Evidence, evaluation, and durable run records](governance/evidence-and-evaluation.md) | [Testing](testing/verification-strategy.md) and [executor runs](runtime/executor-runs.md). |
| Unsure which tests or validation scope applies | [Testing and compatibility strategy](testing/verification-strategy.md) | Return to the owning runtime/orchestration/governance page named above. |

## Choose the execution path before changing it

`voly run` has two different paths. Without `--executor`, the command creates a `Pipeline`, passes optional `cwd` as context, and runs orchestration/inference; `--dry-run` is ignored on this path. With `--executor`, it creates `AgentRunner`, uses the supplied `cwd` (or process directory), and passes `dry_run` to the file-capable run. Do not treat either path's fallback, cost, or safety semantics as an implementation detail of the other.

| Path | Boundary to preserve | Focused reading |
| --- | --- | --- |
| **Pipeline / chat path** — `voly run "…"` without `--executor`; pipeline, A2A chat roles, and SDK chat work | `AIGateway.chat()` is the governed model-call boundary. Gateway controls and provider/model fallback are separate from executor fallback. | [Gateway and FinOps](runtime/gateway-and-finops.md) → [A2A and pipeline](orchestration/a2a-and-pipeline.md) → [architecture](architecture/overview.md) |
| **File-capable executor path** — `voly run "…" --executor <name> --cwd <target>` | The executor acts on the concrete target directory. `AgentRunner` owns worktree reporting, safety policy, executor availability/billing fallback, and final run accounting. | [Executor runs](runtime/executor-runs.md) → [entrypoints and safety](operations/entrypoints-and-safety.md) → [evidence/evaluation](governance/evidence-and-evaluation.md) |
| **Hybrid local A2A** — a pipeline graph with eligible roles and a concrete `cwd` | Chat roles stay on the gateway path; writer roles use the executor path and must not concurrently mutate the same checkout. | [A2A and pipeline](orchestration/a2a-and-pipeline.md) → [executor runs](runtime/executor-runs.md) → [plans and workflows](orchestration/plans-and-workflows.md) |

For an unfamiliar target, perform the read-only readiness check first:

```bash
voly quickstart --check --cwd ~/my-project
```

It checks the supplied directory, reports non-Git rollback limitations, validates an existing target `voly.yaml`, detects a supported file-capable executor, and suggests a first command ending in `--dry-run`. A non-check invocation with `--yes` may create a missing target configuration without secrets; it does not overwrite an existing file.

## Safe change loop

1. **Locate the contract.** Start from the relevant table row and read the linked focused page. Follow its source/test references; do not infer behavior from this navigation page or from a generated record.
2. **Keep target locality.** Pass a concrete `--cwd` for target-repository work. Do not put target-product paths or logic in `voly/`.
3. **Preserve the execution boundary.** Route chat-model callers through the configured gateway path; use `AgentRunner` for file-capable work. Keep model fallback, A2A tier fallback, and executor billing/availability fallback distinct.
4. **Respect operational safety.** Treat `.env`, task text, diffs, and `.voly/` state as potentially sensitive. Use a dry run first when Git-backed rollback is available, inspect the returned diff/safety metadata, and do not commit generated `.voly/` state.
5. **Validate narrowly, then escalate.** Run the owning focused pytest module(s) first. Add contract/failure coverage when changing public formats, safety, persistence, fallback, budgets, or integration boundaries; run the full suite for shared configuration or broad changes.
6. **Keep project documentation synchronized.** A code-behavior change requires its matching `docs/backend/` or `docs/frontend/` update. Keep CLI/API/UI/result expectations aligned.

## Focused checks and execution boundaries

Use the exact module named by the relevant detailed page. Common first checks are:

```bash
pytest tests/test_ai_gateway.py -q
pytest tests/test_executor_safety.py -q
pytest tests/test_a2a_p0.py -q
pytest tests/test_hybrid_a2a.py -q
pytest tests/test_plan_verify.py -q
pytest tests/test_capability_production_validation.py -q
pytest tests/test_web_api.py -q
```

`pytest tests/ -q` is appropriate when a shared interface or broad refactor makes the focused result insufficient. The DSPy runtime smoke is required after changes:

```bash
pytest tests/test_dspy_runtime_smoke.py
```

Repository checks are designed to be hermetic. Run integration, multi-agent, and end-to-end work only in `/home/lanies/git/codeops/TEST_VOLY_JOB_MA/`, not in this repository; use an explicit target `--cwd` and favor a dry run before intentional real execution.

## Invariants worth carrying into every review

- **Project agnosticism:** runtime `cwd` selects the target; VOLY core does not encode a target product.
- **Two execution boundaries:** governed chat uses `AIGateway.chat()`; file-capable work uses executors through `AgentRunner`.
- **Local state and consent:** `.voly/` records are runtime artifacts. Local telemetry/evidence and optional remote projections have distinct purposes and privacy boundaries.
- **Safe extensibility:** capability discovery/staging, measured activation, and Cloudflare snapshot publication are separate controls; remote services are optional integrations rather than the local source of truth.
- **Tests and source win:** treat this OpenWiki map as optional context and verify behavior in source and focused tests before and after a change.
