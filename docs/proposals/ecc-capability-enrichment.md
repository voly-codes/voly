# Plan: ECC capability enrichment

## Goal

Enrich VOLY with reusable capability packs, research-first workflows, safe
continuous learning, compact project memory, and security admission without
turning the control plane into a bundled prompt collection.

## Complexity

- **Complexity:** complex
- **Executor class:** Codex
- **Delivery rule:** every completed phase is committed separately.
- **Commit author:** `Maksim Lanies <dev@voly.codes>`

## Product boundary

VOLY remains the execution control plane. ECC and similar repositories are
external capability providers. Imported content is inert until it passes
admission and is explicitly activated.

## Phase 0 — plan and contracts

- [x] Compare the VOLY and ECC product/architecture boundaries.
- [x] Identify the smallest useful vertical slice.
- [x] Define read-only import as the first delivery.
- [ ] Keep imported skills, agents, rules, hooks, MCP definitions, and commands
      separate from executor capability profiles.
- [ ] Define a versioned capability-pack contract before persistent install.

**Acceptance**

- [x] The implementation sequence is documented.
- [x] Security and rollback boundaries are explicit.

## Phase 1 — safe ECC discovery and dry-run import

- [ ] Add a generic external-pack discovery model.
- [ ] Add an ECC filesystem adapter.
- [ ] Discover agents, skills, rules, hooks, MCP configurations, and legacy
      command shims without executing repository content.
- [ ] Read provenance from Git metadata and package metadata when available.
- [ ] Produce deterministic JSON and human-readable reports.
- [ ] Add `voly capability import ecc --source <path> --dry-run`.
- [ ] Make dry-run mandatory in this phase; do not copy or activate content.
- [ ] Reject missing roots, malformed metadata, and paths escaping the source.
- [ ] Add unit and CLI tests.
- [ ] Document the command and security boundary.

**Acceptance**

- [ ] Running import against an ECC checkout reports inventory and provenance.
- [ ] No files are written outside test temporary directories.
- [ ] No hook, command, MCP server, or imported script is executed.

## Phase 2 — security admission

- [ ] Define normalized findings and permission declarations.
- [ ] Scan prompts and Markdown for instruction-injection indicators.
- [ ] Scan hooks and commands for subprocess, network, filesystem, secret, and
      destructive-operation risks.
- [ ] Parse MCP definitions without enabling servers.
- [ ] Add risk levels: `low`, `medium`, `high`, `critical`.
- [ ] Quarantine high-risk and critical components by default.
- [ ] Emit a machine-readable admission report.
- [ ] Add adversarial fixtures and tests.
- [ ] Update intelligence and capability documentation.

**Acceptance**

- [ ] Unsafe fixtures are denied or quarantined with evidence.
- [ ] Admission never executes imported content.

## Phase 3 — staged installation and provenance

- [ ] Define `capability-pack.yaml` schema v1.
- [ ] Store imported packs under a dedicated `.voly/capability/packs/` root.
- [ ] Record source, revision, license, hashes, admission result, and install
      time in immutable provenance metadata.
- [ ] Add explicit `install`, `list`, `show`, `verify`, and `remove` operations.
- [ ] Make install atomic and recoverable.
- [ ] Prevent imported packs from overwriting user-owned files.
- [ ] Add compatibility aliases for renamed skills and commands.

**Acceptance**

- [ ] Install and remove round-trip without touching unrelated files.
- [ ] Hash verification detects modified installed content.

## Phase 4 — research-first pilot

- [ ] Import or adapt only the `search-first` workflow initially.
- [ ] Add typed research output: candidates, selection, rejected alternatives,
      provenance, and `reuse | adapt | build` decision.
- [ ] Use local code/docs and the existing reuse registry before network search.
- [ ] Apply research only to tasks whose size or risk justifies it.
- [ ] Add shadow mode that records the recommendation without changing routing.
- [ ] Benchmark current VOLY against VOLY plus research-first.

**Acceptance**

- [ ] Research reduces unnecessary custom implementation on the pilot suite.
- [ ] Cost and latency stay inside the configured experiment budget.

## Phase 5 — strategic memory compaction

- [ ] Define a typed session handoff contract.
- [ ] Separate episodic, semantic, procedural, and preference memory.
- [ ] Add project, organization, and global scopes.
- [ ] Store decisions, verified facts, failed attempts, open questions, and next
      actions instead of injecting raw transcripts by default.
- [ ] Add retrieval budgets and per-class limits.
- [ ] Add deduplication, expiry, and contradiction markers.
- [ ] Keep private observations out of exportable packs.

**Acceptance**

- [ ] Relevant context uses fewer tokens than transcript retrieval.
- [ ] Cross-project contamination tests pass.

## Phase 6 — instincts and continuous learning

- [ ] Define an atomic instinct schema with trigger, action, scope, confidence,
      evidence, contradictions, and lifecycle state.
- [ ] Extract candidate instincts from `TaskEvent`, `EvidenceRecord`, tests,
      reviews, rollbacks, retries, and explicit user corrections.
- [ ] Require evidence before confidence increases.
- [ ] Apply penalties for rollback, contradiction, and user correction.
- [ ] Start with manual approval only.
- [ ] Add shadow selection before active prompt injection.
- [ ] Promote project instincts only after cross-project evidence and approval.
- [ ] Cluster stable instincts into versioned skill candidates.

**Acceptance**

- [ ] Learned behavior improves a held-out task suite.
- [ ] Removing an instinct restores baseline behavior.
- [ ] Policy and security rules cannot be overridden by learned content.

## Phase 7 — lifecycle hooks

- [ ] Define harness-neutral lifecycle events.
- [ ] Require permissions, timeout, idempotency, and fail-open/fail-closed policy.
- [ ] Run hooks through a constrained adapter.
- [ ] Add hooks for observation, scoped tests, secret scanning, documentation
      checks, and budget notifications.
- [ ] Keep imported hooks disabled until separately approved.

**Acceptance**

- [ ] A failing hook cannot corrupt the executor run state.
- [ ] Automatic hooks are visible in evidence and telemetry.

## Phase 8 — evaluated agent and skill packs

- [ ] Pilot `security-reviewer`, `tdd-workflow`, and one language reviewer.
- [ ] Define typed input/output contracts and success criteria.
- [ ] Track completion, test pass rate, rollback, corrections, cost, latency,
      retries, and reviewer acceptance per capability and executor.
- [ ] Route by `task → role → capability → executor → model`.
- [ ] Retire capabilities that do not produce measurable added value.

**Acceptance**

- [ ] Every active imported capability has measured evidence.
- [ ] Routing can fall back to the native VOLY workflow.

## Validation strategy

- [ ] Use paired baseline/variant tasks.
- [ ] Change one capability at a time.
- [ ] Keep a held-out task set.
- [ ] Measure quality, cost, latency, retries, rollback, and human corrections.
- [ ] Stop or remove any phase whose added complexity exceeds measured value.

## Initial risk test

The riskiest assumption is that ECC capabilities improve real VOLY outcomes
rather than only increasing context, latency, and orchestration complexity.
The cheapest falsification is a paired benchmark of 20 representative tasks
using baseline VOLY versus VOLY plus one capability at a time.

## Documentation requirements

- [ ] `docs/backend/capability.md` — pack discovery, admission, install, evidence.
- [ ] `docs/backend/intelligence.md` — external capability security analysis.
- [ ] `docs/backend/pipeline.md` — research, memory, and learning stages when
      they become active.
- [ ] `docs/ARCHITECTURE.md` — capability-pack trust boundary.
- [ ] CLI help and examples updated in the same phase as behavior.
