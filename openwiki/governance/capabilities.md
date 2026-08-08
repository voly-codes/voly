---
type: Governance Guide
title: Capability governance and evaluated packs
description: Explains VOLY's executor capability matching, untrusted external-pack intake, measured evaluated-pack activation, and verified Cloudflare snapshot publication.
tags: [voly, capability, governance, security, cloudflare, evaluation]
---

# Capability governance and evaluated packs

VOLY separates ordinary executor/profile matching from the optional **evaluated capability-pack** overlay. The base registry and `ExecutorMatcher` select suitable local or remote profiles. Evaluated packs add a measured capability choice before that matcher; they do not replace native routing. This separation protects the runtime described in [architecture overview](../architecture/overview.md) from unproven imported behavior.

## Two related mechanisms

| Mechanism | Purpose | Fallback / boundary |
|---|---|---|
| Capability registry and matcher | Match executor/model-provider profiles to a role, dimension, task features, and routing policy. | Local behavior is the fallback if remote balanced-policy matching fails. |
| Evaluated packs | Select an active, evidence-bearing task capability, then delegate executor/model selection to the existing matcher. | Inactive, retired, unmeasured, unmatched, or degraded packs return explicit native VOLY fallback. |

A2A lead assignment can use this matching information for role routing, so [pipeline and A2A orchestration](../orchestration/a2a-and-pipeline.md) depends on capability data without making all multi-agent work an evaluated experiment.

## External content intake is inert

`voly capability import ecc --source … --dry-run` is intentionally discovery-only: it inventories supported source content but does not install, load, execute hooks/commands, or start MCP servers. Admission validates bounded content, normalizes findings, infers permissions, checks MCP shape, prevents source-root path escapes, and can quarantine high/critical-risk content.

`voly capability pack install` atomically stages only admitted material under `.voly/capability/packs/`. Manifests and component hashes are verified; unexpected, missing, modified, or escaping files invalidate the staged pack. Successful staging is not activation. This creates a trust boundary before evaluated variants can render any declared staged instruction source.

## Measured lifecycle

The evaluated router requires a pack to be active, evidence-bearing, role-compatible, and trigger-matched. Paired baseline/variant evidence is append-only local JSONL, and each experiment may change only one capability. Records retain completion/test outcomes, rollback/correction/reviewer acceptance, quality delta, latency/tokens, cost availability, and held-out status.

The production gate currently requires six measured outcomes including two held-out outcomes. It activates only when paired value and all success/efficiency criteria pass; it retires a failed value hypothesis early only after three samples with the required held-out evidence. The bundled 20-task suite is a routing probe: it uses synthetic activation, makes no model calls, persists nothing, and explicitly cannot activate a pack.

This lifecycle **uses evidence distinct from** task telemetry and A2A episodes. That distinction keeps a routing test or self-reported task completion from becoming activation proof. See [architecture overview](../architecture/overview.md) for the broader durable-record model.

A governance caveat: direct `evaluated activate` requires some measured evidence, while `activate-ready --yes` recomputes the full production decision. Automation must use the intended command and must not treat the offline benchmark as validation.

## Verified remote snapshot publication

`voly capability evaluated sync` is authenticated publication to the capability worker, not remote instruction activation or `/match` enforcement. The client builds a bounded canonical snapshot of definitions, local state, decisions, metrics, and provenance hashes—excluding raw prompts and individual evidence records. It hashes canonical content into the snapshot ID, uploads, performs authenticated read-back, and writes a local receipt only when content exactly matches.

Receipt freshness is tied to the packs/evidence store state. Cloud deployment readiness additionally requires at least one validated capability, no incomplete pilots, a worker that supports the contract, a current verified receipt, and explicit configuration/deployment approval. The worker’s D1 snapshot/state storage is a publication and audit surface; treat any change that makes it runtime enforcement as a new trust-boundary design.

[Operations, entrypoints, and safety](../operations/entrypoints-and-safety.md) maps the CLI/config/runtime-state controls around this workflow.

## Change checklist

- Keep external discovery and staged content inert; never execute newly admitted components by implication.
- Preserve manifest/hash verification before rendering staged variant text.
- Keep native fallback explicit for every unqualified evaluated route.
- Test validation thresholds, held-out requirements, and the distinction between early retirement and activation.
- Keep Python and Worker canonical serialization compatible before changing snapshot schema or number handling.
- Verify remote sync with upload plus read-back; publication is not authorization to alter runtime routing.

**Useful sources:** `voly/capability/{matcher.py,registry.py,packs.py,pack_admission.py,pack_store.py,evaluated_packs.py,validation.py,remote_sync.py}`, `voly/cli/commands/capability_*.py`, `cf-workers/capability/`, `docs/backend/{capability.md,evaluated-capability-packs.md,production-validation.md}`, `tests/test_capability_*.py`, `tests/test_evaluated_capability_packs.py`.
