# Proposal: Public Agent and Workflow SDK

**Status:** PR0 + PR1 + PR2 + PR3 + PR4 + PR5 + PR6 (7/10 examples) landed
(see `docs/backend/sdk.md` for what's actually implemented vs. this plan)  
**Complexity:** complex  
**Recommended agent:** Codex  
**Related:** `docs/ARCHITECTURE.md`, `docs/backend/pipeline.md`,
`docs/backend/ai-gateway.md`, `docs/backend/executors.md`,
`docs/backend/sdk.md`, `docs/proposals/plan-gate-verification.md`

## Goal

Give VOLY a small, composable Python API for agents and governed workflow
graphs, while keeping `AIGateway`, Plan FSM, Executor safety, Evidence and
human approval as the only underlying runtime contracts.

The intended first-run experience is:

```python
from voly import Agent, Workflow

researcher = Agent("researcher", instructions="Find verifiable facts")
reviewer = Agent("reviewer", instructions="Check claims and sources")

workflow = Workflow("research-review")
workflow.add("research", agent=researcher)
workflow.add("review", agent=reviewer, depends_on=["research"])

result = workflow.run("Compare two markets")
```

This API must remain a facade. It must not call a provider directly, create a
second state machine, or bypass existing cost, safety, evidence and approval
policies.

## Why this work

The comparison with the adjacent `swarms` project identified three material
product gaps:

1. VOLY lacks a simple in-process Python SDK for a first agent run.
2. Existing Plan DAG support is not exposed as a general workflow builder and
   `PlanRunner` currently executes only the first runnable node.
3. VOLY has few reusable workflow presets and runnable examples compared with
   its internal orchestration depth.

VOLY should close those usability gaps without copying a large collection of
independent swarm runtimes. Its differentiator remains governed execution:
cost limits, human gates, safe file actions, evidence and calibration.

## Design principles

1. **One runtime:** `Agent` delegates text calls to `AIGateway.chat()`;
   file-capable work delegates to `AgentRunner`; graphs compile to `Plan`.
2. **One state machine:** workflow status and dependency rules remain in
   `PlanEngine` and `PlanRunner`.
3. **Safe defaults:** text-only agent, no tools, no external action, no active
   learning, no parallel writers.
4. **Explicit capabilities:** tools, execution mode, output schema, approval
   and acceptance checks are declared per node.
5. **Resume by contract:** persisted state is versioned Plan state, not a
   serialized live Python object or provider client.
6. **Backward compatibility:** existing CLI, API, pipeline and stored Plans
   continue working throughout rollout.
7. **Measured expansion:** presets are added only with deterministic contract
   tests and at least one offline example.

## Scope

### In scope

- public `Agent`, `Workflow`, `WorkflowResult` and node-builder APIs;
- sequential, concurrent fan-out/fan-in, supervisor-workers and reviewer-loop
  presets;
- bounded parallel execution of independent chat nodes;
- sequential execution for nodes sharing a writable `cwd`;
- checkpoints and resume using `PlanStore`;
- human approval nodes using existing `human_review` acceptance;
- structured output validation;
- streaming lifecycle events through existing AG-UI/event contracts;
- CLI commands and a visual read-only workflow graph, followed by an optional
  editor after the backend contract stabilizes;
- runnable examples and benchmark fixtures.

### Non-goals

- replacing Pipeline, A2A, PlanRunner or AgentRunner;
- direct provider SDK calls from the new public API;
- arbitrary Python object serialization;
- parallel file writers in the same working tree;
- automatic activation of learned instincts or generated workflows;
- implementing dozens of topology classes with duplicate runtimes;
- a breaking rewrite of stored Plan or TaskEvent schemas in the first phase.

## Target architecture

```text
Python SDK / CLI / REST / UI
          │
          ▼
 Agent + Workflow facade
          │ compile()
          ▼
       Plan + PlanStep
          │
          ▼
 PlanEngine + PlanRunner
    ┌─────┼──────────────┐
    ▼     ▼              ▼
 AIGateway AgentRunner   human_review
 (chat)    (files)       (approval gate)
    └─────┬──────────────┘
          ▼
 Evidence / TaskEvent / spend / learning
```

## Proposed public contracts

### Agent

```python
Agent(
    name: str,
    instructions: str = "",
    model: str | None = None,
    provider: str | None = None,
    tier: str | None = None,
    tools: list[str] | None = None,
    output_schema: type | dict | None = None,
    mode: Literal["chat", "executor"] = "chat",
    executor: str | None = None,
)
```

`Agent.run()` returns a typed `AgentResult` containing content, success,
provider/model/executor attribution, tokens, cost, duration, files touched and
evidence/task identifiers. `Agent.arun()` provides the async equivalent.

### Workflow

```python
workflow.add(
    node_id,
    agent=agent,
    task="optional node instruction",
    depends_on=[...],
    approval=False,
    acceptance=[...],
    timeout_seconds=None,
)

workflow.compile(task, cwd=None) -> Plan
workflow.run(task, cwd=None, resume=False) -> WorkflowResult
workflow.arun(task, cwd=None, resume=False) -> WorkflowResult
```

Compilation must be deterministic. The same workflow definition and task must
produce the same node topology; runtime IDs and timestamps may differ.

### Result contract

`WorkflowResult` contains the final Plan, ordered node results, aggregate cost,
duration, status, partial/failure details and evidence IDs. It never reports
success when a required node is failed or blocked.

## Delivery plan

### Phase 0 — Contracts and compatibility baseline (PR0)

**Deliverables**

- add frozen SDK contract tests before exposing new imports;
- document mapping `Agent → PlanStep` and `Workflow → Plan`;
- decide schema-version policy for workflow metadata;
- capture current `Plan`, `TaskEvent`, CLI and API compatibility snapshots;
- add an architecture decision record stating that the SDK is a facade.

**Likely files**

- `docs/proposals/agent-workflow-sdk.md`
- `docs/backend/sdk.md` (new)
- `tests/test_sdk_contracts.py` (new)
- `tests/test_protocol_contracts.py`
- `docs/ARCHITECTURE.md`

**Done when:** imports and serialized contracts are specified by tests, while
existing behavior remains unchanged.

### Phase 1 — Minimal public Agent SDK (PR1)

**Deliverables**

- implement `voly/sdk/agent.py` and typed results;
- text mode delegates exclusively to `AIGateway.chat()`;
- executor mode delegates to existing `AgentRunner` and requires explicit
  `cwd` for file work;
- expose `Agent` and `AgentResult` from `voly`;
- support synchronous and asynchronous calls without duplicating provider
  logic;
- return cost, model/provider, files and task/evidence identifiers.

**Tests**

- gateway invocation and no-direct-provider invariant;
- executor delegation and missing-`cwd` failure;
- structured result attribution;
- async parity and exception normalization;
- import smoke test: `from voly import Agent`.

**Docs:** create `docs/backend/sdk.md`; update README quickstart and
`docs/ARCHITECTURE.md` entry points.

**Done when:** a text agent can run in under ten lines of Python and its call
still passes through gateway policy, spend accounting and telemetry.

### Phase 2 — Workflow builder compiled to Plan (PR2)

**Deliverables**

- implement `voly/sdk/workflow.py` as a builder, not an executor;
- compile nodes to `PlanStep` with dependency, mode, role and acceptance data;
- validate duplicate IDs, missing dependencies and cycles via `PlanEngine`;
- implement sequential, fan-out/fan-in and approval-node helpers;
- use `PlanRunner` for execution and `PlanStore` for persistence;
- expose `Workflow`, `WorkflowNode` and `WorkflowResult`.

**Tests**

- deterministic compilation;
- cycle and missing-dependency rejection;
- output handoff to dependent nodes;
- approval blocks downstream execution;
- mixed chat/executor graph honors `cwd` and safety policy;
- round-trip through `PlanStore`.

**Docs:** extend `docs/backend/sdk.md`; update `docs/backend/pipeline.md` and
`docs/backend/plan-gate.md` (or the current matching Plan documentation).

**Done when:** an SDK-built graph is persisted and executed as an ordinary
Plan, visible to existing Plan CLI/API paths.

### Phase 3 — Parallel chat waves and durable resume (PR3)

**Deliverables**

- add bounded wave scheduling to `PlanRunner` using all runnable nodes;
- allow parallelism only for independent chat/read-only nodes;
- serialize executor nodes sharing a `cwd` under the existing cwd lock;
- persist after every transition and node result;
- add `resume(plan_id)` and stale-running recovery policy;
- preserve deterministic result ordering regardless of completion order;
- enforce workflow-level timeout and cancellation state.

**Config**

```yaml
workflow_sdk:
  enabled: true
  max_parallel_nodes: 3
  checkpoint: true
  stale_running_seconds: 900
```

**Tests**

- real concurrency timing with fake chat functions;
- no concurrent writers for the same `cwd`;
- restart after partial completion does not rerun verified nodes;
- cancellation/timeout persists an honest terminal or resumable state;
- aggregate cost includes every completed node exactly once.

**Docs:** update Plan, configuration, telemetry and recovery documentation.

**Done when:** a fan-out/fan-in workflow survives process interruption and
resumes without repeating completed or externally effective actions.

### Phase 4 — Reusable topology presets (PR4)

Implement presets as graph factories over `Workflow`, never subclasses with
their own run loops:

| Preset | Shape | Required behavior |
|---|---|---|
| `sequential()` | A → B → C | ordered output handoff |
| `concurrent()` | A, B, C | bounded parallel chat nodes |
| `supervisor_workers()` | S → workers → S2 | supervisor synthesis |
| `reviewer_loop()` | generate ↔ review | bounded iterations and exit criteria |
| `council()` | members → judge | explicit aggregation policy |
| `planner_generator_evaluator()` | P → G → E | structured contracts between roles |

Every preset must define maximum nodes/iterations, result semantics and cost
behavior. Voting or judging output is evidence, not an authorization to bypass
human approval.

**Tests:** graph snapshot, bounds, failure propagation and cost aggregation for
each preset.

**Docs:** add a preset selection guide and one runnable offline example per
preset.

**Done when:** all presets compile to normal Plans and contain no provider or
execution code of their own.

### Phase 5 — API, CLI, streaming and UI visibility (PR5)

**Deliverables**

- CLI: `voly workflow validate|run|resume|show` for SDK/YAML definitions;
- REST endpoints to validate, create, run and resume governed workflows;
- AG-UI events for node queued/running/verifying/completed/failed;
- UI graph viewer with status, duration, cost, executor/model and evidence;
- approval controls reuse the existing Decision/Plan feedback contracts;
- defer drag-and-drop editing until the read-only graph contract is stable.

**Frontend files likely affected**

- `ui/src/lib/components/workflows/`
- `ui/src/lib/api/client.js`
- `ui/src/App.svelte`
- `ui/src/lib/i18n/en/` and `ui/src/lib/i18n/ru/`

**Tests:** API authorization/validation, SSE event ordering, UI component tests,
i18n parity and build.

**Docs:** update `docs/backend/api.md`, `docs/frontend/api-client.md`,
`docs/frontend/components.md` and `docs/frontend/overview.md`.

**Done when:** a user can observe and resume the same persisted workflow from
Python, CLI or UI without divergent state.

### Phase 6 — Examples, templates and product proof (PR6)

Add a curated `examples/workflows/` catalog:

1. sequential research and review;
2. parallel market analysis with synthesis;
3. repository change with tester and reviewer;
4. human-approved HTTP business action;
5. incident triage with read-only parallel investigators;
6. planner-generator-evaluator;
7. resumable long-running workflow;
8. structured-output workflow;
9. MCP tool workflow with an explicit allowlist;
10. capability-routed development workflow.

Each example must include expected output, required credentials, cost/safety
notes and an offline contract test using fakes. Add a comparison benchmark for
first-run lines of code, graph construction, resume, evidence completeness and
failure honesty; do not claim model-quality superiority from synthetic tests.

**Done when:** a new user can select, run and modify a representative workflow
without reading internal pipeline code.

## Dependency order

```text
PR0 contracts
    ↓
PR1 Agent SDK
    ↓
PR2 Workflow → Plan
    ↓
PR3 parallel/resume
    ↓
PR4 presets ──────┐
    ↓             │
PR5 CLI/API/UI    │
    ↓             │
PR6 examples ◀────┘
```

PR1 and the PR0 documentation can be reviewed separately, but PR2–PR6 should
land in order. UI editing is intentionally excluded until after PR5.

## Testing strategy

### Per-PR required checks

```bash
python -m pytest tests/test_sdk_contracts.py tests/test_plan_engine.py \
  tests/test_plan_verify.py tests/test_protocol_contracts.py -q
python -m pytest tests/test_ai_gateway.py tests/test_executor_safety.py \
  tests/test_evidence_foundation.py tests/test_cli_contracts.py -q
ruff check voly tests
```

For PR3 and later, add focused concurrency/recovery tests with injected fake
chat and executor functions. Multi-agent E2E runs must use the external
PulseBoard test repository required by `AGENTS.md`, never this repository.

### Contract invariants

- no SDK source imports provider-specific clients;
- every text call can be attributed to an `AIGateway` result;
- every file mutation is attributed to an Executor result;
- a required failed/blocked node prevents workflow success;
- approved external actions retain idempotency protection on resume;
- verified nodes are not executed twice;
- parallel nodes cannot mutate the same `cwd` concurrently;
- source Plans and thresholds are never auto-modified by learning.

## Documentation requirements

| Behavior change | Required documentation |
|---|---|
| Public Python API | `docs/backend/sdk.md`, README |
| Plan compilation/execution | Plan docs, `docs/ARCHITECTURE.md` |
| Parallel/resume configuration | `docs/backend/config.md`, Plan docs |
| REST/SSE | `docs/backend/api.md`, `docs/frontend/api-client.md` |
| UI workflow view | `docs/frontend/overview.md`, `components.md` |
| Presets/examples | `docs/backend/sdk.md`, `examples/workflows/README.md` |

Generated OpenWiki pages are not edited manually.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A second orchestration stack emerges | SDK compiles to Plan and delegates execution only |
| Public API freezes internal details | expose small typed results; keep Plan available separately |
| Parallel writes corrupt a repository | classify node effects; serialize shared-cwd writers |
| Resume duplicates external action | persist transition before/after action and require idempotency |
| Hidden cost explosion in presets | hard node/iteration caps and aggregate spend policy |
| Agent monolith similar to Swarms | composition around gateway/runner adapters; no tool/runtime logic in facade |
| UI and SDK disagree | both read the same stored Plan and event stream |
| Marketing outruns evidence | publish contract benchmarks and explicit limitations |

## Success metrics

- first text agent requires no more than 10 lines of user code;
- sequential two-agent workflow requires no more than 15 lines;
- 100% of SDK text calls are visible in gateway telemetry;
- 100% of file mutations have executor/evidence attribution;
- resume tests demonstrate zero duplicate verified-node executions;
- shared-cwd writer concurrency remains zero;
- every shipped preset has an offline contract test and runnable example;
- existing Plan/Pipeline/CLI contract suites remain green.

## Implementation checklist

```text
[x] PR0  freeze SDK/Plan compatibility contracts and architecture decision
[x] PR1  minimal public Agent + AgentResult facade
[x] PR2  Workflow builder compiles to Plan and runs through PlanRunner
[x] PR3  bounded chat waves, checkpoints, recovery and resume
[x] PR4  six graph-factory presets with bounds and tests
[x] PR5  CLI/API/AG-UI lifecycle and read-only workflow graph UI
[x] PR6  seven of ten runnable examples (3 blocked on unimplemented Agent
         capabilities), offline fixtures and product-proof benchmark
```

## Changelog

- v0.1 — initial draft.
- v0.2 — PR0 + PR1 landed: `voly/sdk/agent.py` (`Agent`, `AgentResult`,
  `AgentError`), exported as `voly.Agent`; frozen contract tests
  (`tests/test_sdk_contracts.py`); `docs/backend/sdk.md`. Fixed a real bug
  found while wiring chat mode: `PlanRunner._exec_chat`'s no-`chat_fn`
  fallback called `AIGateway(self.config)`, which silently produced an
  ungoverned gateway (config's DLP/spend/cache/fallback all ignored) because
  `AIGateway.__init__` does not accept a `VOLYConfig` positionally. Extracted
  the governed wiring `Pipeline.gateway` already used into
  `voly.ai_gateway.gateway_from_config()` and pointed both `PlanRunner` and
  `Agent` at it — this was load-bearing for the proposal's own "every text
  call passes through gateway policy" claim, since Phase 2's `Workflow`-built
  chat nodes will run through this exact `PlanRunner` path. Documented (in
  `docs/backend/sdk.md`) that Phase 2's "human approval nodes using existing
  `human_review` acceptance" deliverable needs a design decision first:
  `human_review` today is fail-closed-only outside `DecisionService`, which
  only operates on `business_decision`-kind Plans — a generic `Workflow`
  approval node cannot reuse it as-is.
- v0.3 — resolved the v0.2 gap ahead of Phase 2: `voly/plan/approval.py`
  (`decide()`) generalizes `DecisionService.decide()`'s idempotent /
  fail-closed-on-conflict contract to any Plan/step pair, without touching
  `DecisionService` or any shipped business-Decision behavior.
  `PlanRunner._verify()` now parks a `human_review`/`action_succeeded` step
  in `verifying` instead of failing it, and — importantly — `mode: shadow`'s
  soft-open no longer applies to either type (a human/action gate is not a
  quality signal to bypass). `PlanRunner.run()`'s "nothing runnable" branch
  distinguishes a paused in-flight step from a real dependency deadlock, and
  `PlanRunner.resume(plan_id)` continues a paused Plan once
  `approval.decide()` resolves it. See `docs/backend/sdk.md` and
  `docs/backend/plan.md` for the full design, and
  `tests/test_plan_approval.py` for the pause/approve/reject/resume contract
  tests, including a shadow-mode test proving approval is never bypassed.
- v0.4 — PR2 landed: `voly/sdk/workflow.py` (`Workflow`, `WorkflowNode`,
  `WorkflowResult`, `NodeResult`), exported as `voly.Workflow`. Compiles to a
  `Plan` tagged `metadata["kind"] = "sdk_workflow"`, validates via
  `PlanEngine` (re-raised as `WorkflowError`), and runs through the
  unmodified `PlanRunner`/`PlanStore`. `approval=True` nodes use the v0.3
  approval-gate primitive directly — the pause/approve/resume path proposed
  there is now exercised end-to-end from `Workflow.run()`. Two supporting
  `PlanRunner` gaps had to be closed for the contract to hold: (1) per-step
  `cost_usd`/`duration_ms` didn't exist anywhere in `Plan`/`PlanStep` at all,
  so `WorkflowResult.cost_usd` would have been silently always `0.0` — added
  both fields to `PlanStep`, populated by `_exec_chat`/`_exec_executor`'s
  default (non-injected) implementations only, so existing `chat_fn`/
  `executor_fn` test doubles are unaffected; (2) a dependent node's
  instruction never referenced its dependency's output — `PlanRunner` now
  prepends each `depends_on` step's stored output as context before running
  a step, benefiting every Plan, not only SDK-built ones. Also fixed a Phase
  1 completeness gap found while wiring node compilation:
  `Agent._run_executor` never used `self.instructions` (only `_run_chat`
  did) — an `Agent(instructions=..., mode="executor")` silently dropped it.
  `Workflow.run(resume=True)` intentionally raises `NotImplementedError`:
  there is no way to identify which prior Plan to resume from `task` text
  alone (plan_id is a fresh "runtime id" every `compile()` call, matching
  the proposal's own compilation-determinism note, which promises identical
  *topology*, not identical *plan_id*) — resuming a paused node works today
  via `voly.plan.approval.decide()` + `PlanRunner.resume(plan_id)` directly,
  documented in `docs/backend/sdk.md`, and Phase 3 owns defining the real
  addressing scheme. `WorkflowNode.timeout_seconds` is accepted (frozen
  constructor contract) but not enforced — no `PlanStep` field, no
  `PlanRunner` timeout logic exists yet; that's explicitly Phase 3's
  "enforce workflow-level timeout," and wiring a partial version now would
  have meant `Workflow` (a "builder, not an executor" per this proposal)
  reaching into `PlanRunner`'s execution/scheduling internals prematurely.
- v0.5 — PR3 landed: `PlanRunner` schedules independent `mode: chat` nodes
  in bounded concurrent waves (new `workflow_sdk.*` config —
  `max_parallel_nodes`, `stale_running_seconds`; `checkpoint` reserved,
  since persistence-after-every-step was already unconditional).
  `mode: executor` nodes still always serialize (shared Plan `cwd`); only
  the network-call phase runs in a worker thread (mirroring the split-phase
  pattern `voly.a2a.multiagent_run` already uses), every `Plan`/`PlanStep`
  mutation happens back on the calling thread, so no lock is needed and
  `node_results` stay in declared order regardless of completion order.
  `PlanStep` gained a `started_at` field (set by `PlanEngine.transition()`
  on entry to `running`) so `PlanRunner._recover_stale_running_steps()` can
  detect and recover a step whose process crashed mid-execution before
  `run()`/`resume()` continues. `PlanRunner.cancel(plan_id)` marks a Plan
  aborted; the run loop re-checks persisted status before every post-step
  save so an external cancel landing mid-step is adopted instead of
  silently clobbered by the runner's own next save (a real race caught
  while writing the concurrency tests, not merely theoretical — see
  `tests/test_plan_concurrency.py::test_cancel_stops_a_run_in_flight_from_another_thread`).
  `run(timeout_seconds=...)` bounds the whole call and leaves a resumable
  (not failed) Plan on expiry. `Workflow.resume(plan_id)`/`Workflow.cancel(plan_id)`
  wrap the above; `Workflow.run(resume=True)` still raises
  `NotImplementedError` for the reason recorded in v0.4 — an explicit
  `plan_id` remains the only way to identify which prior Plan to continue.
  `WorkflowNode.timeout_seconds` (per-node) is still unenforced — distinct
  from `run()`'s new workflow-level timeout, and still not owned by any
  landed phase.
- v0.6 — PR4 landed: `voly/sdk/presets.py` — `sequential`, `concurrent`,
  `supervisor_workers`, `reviewer_loop`, `council`,
  `planner_generator_evaluator`, all exported from `voly.sdk` and `voly`
  directly. Each is a plain function returning an uncompiled `Workflow` (no
  `Workflow`/`PlanRunner` subclass, no provider import — covered by the
  existing `voly/sdk/**` import scan in `tests/test_sdk_contracts.py`), so
  every existing `Workflow` guarantee (compile-time cycle/dependency
  validation, dependency-output handoff, bounded parallel chat waves,
  resume/cancel, cost aggregation) applies to a preset's graph unchanged.
  Every preset enforces a hard node/iteration bound at build time
  (`WorkflowError`, not truncation): `MAX_SEQUENTIAL_NODES`/
  `MAX_CONCURRENT_NODES=20`, `MAX_WORKERS`/`MAX_COUNCIL_MEMBERS=10`,
  `MAX_REVIEWER_ITERATIONS=10`. `council`'s and `supervisor_workers`'
  judge/synthesis node is a real, costed chat call the caller can read from
  `WorkflowResult`, never an implicit authorization to skip human approval —
  neither preset adds a `human_review` gate itself. Found and resolved
  during design, not after: `reviewer_loop` cannot be a true early-exit loop
  over a Plan, because `PlanEngine` has no conditional-skip primitive (a
  Plan is a static DAG, not a branching state machine) — gating every
  round's `review_i` on `exit_acceptance` would mean a round that *fails*
  the criteria blocks the *next* generate attempt, which is backwards from
  "keep retrying until it passes." Implemented instead as a fixed,
  always-fully-executed chain of `max_iterations` rounds where
  `exit_acceptance` gates only the final round's review node — documented in
  `docs/backend/sdk.md` as a partial "exit," with the real early-exit case
  named as future work needing `PlanEngine` changes, not an SDK-layer
  workaround pretending otherwise. See `tests/test_sdk_presets.py` for graph
  snapshots, bound enforcement, handoff-reaches-the-aggregation-node checks
  and both `reviewer_loop` exit-gate outcomes.
- v0.7 — PR5 landed: `voly/sdk/loader.py` (`load_workflow_file`/
  `load_workflow_dict`) parses a YAML/JSON **Workflow document**
  (`Agent`-shaped nodes) into an ordinary `Workflow` via `Workflow.add()` —
  distinct from `voly.plan.loader.load_plan_file`, which loads an
  already-compiled `Plan`/`PlanStep` document for `voly plan run`. CLI:
  `voly workflow validate|run|resume|show` in
  `voly/cli/commands/workflow_cmd.py`, added alongside (not replacing) that
  module's pre-existing `stats`/`review-until-clean` subcommands for the
  unrelated bounded-review-workflow concept — no name collision since the
  new subcommand names don't overlap. REST/SSE:
  `voly/web/routes/workflows.py` — `validate`/`run`/`{plan_id}/resume`
  (SSE)/list/get/`{plan_id}/nodes/{node_id}/decide`, all delegating to the
  same `voly.sdk.loader` + `PlanRunner` + `voly.plan.approval` machinery the
  CLI and Python SDK use, so all three surfaces observe the same persisted
  Plan (the proposal's "UI and SDK disagree" mitigation). Node-lifecycle SSE
  events (`queued`/`running`/`verifying`/`completed`/`failed`) are produced
  by polling the persisted Plan every ~1s — mirroring `/api/run`'s existing
  heartbeat-polling pattern in `voly/web/routes/run.py`, at Phase 3's
  per-step persistence granularity — not a push channel threaded through
  `PlanRunner`'s internals, so no second event system was introduced. UI:
  `ui/src/lib/components/workflows/WorkflowsPage.svelte` at `#/workflows` —
  a read-only list + per-node detail view with Approve/Reject on a paused
  `human_review` node, reusing the same approval contract
  `DecisionsPage.svelte` already uses for business Decisions. Scoped down
  from the full Phase 5 wish list on purpose: the UI only *observes*
  persisted workflows today (list/detail poll) and has no run/resume trigger
  of its own, and the node view is a top-to-bottom status list, not a
  force-directed graph canvas — both explicitly deferred by the proposal
  ("defer drag-and-drop editing until the read-only graph contract is
  stable"; this ships that contract first). Found and fixed while writing
  the approval-decide tests: `voly.plan.approval.decide()` raises
  `PlanValidationError` (not `ApprovalError`/`FileNotFoundError`) for an
  unknown `step_id` on an otherwise-valid plan — the REST handler now catches
  it too and returns HTTP 404 instead of leaking a 500. Tests:
  `tests/test_sdk_loader.py`, `tests/test_workflow_cli.py`,
  `tests/test_workflows_api.py`; `ui/` verified via `npm run build` (no new
  errors; one new a11y warning class already present on several pre-existing
  components in this codebase, e.g. `Drawer.svelte`).
- v0.8 — PR6 landed (7 of 10 scoped examples): `examples/workflows/` — seven
  standalone, `--offline`-runnable scripts (`01`–`07`, one per landed
  capability: `sequential`/`supervisor_workers`/`planner_generator_evaluator`
  presets, a manually-built mixed chat/executor graph, an `approval=True`
  pause/decide/resume round trip, a manually-built read-only parallel-fan-in
  graph, and a workflow-level-timeout/resume round trip), each with a
  docstring stating expected `--offline` output, required credentials and
  cost/safety notes (enforced by
  `tests/test_examples_workflows.py::test_every_example_has_a_module_docstring_with_required_sections`).
  Examples 8–10 (structured-output, MCP-tool-allowlist, capability-routed)
  are *not* implemented — `Agent(output_schema=...)`/`Agent(tools=...)` still
  raise `NotImplementedError`, and capability-registry routing isn't wired
  into `Agent`/`Workflow` at all; faking any of them would misrepresent
  current capability, so the catalog's README documents the gap instead
  (`examples/workflows/README.md`, "Not implemented"). `BENCHMARK.md`
  measures (not estimates) first-run LOC against a hand-written
  `Plan` YAML equivalent (`examples/workflows/_plan_equivalent_01.yaml`,
  verified to load and pass `PlanEngine().validate()`), and confirms resume/
  failure-honesty are `PlanEngine`/`PlanRunner` properties every Plan gets
  regardless of construction method, not something the SDK adds. Found while
  writing it, not fixed here (scope: an examples/benchmark PR, not a
  contract-breaking change): `PlanRunner._exec_executor()` calls
  `AgentRunner.run()` for a `Workflow` executor-mode node exactly like
  `Agent._run_executor()` does, but never captures the returned
  `RunnerResult.task_id`, and `NodeResult` has no `evidence_id` field at
  all — so that node's `EvidenceStore` record exists but is unrecoverable
  from `WorkflowResult`/`NodeResult`, unlike a direct
  `Agent.run(mode="executor")` call. Documented in `docs/backend/sdk.md` and
  `BENCHMARK.md`'s "Evidence completeness" section as a real gap for a
  future phase — `NodeResult`'s field set is a frozen contract
  (`tests/test_sdk_contracts.py::test_node_result_field_contract_is_frozen`),
  so changing it needs its own deliberate PR.

## Recommended execution model

This is a complex cross-cutting task. Use Codex for PR0–PR5. Documentation-only
example polishing inside PR6 may use zen, but every code-bearing PR must be
owned by one agent that updates its matching documentation and produces a
`voly-report` completion report.
