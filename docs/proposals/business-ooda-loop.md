# Proposal: Business signal loop (Sensing → Interpret → Decide → Act → Learn)

**Status:** implementation started — PR0 contracts landed in the working tree
**Layer:** new — **C** (business-signal orchestration; sits beside Layer A model gateway and Layer B code-agent orchestration, does not replace either)
**Author context:** adapting VOLY toward Salim Ismail's "Intelligence Stack" model (*The Organizational Singularity*): Sensing → Interpretation → Decision → Orchestration/Execution → Learning, wrapped in a Governance band. VOLY already implements a mature version of this loop, but scoped to one input type — a human-typed coding task — and one output type — a git diff. This proposal generalizes the loop to arbitrary business signals and business actions, reusing existing contracts instead of building a parallel stack.
**Related:** `voly/intelligence/` (repo_analyzer — code-scoped sensing, not reused directly but same shape), `voly/dspy/programs/*.py`, `voly/plan/` (FSM, gates, `review_required` pattern), `voly/executor/base.py` (`Executor`, `ExecutorResult`), `voly/capability/` (`ExecutorMatcher`, capability-aware fallback), `voly/learning/instincts.py`, `voly/evaluation/calibration.py`, `voly/evidence/` (`EvidenceRecord`, human feedback), `voly/telemetry.py` (`TaskEvent` v3), `voly/ai_gateway/` (`AIGateway.chat()`), `docs/proposals/plan-gate-verification.md` (this proposal reuses its FSM instead of adding a second one)

---

## Summary

VOLY is a control plane for AI agents. Today every run starts from a human-typed
task (CLI, `POST /api/run`, or CI) and ends in a code artifact (git diff) or a chat
response. It already has, in that narrow scope, a working version of four of
Ismail's five layers plus governance:

| Ismail layer | VOLY today | Scope today |
|---|---|---|
| Sensing | `voly/intelligence/` (`repo_analyzer.py`, `dependency_analyzer.py`, `security_scanner.py`) | one git repository, pre-run |
| Interpretation | `voly/dspy/programs/{architect,router,bugfixer}.py`, A2A role decomposition | one coding task → sub-tasks |
| Decision | `voly/plan/` FSM + `review_required` pattern (security/testing tasks already pend for a human) | file-diff acceptance only |
| Orchestration/Execution | `AgentRouter` + billing fallback chain (`claude-code → cursor → deepseek → wrangler → opencode → zen`) | file-capable CLI executors only |
| Learning | `voly/learning/instincts.py`, `voly/evaluation/calibration.py`, DSPy program compilation from stored examples | code-task outcomes only |
| Governance | `AIGateway` (DLP → Cache → Rate limit → Spend limit), `TaskEvent`/`EvidenceRecord` versioned + privacy-allowlisted telemetry, capability-pack admission/quarantine | already domain-agnostic |

**Gap:** nothing today originates a task from the outside world (a competitor
filing, a price change, an inbound lead, a regulatory update), and nothing
executes a business action (send an email, update a CRM record, call a
partner API) through the same governed, evidenced path a code task gets today.

This proposal adds that missing edge on both ends — **Sensing in**,
**business Executors out** — and reuses the existing Decision (`plan/`
FSM) and Learning (`instincts`/`calibration`) machinery unchanged in the
middle.

---

## Problem

```text
Today:      human types task  →  VOLY orchestrates  →  code diff / chat reply
Missing:    world event        →  ????                →  business action
```

What exists and should be kept as-is (do not fork):

1. **Decision gate** — `voly/plan/` already has a working FSM
   (`pending → running → done → verifying → verified`) and a
   human-pending-review pattern (security/testing tasks stay pending until
   `POST /api/evidence/{task_id}/feedback`). This *is* Ismail's "yes/no
   checkpoint" — it just has never been fed anything but code tasks.
2. **Governance** — `AIGateway.chat()` sole exit, spend limits, DLP,
   versioned/allowlisted telemetry, capability-pack quarantine for untrusted
   external code. All of it is already domain-agnostic and should apply to
   business signals and business actions unchanged.
3. **Learning** — `instincts.py` / `calibration.py` already turn human
   feedback + outcome evidence into future routing/planning improvements.
   The mechanism doesn't care whether the underlying task was "fix a bug"
   or "respond to a competitor's price cut."

What's missing:

1. A **Signal** source — something that produces a candidate task from an
   external observation instead of a human typing one in.
2. An **Option** step — something that turns a raw Signal into 1–N
   candidate actions with a rationale, before it reaches the existing
   Decision gate.
3. **Business Executors** — the `Executor`/`ExecutorResult` interface
   already used for `claude-code`/`cursor`/etc., implemented for
   non-code actions (call an API, send a message, file a document).

---

## Goals

1. Represent an external observation as a versioned, evidenced artifact
   (`Signal`), the same way a code task becomes a `TaskEvent`.
2. Turn Signals into candidate actions (`Option[]`) using the existing DSPy
   program pattern — no new LLM-calling path outside `AIGateway.chat()`.
3. Route an approved Option through the **existing** `voly/plan/` FSM and
   `review_required` human gate — do not build a second approval mechanism.
4. Execute approved business actions through the **existing** `Executor`
   interface and capability-aware fallback — do not build a second
   execution engine.
5. Feed outcomes into the **existing** `instincts.py` / `calibration.py`
   loop.
6. Ship gated behind config, `mode: shadow` first, zero behavior change to
   the current code-task path when disabled.

## Non-goals (v1)

- A generic business-rules engine or no-code workflow builder.
- Autonomous execution without a human "yes/no" — the Decision gate stays
  mandatory in `active` mode, exactly as it is today for security/testing
  review.
- Full CRM/ERP integrations — v1 ships one Sensing connector and one
  generic business Executor (see Phase 1/4) as proof of the contract, not
  a connector marketplace.
- Replacing `voly/intelligence/` (repo intelligence stays code-scoped) —
  Signal is a new, parallel concept, not a rename.
- Real-time/streaming ingestion — polling connectors only in v1, matching
  the existing `voly/intelligence/repo_analyzer_cache.py` cache-by-SHA
  pattern (poll, dedupe, cache).

---

## Design principles

Inherited unchanged from `docs/ARCHITECTURE.md`:

1. Project/product-agnostic core — no business-specific logic in `voly/`.
2. `AIGateway` stays the sole exit to chat models.
3. Shadow before active for every new gate.
4. Runtime state is not source (`.voly/signals/`, `.voly/decisions/` are
   generated artifacts, gitignored like `.voly/events/`).
5. Capability-aware routing over static chains, matching how
   `capability/fallback.py` already replaces the static
   `BILLING_FALLBACK_CHAIN`.

New for this proposal:

6. **No second FSM.** An Option becomes a `Plan` with one step; Decision
   reuses `voly/plan/types.py` states verbatim.
7. **No second evidence format.** A business action produces an
   `EvidenceRecord` the same shape as a code action, with `WorkReport`
   replaced by a business-analog `ActionReport` (see below).

---

## Target model

### Signal (new artifact)

```yaml
# .voly/signals/<date>/<signal_id>.json
schema_version: 1
signal_id: "rss-a1b2c3"
source: "rss"                    # connector name
source_ref: "https://example.com/feed.xml#entry-42"
captured_at: "2026-08-27T10:03:00Z"
dedup_key: "sha256:…"            # connector-defined, prevents re-ingest
payload:
  title: "Competitor X cuts enterprise pricing 15%"
  body: "…"
  raw: {…}                       # connector-specific, opaque to core
confidence: 0.8                  # connector's own signal quality estimate
```

### Option (interpretation output, DSPy `analyst` program)

```yaml
# .voly/signals/<date>/<signal_id>.options.json
schema_version: 1
signal_id: "rss-a1b2c3"
options:
  - option_id: "opt-1"
    title: "Match pricing for enterprise tier"
    rationale: "…"
    urgency: high               # low | medium | high
    estimated_impact: "…"       # free text in v1, structured later
    action_kind: "business"     # business | code | ignore
  - option_id: "opt-2"
    title: "No action — monitor for 2 weeks"
    urgency: low
    action_kind: "ignore"
```

Generated by `voly/dspy/programs/analyst.py` (new file, same shape as
`programs/router.py`), run through the existing `VOLYDSPyLM` adapter — so
DLP/cache/rate-limit/spend-limit apply for free, same as every other DSPy
program today.

### Decision (reuses `voly/plan/` — no second FSM)

An Option selected for review becomes a **two-step Plan**. The first step is
the mandatory human checkpoint; the second performs the approved action and
cannot start until the checkpoint is verified:

```yaml
plan_id: "opt-1"
steps:
  - id: approve-option
    mode: business             # new mode, alongside existing chat | executor
    status: pending
    acceptance:
      - type: human_review     # new acceptance type, alongside command/files_exist/…
  - id: execute-action
    mode: business
    status: pending
    depends_on: [approve-option]
    acceptance:
      - type: action_succeeded
```

Both steps use the exact `pending → running → done → verifying → verified`
FSM from `docs/proposals/plan-gate-verification.md`. `human_review` is an
asynchronous acceptance check that resolves only via explicit
`POST /api/decisions/{plan_id}/feedback` (approve/reject), mirroring the
existing evidence-feedback API shape. Approval verifies `approve-option` and
unblocks `execute-action`; it does **not** mark the action itself as completed.
A rejection fails `approve-option`, records the explicit decision, and leaves
`execute-action` blocked. Repeated identical decisions are idempotent;
conflicting decisions fail closed.

### ActionReport (business analog of `WorkReport`)

```yaml
# alongside EvidenceRecord, same lifecycle as WorkReport for code
action_kind: "http_call"          # http_call | notify | ...
target: "https://api.partner.example/v1/deals/123"
request_summary: "PATCH deals/123 status=won"   # redacted per evidence/privacy.py rules
result: "200 OK"
```

---

## Where it plugs into VOLY

| Existing piece | Role in this design | Change needed |
|---|---|---|
| `voly/dspy/adapter.py`, `AIGateway.chat()` | Runs the `analyst` program | none — reused as-is |
| `voly/plan/types.py`, `engine.py`, `store.py` | Decision FSM for Options | add `mode: business` and `human_review` check type |
| `voly/plan/verify.py` | Dispatch acceptance checks | add one dispatch case |
| `voly/executor/base.py` (`Executor`, `ExecutorResult`) | Interface for business actions | new implementations only, interface unchanged |
| `voly/capability/` (`ExecutorMatcher`, `fallback.py`) | Route/score business executors alongside code executors | register the string capability key `business_action` (the current `CapabilityDomain` is a score dataclass, not an enum) |
| `voly/evidence/` (`baseline.py`, `record.py`, `store.py`) | Evidence for business actions | `ActionReport` alongside `WorkReport`; same `EvidenceRecord` envelope |
| `voly/learning/instincts.py`, `voly/evaluation/calibration.py` | Learn from Decision/outcome pairs | ingest `plan_id` (business) same as it ingests judge-quality calibration events today |
| `voly/telemetry.py` (`TaskEvent` v3) | Auditability | schema bump (see Risks) to carry `signal_id` / `plan_id` (business) — nested blob first, same strategy the plan-gate proposal used |
| `voly/evidence/privacy.py` | Redaction before any remote analytics | Signal/Option/ActionReport payloads go through the same allowlist, fail-closed by default |
| Web UI | New `#/signals` and `#/decisions` routes | reuse `WorkReport.svelte` / evidence-feedback UI patterns |

**Integration strategy:**

- New package `voly/sensing/` (types, connectors, store) — keeps core free
  of business-specific logic, same rationale as `voly/plan/` being its own
  package.
- New package `voly/dspy/programs/analyst.py` — one file, existing
  programs directory.
- `voly/plan/` gets additive changes (`mode: business`, `human_review` and
  `action_succeeded` checks), not a rewrite or a second state machine.
- New business executors live in `voly/executor/`, registered in
  `voly/capability/registry.py` seeds like existing executor profiles.

---

## Config

```yaml
# voly.yaml
sensing:
  enabled: false                 # master switch — zero behavior change when off
  mode: shadow                   # off | shadow | active
  # shadow: connectors poll and store Signals + Options, nothing reaches Decision
  # active: Options above urgency threshold auto-create a pending Plan
  store_dir: .voly/signals
  connectors:
    - name: rss
      feeds: ["https://example.com/feed.xml"]
      poll_interval_seconds: 900
  min_urgency_for_decision: medium

business_executors:
  enabled: false
  allow: ["http_call", "notify"]  # explicit allowlist, fail closed
  http:
    allowed_hosts: []              # empty means no HTTP action may run
    allowed_methods: ["POST", "PATCH"]
```

Env overrides: `VOLY_SENSING_ENABLED`, `VOLY_SENSING_MODE`,
`VOLY_BUSINESS_EXECUTORS_ENABLED` — matching the existing `VOLY_PLAN_*`
convention.

---

## Phased delivery (PR plan)

### Phase 0 — Spec + contracts (PR0, docs + types only)

- This proposal as canonical design; link from `docs/ARCHITECTURE.md`.
  documentation map.
- Dataclasses: `Signal`, `Option`, `ActionReport` (`voly/sensing/schema.py`).
- No runtime behavior change.

**Done when:** types importable; CI green; doc linked.

---

### Phase 1 — Sensing connector skeleton (PR1)

| Deliverable | Detail |
|---|---|
| `voly/sensing/connectors/base.py` | `SensingConnector.poll() -> list[Signal]` |
| `voly/sensing/connectors/rss.py` | first real connector — no auth, easiest to test |
| `voly/sensing/store.py` | atomic JSON under `.voly/signals/`, dedup by `dedup_key` (same atomic-write pattern as `voly/plan/store.py`) |
| CLI | `voly sensing poll --connector rss`, `voly sensing list` |
| Tests | fixture feed → dedup on second poll → stored Signal shape |

**Done when:** polling a feed twice produces exactly one stored Signal;
`sensing.enabled=false` by default means this code never runs in existing
deployments.

---

### Phase 2 — Interpretation (PR2)

| Deliverable | Detail |
|---|---|
| `voly/dspy/programs/analyst.py` | Signal → `Option[]`, `ChainOfThought` like `TaskPlannerProgram` |
| Wiring | `voly/sensing/interpret.py` calls `DSPyRunner` in shadow mode |
| Storage | `.voly/signals/<date>/<id>.options.json` |
| Tests | golden Signal fixtures → expected Option shape (not exact text) |

**Done when:** `mode: shadow` produces stored Options for every polled
Signal, with zero effect on Decision/Execution (nothing auto-creates a
Plan yet).

---

### Phase 3 — Decision wiring (PR3)

| Deliverable | Detail |
|---|---|
| `voly/plan/types.py` | add `mode: business` alongside `chat`/`executor` |
| `voly/plan/verify.py` | add asynchronous `human_review` and post-action `action_succeeded` acceptance checks |
| API | `POST /api/decisions/{plan_id}/feedback` (approve/reject) — mirrors `routes/evidence.py` |
| CLI | `voly decide list`, `voly decide approve/reject <plan_id>` |
| Auto-create | in `mode: active`, an Option with `urgency >= min_urgency_for_decision` creates a pending business Plan |
| UI | `#/decisions` route, reuse `WorkReport.svelte`-style pending-review card |

**Done when:** an Option above threshold produces a Plan whose
`approve-option` step stays at `verifying` until explicit feedback moves that
step to `verified`/`failed`. Only approval unblocks the still-pending
`execute-action` step.

---

### Phase 4 — Orchestration: business Executors (PR4)

| Deliverable | Detail |
|---|---|
| `voly/executor/http_action.py` | generic HTTP action executor with host/method allowlists, SSRF protection, bounded redirects/body/timeouts, idempotency key, and redacted evidence |
| `voly/executor/notify.py` | one explicitly configured notification transport in v1; additional email/Slack transports are later integrations |
| `voly/capability/` | register the `business_action` capability key; seed profiles in `capability/seeds/` |
| Evidence | `ActionReport` alongside `WorkReport`; same `EvidenceRecord` envelope, redacted per `evidence/privacy.py` |
| Fallback | reuse `ExecutorMatcher` scoring instead of a new static chain |

**Done when:** a verified `approve-option` step unblocks `execute-action`,
which runs once through a real `Executor`, produces an `EvidenceRecord`, and
emits a `TaskEvent`. Retry must use an idempotency key and must not duplicate an
irreversible external action.

---

### Phase 5 — Learning (PR5)

| Deliverable | Detail |
|---|---|
| `voly/learning/instincts.py` | ingest Decision approve/reject + downstream outcome as a calibration event, same shape as existing judge-quality events |
| `voly/evaluation/calibration.py` | extend confusion-matrix aggregation to business Decisions |
| `voly/dspy/compiler.py` | optional: compile `analyst.py` from accumulated approved/rejected Option examples |

**Done when:** `voly eval calibrate` reports include business-Decision
rows alongside existing judge-calibration rows; reports stay observational
(never auto-tune thresholds), matching the existing calibration contract.

---

### Phase 6 — Governance polish (PR6, optional)

| Deliverable | Detail |
|---|---|
| `TaskEvent` schema | bump `schema_version` (nested `signal`/`business_plan` blob first, per plan-gate proposal's precedent) |
| `tests/test_protocol_contracts.py` | add contract snapshot entries |
| Docs | `docs/backend/sensing.md`, `docs/backend/decisions.md`; update `docs/ARCHITECTURE.md` map |

---

## Acceptance criteria (proposal-level)

1. **Zero blast radius by default:** `sensing.enabled=false` and
   `business_executors.enabled=false` leave every existing code-task path
   byte-identical.
2. **Shadow before active:** Phases 1–2 never create a Plan or call an
   Executor; only Phase 3's `active` mode does, and only above a
   configured urgency threshold.
3. **No parallel FSM:** business Decisions are `voly/plan/` Plans; no new
   state machine module.
4. **No parallel executor stack:** business actions implement the
   existing `Executor` interface; routed by the existing capability
   matcher.
5. **No parallel evidence format:** business actions produce
   `EvidenceRecord` + `TaskEvent`, same schema family as code tasks.
6. **Human checkpoint is mandatory in `active` mode** — `execute-action`
   cannot start until `approve-option` is explicitly approved and verified.
7. **Redaction unchanged:** Signal/Option/ActionReport payloads pass
   through `evidence/privacy.py`'s existing fail-closed allowlist before
   any remote analytics.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scope creep into a full business-automation platform | Cap v1 to one connector (RSS) + two executors (HTTP action, notify); everything else is a future PR, not this one |
| `TaskEvent` schema churn | Nested blob first, versioned, contract-tested — same strategy already used for the plan-gate work |
| Analyst program hallucinating high-urgency Options | `min_urgency_for_decision` threshold + mandatory human approval before any Executor runs; shadow mode first to observe false-positive rate before enabling `active` |
| Business Executors as a new untrusted-input surface | Explicit `business_executors.allow` allowlist, fail closed; route through capability admission the same way external capability packs are quarantined today |
| Generic HTTP action enables SSRF or duplicate irreversible writes | Host/method allowlists, private-address denial after DNS resolution, bounded redirects/timeouts/body, redacted evidence, and mandatory idempotency keys |
| Connector-sourced data leaking into remote analytics | Same allowlist/redaction path as existing evidence privacy contract; Signal `raw` payload never leaves `.voly/signals/` |

---

## Alternatives considered

| Option | Why not for v1 |
|---|---|
| New standalone "business agent" service outside VOLY | Duplicates governance (DLP/spend/telemetry) that already exists in `AIGateway`; loses the audit trail |
| Skip Decision gate, let `analyst` auto-execute high-confidence Options | Contradicts Ismail's own model (human stays "above the loop, not in it") and VOLY's existing fail-closed posture for review-required tasks |
| Build a generic no-code workflow engine for business logic | Same objection `plan-gate-verification.md` raised for Temporal/DBOS — overkill, and out of scope per `CLAUDE.md` |
| Model Signal/Option inside `voly/intelligence/` | That package is code-repository-scoped by design (license/architecture/dependency analysis); overloading it blurs a clean boundary for no reuse benefit |

---

## Success metrics (after Phase 4)

- **Signal → Decision conversion rate:** share of Signals whose top Option
  crosses the urgency threshold and reaches a human.
- **Approval rate:** approved vs rejected Decisions — a very low approval
  rate signals the `analyst` program needs recalibration before going
  `active` broadly.
- **Time to action:** Signal capture → Decision approved → Executor
  completion, the concrete "hours not weeks" claim from Ismail's model,
  measurable from existing `TaskEvent` timestamps.
- **Cost per Decision:** already free via `AIGateway` spend telemetry —
  no new instrumentation needed.

---

## Implementation checklist (engineering)

```text
[x] PR0  docs/proposals/business-ooda-loop.md + ARCHITECTURE pointer + importable contracts
[x] PR1  voly/sensing/{schema,store,connectors/{base,rss}}.py + config/CLI/tests
[x] PR2  voly/dspy/programs/analyst.py + voly/sensing/interpret.py + tests
[ ] PR3  two-step business Plan + human_review/action_succeeded checks + decisions API/CLI/UI
[ ] PR4  voly/executor/{http_action,notify}.py + capability BUSINESS_ACTION domain
[ ] PR5  instincts.py / calibration.py extended to business Decisions
[ ] PR6  TaskEvent schema bump + contract tests + docs
```

---

## One-line pitch (for chats / README)

> VOLY already senses code repositories, interprets tasks into role plans,
> gates risky work behind human review, executes through a governed
> multi-provider fallback chain, and learns from evidence — this proposal
> just opens the two ends (Sensing, business Executors) so the same loop
> can run on a world event instead of only a typed coding task.

---

## Changelog

- v0.1 — initial draft.
