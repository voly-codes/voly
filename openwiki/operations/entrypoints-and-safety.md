---
type: Operations Guide
title: Entrypoints, configuration, and safety
description: Operational map for VOLY's CLI, FastAPI/Svelte UI, configuration, local runtime artifacts, security posture, and verification workflow.
tags: [voly, operations, cli, api, ui, configuration, testing]
openwiki:
  roles: [operations, repository]
  change_kinds: [entrypoints, configuration, documentation-automation]
  source_paths: [pyproject.toml, voly/cli/main.py, voly/web/server.py, .github/workflows/openwiki-update.yml]
  test_paths: [tests/test_cli_*.py, tests/test_web_api.py, tests/test_web_registry.py]
  invariants: [The generated wiki is optional just-in-time context; source code and tests remain authoritative.]
  validation_commands: [pytest tests/test_web_api.py -q]
---

# Entrypoints, configuration, and safety

VOLY’s operational surfaces submit work to the pipeline or executor architecture and expose its run state. This page is the companion to [architecture overview](../architecture/overview.md): use it for configuration and operational changes, then follow the architecture link for the execution boundary affected.

## Entry points

- **CLI:** `pyproject.toml` exposes `voly = voly.cli.main:main`. The Click command group registers task execution, setup, status, UI/server, catalog/registry, telemetry, and capability command families. `voly run` is the primary local automation surface.
- **Web/API:** `voly/web/server.py:create_app()` creates the optional FastAPI application used by `voly ui`. It wires route modules for run/tasks/runs, telemetry, gateway, evidence, marketplace, capability, and related services; it also supplies correlation middleware and a watchdog for stale run records.
- **Dashboard:** `ui/` is a Svelte 5/Vite app. `App.svelte` starts task refresh/SSE streaming and presents run, gateway, telemetry, DSPy, Cloudflare, marketplace, and plugin drawers. Built assets can be served by FastAPI.
- **Documentation automation:** `.github/workflows/openwiki-update.yml` runs daily at 08:00 UTC or on manual dispatch. It installs OpenWiki, runs `openwiki code --update --print`, and creates or force-updates the `openwiki/update` pull-request branch when the staged changes include `openwiki/`, `AGENTS.md`, `CLAUDE.md`, or the workflow itself. The generated wiki is optional just-in-time context; source code and tests remain authoritative.

CLI/API callers supply `cwd` to identify the target project. For complex work, those entrypoints can initiate the [pipeline and A2A orchestration](../orchestration/a2a-and-pipeline.md) flow; simple file work reaches `AgentRunner` directly.

## Configuration and sensitive material

`voly.yaml` is the checked-in runtime configuration; `voly/config/` owns typed defaults and parsing. `codeops.yaml` is a broader repository-level orchestration configuration. `.env.example` is a placeholder-only reference for environment-variable setup; never put secret values in documentation or source.

The web app loads a root `.env` at startup if present. That behavior means development and deployment changes need special care: avoid relying on unchecked local state, and never expose a service externally without reviewing the documented authentication/CORS configuration in `docs/backend/api.md` and `docs/backend/config.md`.

The UI/API optional dependency group is `voly[ui]`; development tools live under `voly[dev]`; other extras are separately declared in `pyproject.toml`. Update packaging lists with new importable packages because editable installs can hide an omitted wheel package.

## Runtime state and privacy

Generated state is deliberately outside source control, primarily below `.voly/`: events, runs, evidence, evaluation reports, episodes, gateway cache, DSPy artifacts, reports, and capability stores/packs. Local records may hold richer task and repository context than remote analytics. Do not promote those artifacts to committed fixtures without a deliberate privacy review.

`correlation_id` connects request, logs, SSE/API outcomes, and TaskEvent visibility. Preserve it across new entrypoint layers and do not change it casually in a UI-only patch.

Capability operations are especially sensitive: [capability governance](../governance/capabilities.md) explains why staged external content, validated activation, and remote snapshots are separate. Configuration or CLI work must preserve those gates.

## Verification workflow

The project uses pytest (`tests/`, configured in `pyproject.toml`) plus Ruff/Mypy tooling. Run focused tests for the behavior you change, then broader relevant suites:

| Change area | Focused checks |
|---|---|
| Pipeline/A2A/hybrid/judge | `tests/test_a2a_*.py`, `tests/test_hybrid_a2a.py`, `tests/test_agentic_judge.py` |
| Gateway/provider/spend | `tests/test_ai_gateway.py`, `tests/test_gateway_provider_health.py`, `tests/test_failure_paths.py` |
| Executors/evidence/evaluation | `tests/test_executor_*.py`, `tests/test_evidence_*.py`, `tests/test_evaluation.py` |
| Capability lifecycle/sync | `tests/test_capability_*.py`, `tests/test_evaluated_capability_packs.py` |
| CLI/API/UI integration | `tests/test_cli_*.py`, `tests/test_web_api.py`, `tests/test_web_registry.py` |
| Packaging/docs | `tests/test_smoke.py`, `scripts/check_doc_links.py`, `scripts/check_env_doc_sync.py` |

Use `docs/backend/` as the detailed behavior reference and update the matching document with source changes, as repository guidance requires.

## Change checklist

- Keep CLI arguments, API request/event shapes, frontend client/store expectations, and route implementation synchronized.
- Preserve `cwd` as the target-project boundary; do not hardcode a product repository.
- Do not read, log, document, or commit live secrets; point users to placeholder setup or secret-management controls.
- Run the smallest relevant test slice first; include contract/packaging checks when changing public surfaces.
- Inspect `git status` before committing: local logs and generated `.voly` state are not change inputs unless explicitly intended.

**Useful sources:** `pyproject.toml`, `voly/cli/main.py`, `voly/web/server.py`, `voly/web/routes/`, `voly.yaml`, `.env.example`, `ui/{package.json,src/App.svelte}`, `docs/backend/{api.md,config.md,executors.md}`, `tests/`, `.github/workflows/openwiki-update.yml`.
