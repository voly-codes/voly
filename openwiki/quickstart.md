---
type: quickstart guide
title: VOLY OpenWiki quickstart
description: Task-routing guide for VOLY coding agents. Use it to identify the smallest authoritative architecture, orchestration, workflow, governance, or operations guide, then start from the relevant source and focused tests.
tags: [voly, quickstart, control-plane, task-routing, testing]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T12:39:44.580Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-81efd633b7a2af55b81ac9ad
    resource: repo://tests/test_quickstart.py
  - id: openwiki-source-bd45d97ff1d44099fbedafcc
    resource: repo://tests/test_smoke.py
  - id: openwiki-source-d5ea337baaf9428410f42e17
    resource: repo://voly/__init__.py
  - id: openwiki-source-977fb78553c15ddb8fb9192d
    resource: repo://voly/cli/commands/quickstart.py
  - id: openwiki-source-3cbe083798ded0438463ec65
    resource: repo://voly/cli/commands/run_cmd.py
  - id: openwiki-source-4179cef67895cf94beb7d680
    resource: repo://voly/cli/main.py
generated: { by: "openwiki/0.6.0", at: "2026-09-26T12:39:44.580Z" }
---

# VOLY OpenWiki quickstart

VOLY is a Python control plane for routing, orchestrating, budgeting, and verifying AI coding-agent work. It is not the target application: file-capable work is scoped to an explicit target repository, normally through `--cwd`. The installed `voly` command enters the Click group at `voly.cli.main:main`; the top-level Python package also exports the `Workflow` SDK alongside `Pipeline`, `AgentRouter`, and configuration types.

**Use this page as a router, not as a replacement for source.** Generated OpenWiki is optional just-in-time context. Source code and tests define behavior; begin with the narrowest domain below, follow its linked guide, and validate with the focused tests before widening scope.

## First safe check

For an installed package, check a candidate target repository without running an agent:

```bash
voly quickstart --check --cwd ~/my-project
```

The command inspects the directory, Git presence, local `voly.yaml` status, and available executors, then prints a suggested executor command with `--dry-run`. `--check` does not create configuration; without `--check`, `--yes` creates a missing `voly.yaml` only after the readiness result has no blockers. It never starts an agent itself. A non-Git directory is a warning, because Git-backed rollback and diff checks are weaker; a missing directory, invalid configuration, or no detected supported executor is a blocker.

For repository development, the project requires Python 3.10 or newer and exposes the same console script through the package metadata:

```bash
python -m pip install -e ".[dev]"
pytest tests/test_smoke.py -q
```

`tests/test_smoke.py` is the broad packaging/import and no-network CLI smoke net, not a substitute for the narrower behavioral tests in the routing map.

## Route a change to the smallest guide

| If the task changes or asks about… | Read this guide first | Start from these source boundaries | Focused tests and first validation |
|---|---|---|---|
| The project-`cwd` boundary; governed model inference versus file-capable execution; gateway/provider behavior; telemetry, evidence, or Cloudflare integration edges | [Control-plane architecture](architecture/overview.md) | `voly/ai_gateway/gateway.py`, `voly/runner/agent_runner.py`, `voly/telemetry.py` | `tests/test_ai_gateway.py`, `tests/test_gateway_provider_health.py`, `tests/test_executor_cwd_and_a2a_call.py`, `tests/test_protocol_contracts.py`<br>`pytest tests/test_ai_gateway.py -q` |
| Task decomposition, automatic or explicit A2A delegation, local dependency waves, federated dispatch, hybrid chat/executor roles, episodes, or the read-only judge | [Pipeline and A2A orchestration](orchestration/a2a-and-pipeline.md) | `voly/pipeline/`, `voly/pipeline/stages_a2a.py`, `voly/a2a/multiagent_run.py`, `voly/a2a/agentic_judge.py` | `tests/test_a2a_p0.py`, `tests/test_hybrid_a2a.py`, `tests/test_a2a_federation.py`, `tests/test_agentic_judge.py`<br>`pytest tests/test_a2a_p0.py -q` |
| A durable plan, dependency or verification gate, human approval, workflow concurrency/resume/cancellation, or the public Python `Agent`/`Workflow` SDK and presets | [Plan engine and workflow SDK](workflows/sdk-and-plan-execution.md) | `voly/plan/`, `voly/sdk/`, `voly/workflow/`, `voly/__init__.py` | `tests/test_plan_engine.py`, `tests/test_plan_runner.py`, `tests/test_plan_approval.py`, `tests/test_sdk_workflow.py`<br>`pytest tests/test_plan_runner.py -q` |
| Executor/profile matching; importing or staging external capability packs; evaluated-pack evidence, activation, native fallback, or verified remote snapshot publication | [Capability governance and evaluated packs](governance/capabilities.md) | `voly/capability/`, `voly/cli/commands/capability_cmd.py`, `voly/cli/commands/capability_pack_cmd.py`, `voly/cli/commands/capability_evaluated_cmd.py` | `tests/test_capability_pack_import.py`, `tests/test_capability_pack_store.py`, `tests/test_evaluated_capability_packs.py`, `tests/test_capability_remote_sync.py`<br>`pytest tests/test_capability_pack_import.py -q` |
| Commands, CLI/API/UI/pipeline-server entrypoints, configuration/environment resolution, runtime records, target-repository write safety, dry runs, or operational exposure | [Entrypoints, configuration, and safe execution](operations/entrypoints-and-safety.md) | `voly/cli/main.py`, `voly/cli/commands/run_cmd.py`, `voly/config/`, `voly/web/`, `voly/pipeline_server.py`, `voly/runner/agent_runner.py` | `tests/test_cli_contracts.py`, `tests/test_config.py`, `tests/test_executor_safety.py`, `tests/test_web_api.py`, `tests/test_pipeline_server.py`<br>`pytest tests/test_executor_safety.py -q` |

## Choose the execution boundary before changing behavior

`voly run` has two intentionally different paths:

- With `--executor`, the command constructs `AgentRunner` and passes it a `cwd` (the supplied path or the process working directory). This is the file-capable path, and `--dry-run` is passed to its safety policy.
- Without `--executor`, it constructs `Pipeline`, passes optional `cwd`/repository context, and runs inference/orchestration. The CLI explicitly warns that `--dry-run` is ignored on this pipeline path.

Do not solve a chat-provider change by bypassing `AIGateway.chat()`, and do not treat a file executor as a normal model call. The architecture guide explains the full ownership, fallback, evidence, and telemetry distinctions; the operations guide explains the Git-based safety behavior.

## Change discipline

1. **Keep target scope explicit.** Do not embed product-specific paths under `voly/`; provide or resolve the target repository deliberately through `--cwd` and the documented configuration boundary.
2. **Preserve the owner of state.** A plan/workflow, multi-agent episode, task telemetry event, executor evidence/evaluation, and capability decision are separate records with separate contracts. Follow the linked domain rather than merging their semantics opportunistically.
3. **Treat capability content as untrusted.** Discovery and staging do not activate imported instructions, hooks, commands, or remote state. Preserve evidence-gated activation and explicit native fallback.
4. **Treat runtime output as sensitive local state.** `.voly/` may contain task, repository, evidence, run, cache, and report context. Do not commit it or put secrets in configuration, tests, documentation, or logs.
5. **Test the affected contract first.** Run the table’s smallest test command, preserve failures, then add adjacent focused tests only when the boundary you changed requires them.

## Repository landmarks

- `voly/` contains the Python runtime; `pyproject.toml` declares the `voly` console script and the package/development optional dependencies.
- `tests/` is the behavioral and compatibility suite. `tests/test_smoke.py` verifies core imports, basic CLI commands, package declarations, and selected telemetry behavior without requiring external services.
- `ui/` and `voly/web/` form the optional dashboard/API surface; `cf-workers/` is an optional Cloudflare integration boundary, not the source of truth for local project state.
- `AGENTS.md` supplies repository-wide agent rules: use `AIGateway.chat()` for model calls except file-capable executors, keep target work behind `--cwd`, and treat OpenWiki as optional context.
