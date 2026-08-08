---
type: Architecture Overview
title: VOLY control-plane architecture
description: Explains VOLY's project-agnostic execution split, control boundaries, durable records, and model-versus-executor responsibilities.
tags: [voly, architecture, gateway, executors, telemetry]
---

# VOLY control-plane architecture

VOLY sits between an operator and agents that reason about or modify another repository. The target project is passed at runtime, so VOLY can enforce common routing, economics, safety, and observability rules without embedding product-specific behavior. `README.md` and `docs/ARCHITECTURE.md` are the primary product and system references.

## Two paths, one control plane

| Path | Primary implementation | Responsibility |
|---|---|---|
| Pipeline / inference | `voly/pipeline/core.py` | Route text work; compose memory, skills, token handling, optional DSPy, and model inference. |
| Executor / file work | `voly/runner/agent_runner.py` | Run a file-capable agent against `cwd`, manage billing fallback, capture a work report, and emit run records. |

The [pipeline and A2A orchestration](../orchestration/a2a-and-pipeline.md) page describes how a complex pipeline task can dispatch dependency-linked roles, including hybrid roles that use the executor path. This is not a general license for arbitrary writes: executor behavior remains bound to the supplied target project and the runner's safety/evidence policies.

## Gateway boundary

`AIGateway.chat()` is the canonical boundary for chat-model calls. Its enabled path checks DLP, derives a scope-aware cache key, checks rate and spend limits, invokes either a Cloudflare provider path or delegated/direct adapter, marks provider health on failures, and records spend only after a successful result. It can delegate a request to a configured upstream gateway and then fall back to the original direct adapter when that upstream fails.

The gateway therefore **shares cost and safety infrastructure with** A2A chat roles, DSPy, and ordinary pipeline inference. File-capable executors remain a separate mechanism, even when a hybrid A2A role invokes them. Preserve that distinction when adding providers or fallback: a text-only provider should not silently become an executor.

## Durable records and contracts

VOLY keeps related but distinct records:

- **`TaskEvent`** telemetry describes a run for CLI/API/UI visibility. `docs/ARCHITECTURE.md` identifies it as a versioned schema contract and ties it to `correlation_id` propagation.
- **Evidence and evaluation records** describe repository baseline, execution bundle, root-cause attribution, deterministic checks, and optional human feedback. `AgentRunner` creates this evidence around file-capable runs when enabled; it must not be conflated with telemetry.
- **A2A episodes** capture multi-agent lineage—traces, artifacts, decisions, metrics, and costs—under `<cwd>/.voly/episodes/`. They **link orchestration to** evidence/evaluation without replacing those schemas; see [pipeline and A2A orchestration](../orchestration/a2a-and-pipeline.md).
- **Capability-pack evidence and snapshots** are governance records used to decide whether an optional variant has measured value. They are not normal routing telemetry; see [capability governance](../governance/capabilities.md).

These record boundaries exist so operational visibility, evaluation evidence, agent lineage, and capability experiments can evolve without silently changing each other’s semantics.

## Runtime and deployment edges

The Python package exposes a Click CLI (`voly.cli.main:main`) and optional FastAPI UI/API extras. The Svelte dashboard is a separate Vite application under `ui/`; when its assets are built, FastAPI can serve them. Cloudflare workers provide remote boundaries such as capability snapshots and A2A federation, not replacements for local runtime source of truth.

[Operations, entrypoints, and safety](../operations/entrypoints-and-safety.md) explains how these surfaces are configured and checked. That page is also the canonical place for local-runtime artifacts and test guidance.

## Change checklist

- Keep model calls behind `AIGateway.chat()` unless a source-backed exception is intentionally designed.
- Preserve spend-on-success accounting; failures must not inflate daily usage.
- Update versioned protocol tests and documentation when event, evidence, or worker payload shapes change.
- Treat `cwd` isolation and file-executor safety as architecture, not convenience.
- For orchestration changes, verify local and federation modes separately; for capability changes, preserve native fallback and the separate measured-validation gate.

**Useful sources:** `docs/ARCHITECTURE.md`, `README.md`, `voly/ai_gateway/gateway.py`, `voly/runner/agent_runner.py`, `voly/telemetry.py`, `voly/evidence/`, `tests/test_protocol_contracts.py`.
