# Public Agent and Workflow SDK

Proposal: `docs/proposals/agent-workflow-sdk.md`. This doc tracks what is
actually implemented; the proposal tracks the full multi-phase plan.

**Status: Phase 0 through Phase 6 landed** (Phase 6 partially — 7 of 10
scoped examples; see below). `Workflow` compiles to a normal `Plan` and runs
through `PlanRunner`, which now schedules independent `mode: chat` nodes in
bounded parallel waves and supports durable resume, cross-process
cancellation and a workflow-level timeout. `voly.sdk.presets` adds six
graph-factory topology presets over `Workflow`. Phase 5 adds
`voly workflow validate|run|resume|show`, the `/api/workflows/*` REST/SSE
surface, and a read-only `#/workflows` UI graph viewer. Phase 6 adds
`examples/workflows/` (7 runnable examples + a measured comparison
benchmark).

## Architecture decision: the SDK is a facade

`voly.sdk` introduces **no new runtime**. It is a thin, typed wrapper over
contracts that already exist and are already governed:

- chat calls go through `AIGateway.chat()` (via
  `voly.ai_gateway.gateway_from_config`, the same governed wiring
  `Pipeline.gateway` builds — DLP, spend limits, cache, rate limits, the
  configured fallback chain and BYOK all apply unchanged);
- file-capable calls go through `voly.runner.agent_runner.AgentRunner.run()`
  (billing fallback chain, evidence collection, `WorkReport` all apply
  unchanged);
- `Workflow.compile()` produces an ordinary `voly.plan.types.Plan` and
  execution stays inside `PlanEngine`/`PlanRunner` — no second state machine,
  no per-node scheduler of its own.

No module under `voly/sdk/` constructs a provider client (`anthropic`,
`openai`, raw `httpx`/`requests`, …) or calls one directly —
`tests/test_sdk_contracts.py::test_sdk_source_never_imports_a_provider_client_directly`
freezes that invariant by scanning the package's imports.

## `Agent`/`WorkflowNode` → `PlanStep` mapping

`Workflow._compile_node()` is the single place this mapping is implemented
(`voly/sdk/workflow.py`):

| `Agent`/node field | `PlanStep` field | Notes |
|---|---|---|
| `agent.name` | `role` | |
| `agent.instructions` + node `task` | `task` | folded at compile time: `f"{instructions}\n\n{task}"` — `PlanStep` has no separate instructions field, and a live `Agent` object is never read again at run time (see "resume by contract") |
| `agent.model` / `agent.provider` | `model` / `provider` | used as-is when `agent.tier` is unset |
| `agent.tier` | `model` / `provider` (resolved) + `tier` (informational) | resolved to a concrete pair via `voly.a2a.assignment.resolve_tier_model()` at compile time — `PlanRunner` never reads `step.tier` for routing, only `step.model`/`step.provider` |
| `agent.mode` | `mode` | `MODE_CHAT` / `MODE_EXECUTOR` |
| `agent.executor` | `executor` | |
| node `depends_on` | `depends_on` | validated by `PlanEngine.validate()` (dup ids, unknown deps, cycles) — `Workflow` does not reimplement graph validation, it re-raises `PlanValidationError` as `WorkflowError` |
| node `acceptance` | `acceptance` | extra `AcceptanceCheck`s beyond the approval gate below |
| node `approval=True` | appends `AcceptanceCheck(type=CHECK_HUMAN_REVIEW)` to `acceptance` | see "Approval nodes" below |
| node `timeout_seconds` | *(still not wired)* | accepted on `Workflow.add()` but currently a no-op — this is a *per-node* timeout, distinct from Phase 3's *workflow-level* `run(timeout_seconds=...)` (below), which bounds the whole call, not one node. No phase currently owns per-node enforcement; `PlanStep` has no per-step timeout field |
| `agent.tools`, `agent.output_schema` | *(not representable)* | `Agent.__init__` already raises `NotImplementedError` if either is set, so a node's agent can never reach compilation with them |

## Schema-version policy

`TaskEvent` stays at `schema_version=4` — neither `Agent.run()` chat calls nor
`Workflow`-compiled Plans add fields to it (see
`tests/test_protocol_contracts.py`). A chat call made through `Agent.run()`
emits a plain `TaskEvent` with `workflow="sdk-agent"`, visible in
`voly runs list`/telemetry like any other chat call.

A `Workflow`-compiled `Plan` is an ordinary `voly.plan.types.Plan` (current
`SCHEMA_VERSION`) — not a new persisted format — with
`plan.metadata["kind"] = "sdk_workflow"` and
`plan.metadata["workflow_name"] = self.name`, mirroring the
`"business_decision"` convention `voly.decisions.DecisionService` already
uses. This is why `DecisionService.decide()` correctly refuses these
Plans (`kind` mismatch) — approval on a `Workflow` node resolves through the
generic `voly.plan.approval.decide()` instead (below), which does not filter
by `kind` at all.

## Resolved: `human_review` is now a generic approval primitive

The proposal's Phase 2 deliverables say "human approval nodes using existing
`human_review` acceptance." That acceptance type existed
(`voly/plan/verify_types.py::CHECK_HUMAN_REVIEW`) but was, until now, **not**
a generic "pause this Plan for approval" mechanism — it was hardwired to
`voly.decisions.DecisionService`, which only operates on Plans whose
`metadata["kind"] == "business_decision"`. Option 2 from the original design
choice (a generic pending-approval mechanism decoupled from
`DecisionService`) was implemented, without touching `DecisionService` or any
already-shipped business-Decision behavior:

- **`voly/plan/approval.py`** — `decide(store, plan_id, step_id, decision, *,
  comment="")`. Same idempotent-approve / fail-closed-on-conflict contract as
  `DecisionService.decide()`, generalized to *any* Plan/step pair whose
  acceptance declares `human_review` — state is read directly off the step's
  `verified`/`failed` status rather than a parallel `metadata["decision"]`
  field, since a `human_review` step can only ever reach those statuses
  through this function (see next point).
- **`PlanRunner._verify()`** now special-cases `human_review` and
  `action_succeeded`: instead of routing them through
  `complete_verification()` (which would transition the step to `failed`),
  it populates `verify_log` for visibility and leaves the step parked in
  `verifying`. Critically, this bypasses `mode: shadow`'s normal soft-open
  (force any failed check to `verified`) for these two types specifically —
  a human/action gate is not a quality signal shadow mode should be allowed
  to wave through.
- **`PlanRunner.run()`**'s "nothing runnable" branch now distinguishes a step
  legitimately parked in `running`/`done`/`verifying` (paused, plan status
  stays `running`) from a genuine dependency deadlock (`pending` steps with
  no in-flight work anywhere — real failure, `plan.status = failed`).
- **`PlanRunner.resume(plan_id)`** reloads the Plan from `PlanStore` and calls
  `run()` again — no special resume state exists to restore; `run()` always
  recomputes runnable steps from whatever is currently persisted, so once
  `approval.decide()` moves the parked step to `verified`, its dependents
  become runnable on the next `run()`/`resume()` call.

A step already pre-seeded at `verifying` (the convention `DecisionService`
itself uses for `approve-option` — an approval gate has no task to execute)
is never picked up by `runnable_steps()` in the first place, so it reaches
the "nothing runnable" branch immediately rather than through `_verify()`;
both paths are covered in `tests/test_plan_approval.py`.

`DecisionService` was deliberately left as its own, unmodified,
business-specific layer. `Workflow.add(node_id, agent=..., approval=True)`
compiles that node's `PlanStep.acceptance` to include `human_review`, and the
node is resolved through `voly.plan.approval.decide()` directly — see
"Approval nodes" below.

## Public contracts (Phase 1)

```python
from voly import Agent, AgentResult

researcher = Agent("researcher", instructions="Find verifiable facts")
result: AgentResult = researcher.run("Compare two markets")
```

```python
Agent(
    name: str,
    instructions: str = "",
    model: str | None = None,
    provider: str | None = None,
    tier: str | None = None,
    tools: list[str] | None = None,       # raises NotImplementedError if non-empty (Phase 1)
    output_schema: type | dict | None = None,  # raises NotImplementedError if set (Phase 1)
    mode: Literal["chat", "executor"] = "chat",
    executor: str | None = None,
    *,
    config: VOLYConfig | None = None,     # injectable for tests/alternate config; not in the frozen positional contract
)
```

`Agent.run(task, *, cwd=None, timeout=300, max_turns=30) -> AgentResult`.
`executor` mode raises `AgentError` if `cwd` is omitted — file-capable work
always requires an explicit working tree, matching `AgentRunner.run()`'s own
required `cwd`. `Agent.arun()` is the async equivalent; since neither
`AIGateway.chat()` nor `AgentRunner.run()` is natively async, it offloads the
synchronous call via `asyncio.to_thread` rather than duplicating gateway or
executor logic behind a second async-native implementation.

`AgentResult` fields: `content`, `success`, `error`, `provider`, `model`,
`executor`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`,
`files_touched`, `task_id`, `evidence_id`, `raw` (plus the `total_tokens`
property). `evidence_id` is set (equal to `task_id`) only when
`config.evidence.enabled` and the call ran in `executor` mode — chat-only
calls have no `WorkReport`/file mutation to evidence.

`tests/test_sdk_contracts.py` freezes the constructor parameter list/order
and the `AgentResult` field set as snapshots — see that file's docstring for
the update procedure if either genuinely needs to change.

## Public contracts (Phase 2)

```python
from voly import Agent, Workflow

researcher = Agent("researcher", instructions="Find verifiable facts")
reviewer = Agent("reviewer", instructions="Check claims and sources")

workflow = Workflow("research-review")
workflow.add("research", agent=researcher)
workflow.add("review", agent=reviewer, depends_on=["research"])

result = workflow.run("Compare two markets")
```

```python
Workflow(name: str, *, config: VOLYConfig | None = None)

workflow.add(
    node_id: str,               # positional
    *,
    agent: Agent,
    task: str = "",
    depends_on: list[str] | None = None,
    approval: bool = False,
    acceptance: list[AcceptanceCheck] | None = None,
    timeout_seconds: int | None = None,  # accepted, currently a no-op — see mapping table above
) -> Workflow                   # chainable

workflow.compile(task: str = "", *, cwd: str | None = None) -> Plan
workflow.run(
    task: str = "", *, cwd=None, resume: bool = False,
    mode: str | None = None, timeout_seconds: float | None = None,
) -> WorkflowResult
workflow.arun(...) -> WorkflowResult   # asyncio.to_thread(self.run, ...), same reasoning as Agent.arun()

# Phase 3 — see "Resuming/cancelling a workflow" below
workflow.resume(plan_id: str, *, mode=None, timeout_seconds=None) -> WorkflowResult
workflow.cancel(plan_id: str, *, error: str = "cancelled") -> None
```

`compile()`/`run()` raise `WorkflowError` for a duplicate node id, an unknown
`depends_on` target, a dependency cycle, or an empty workflow (all detected
by `PlanEngine.validate()` and re-raised with the SDK's own exception type).
`run(resume=True)` raises `NotImplementedError` — see "Resuming/cancelling a
workflow" below for `Workflow.resume(plan_id)`, the real, working
alternative.

`timeout_seconds` bounds `run()`'s whole call, not any one node — on expiry
the Plan is left resumable (`status="running"`, not failed/aborted); see
below.

`mode` defaults to `"active"` (hard gate — a failed/pending-approval node
blocks its dependents) regardless of the global `plan.mode` config value,
since a `Workflow` call site is a deliberate, new entry point where "governed
by default" is the right default independent of whatever `voly plan run`/A2A
happen to have `plan.mode` set to for their own purposes. Pass
`mode="shadow"` explicitly to soften non-approval acceptance failures.

`WorkflowResult` fields: `plan` (the executed `Plan`), `success`, `status`
(`plan.status`), `node_results` (`list[NodeResult]`, one per compiled node in
declaration order), `cost_usd` (sum of every node's `cost_usd`), `duration_ms`
(whole-Plan wall time from `PlanRunner`), `error`. `success` is `plan.status
== PLAN_COMPLETED` — a pending or failed node can never make this `True`.

`NodeResult` fields: `node_id`, `status` (the `PlanStep` status —
`pending`/`verifying`/`verified`/`failed`/…), `success` (`status == VERIFIED`),
`output`, `error`, `cost_usd`, `duration_ms`, `files_touched`. These are read
back from the executed `PlanStep` — never a live `AgentResult` kept around
from before the run, matching "resume by contract": everything `WorkflowResult`
reports is reconstructable from the persisted `Plan` alone.

### Approval nodes

`workflow.add("decide", agent=manager, approval=True)` compiles to a
`PlanStep` whose acceptance includes `human_review`. The node still runs
normally (the agent produces real output) — `approval=True` means that
output requires an explicit human sign-off before dependents may start, not
that the node is skipped. See `voly/plan/approval.py` and the "human_review"
section above for the underlying mechanism;
`tests/test_sdk_workflow.py::test_approval_blocks_downstream_execution` is
the full compile → run → pause → approve → resume round trip.

### Resuming/cancelling a workflow

`Workflow.run(resume=True)` is not implemented — `Workflow` has no way to
identify *which* prior Plan to resume from `task` text alone (compilation
deliberately gives every `compile()`/`run()` call a fresh `plan_id`; only the
node *topology* is guaranteed deterministic, see the proposal's compilation
note). `Workflow.resume(plan_id)` is the real, working alternative — the
caller supplies the `plan_id` from a prior `WorkflowResult.plan.plan_id`:

```python
result = workflow.run("Should we proceed?")   # pauses on an approval node
# ... time passes, a human reviews result.node("decide").output ...

from voly.plan.approval import decide as decide_human_review
from voly.plan.store import PlanStore

decide_human_review(PlanStore(config.plan.store_dir), result.plan.plan_id, "decide", "approve")
resumed = workflow.resume(result.plan.plan_id)
```

`resume()` also recovers a step stuck in `running` past
`workflow_sdk.stale_running_seconds` before continuing — that only happens
if the process that produced `result` crashed mid-step, since a live run
never revisits a `running` step itself. `Workflow.cancel(plan_id)` marks the
Plan aborted; safe to call from another thread/process while a
`run()`/`resume()` for the same `plan_id` is in flight elsewhere — see
`docs/backend/plan.md` for how the run loop avoids clobbering a cancel that
lands mid-step.

## Output handoff between nodes

A dependent node's instruction is never a live template over its
dependency's `AgentResult` — `PlanRunner` prepends each `depends_on` step's
stored `output` as plain context before the node's own task at execution
time (see `docs/backend/plan.md`). This is a `PlanRunner` behavior, not
something `Workflow` does at compile time, so it benefits every Plan, not
only SDK-built ones.

## Bounded parallel chat waves (Phase 3)

A `Workflow` with independent nodes (no `depends_on` between them) runs
them concurrently, bounded by `workflow_sdk.max_parallel_nodes`:

```python
workflow = Workflow("market-scan")
workflow.add("us", agent=Agent("us-analyst"))
workflow.add("eu", agent=Agent("eu-analyst"))
workflow.add("apac", agent=Agent("apac-analyst"))
workflow.add(
    "synthesize", agent=Agent("lead"), depends_on=["us", "eu", "apac"],
)
result = workflow.run("Compare regional demand")
```

With the default `max_parallel_nodes=3`, the three analyst nodes' chat calls
run at the same time (each sees the others' output only once all three are
`verified` and `synthesize` becomes runnable — see output handoff above);
`synthesize` still waits for all three regardless of concurrency.
`mode="executor"` nodes are never part of a wave — see
`docs/backend/plan.md` for why (they share the Plan's one `cwd`) and for the
concurrency-safety design (only network calls run in worker threads; every
`Plan`/`PlanStep` mutation happens back on the calling thread). Set
`workflow_sdk.max_parallel_nodes: 1` (or `workflow_sdk.enabled: false`) to
force today's original one-step-at-a-time behavior unconditionally.

## Bug fixed alongside PR1: `PlanRunner`'s default chat path was ungoverned

While wiring `Agent`'s chat mode through the same gateway construction
`Pipeline.gateway` uses, `voly/plan/runner.py::_exec_chat`'s fallback path
(used whenever a `Plan` is run without an injected `chat_fn` — which is what
every `Workflow`-compiled chat node does) was found
calling `AIGateway(self.config)` directly. `AIGateway.__init__` takes bare
constructor args (`account_id`, `gateway_id`, `api_token`), not a
`VOLYConfig` — passing one positionally lands it in the unrelated `provider`
slot, so `cache`/`rate_limit`/`spend_limit`/`dlp`/`fallback`/BYOK all stayed
at `AIGateway`'s bare dataclass defaults regardless of the caller's
`ai_gateway.*` config. Fixed by extracting the governed-wiring block already
duplicated across `Pipeline.gateway`, `SignalInterpreter._build_gateway`, and
others into `voly.ai_gateway.gateway_from_config(config)`, and pointing
`PlanRunner._exec_chat` and `Agent._run_chat` at it. See
`tests/test_plan_runner.py::test_default_chat_path_builds_a_governed_gateway`
for the regression test. The other existing duplicates of this wiring block
were left as-is (out of scope for this change) — a future cleanup could point
them at the same factory.

## Testing

```bash
python -m pytest tests/test_sdk_contracts.py tests/test_sdk_agent.py \
  tests/test_sdk_workflow.py tests/test_sdk_presets.py tests/test_sdk_loader.py \
  tests/test_workflow_cli.py tests/test_workflows_api.py tests/test_examples_workflows.py \
  tests/test_plan_runner.py tests/test_plan_approval.py tests/test_plan_concurrency.py \
  tests/test_protocol_contracts.py -q
ruff check voly/sdk voly/ai_gateway/factory.py voly/plan/approval.py voly/plan/runner.py \
  voly/cli/commands/workflow_cmd.py voly/web/routes/workflows.py examples/workflows
```

`tests/test_plan_concurrency.py` covers real wall-clock concurrency timing
(not mocked-out), bounded wave size, executor-node serialization, stale
recovery, resume-does-not-rerun-verified-nodes, cross-thread cancellation
and workflow-level timeout — the specific test categories Phase 3's proposal
calls for.

## Topology presets (Phase 4)

`voly.sdk.presets` (also exported from `voly` directly) provides six graph
factories over `Workflow`. Each is a plain function — `Workflow.add()` some
number of times, then return the builder — never a `Workflow`/`PlanRunner`
subclass with its own run loop, and never a provider import (covered by the
same `tests/test_sdk_contracts.py` import scan that covers `agent.py`/
`workflow.py`, since it walks all of `voly/sdk/`).

```python
from voly import Agent, sequential, concurrent, supervisor_workers, reviewer_loop, council, planner_generator_evaluator

result = sequential([Agent("researcher"), Agent("reviewer")]).run("Compare two markets")
result = concurrent([Agent("us"), Agent("eu"), Agent("apac")]).run("Regional demand")
result = supervisor_workers(Agent("lead"), [Agent("w1"), Agent("w2")]).run("Break down and solve")
result = reviewer_loop(Agent("writer"), Agent("editor"), max_iterations=3).run("Draft the memo")
result = council([Agent("bull"), Agent("bear")], Agent("judge")).run("Should we invest?")
result = planner_generator_evaluator(Agent("planner"), Agent("coder"), Agent("qa")).run("Ship the feature")
```

| Preset | Shape | Node ids | Bound |
|---|---|---|---|
| `sequential(agents, *, tasks=None)` | A → B → C | `n0, n1, ...` | `MAX_SEQUENTIAL_NODES=20`, ≥2 agents |
| `concurrent(agents, *, tasks=None)` | A, B, C (independent) | `n0, n1, ...` | `MAX_CONCURRENT_NODES=20`, ≥2 agents |
| `supervisor_workers(supervisor, workers, *, dispatch_task="", synthesis_task="")` | S → workers → S2 | `supervise`, `worker0, ...`, `synthesize` | `MAX_WORKERS=10`, ≥1 worker |
| `reviewer_loop(generator, reviewer, *, max_iterations=3, exit_acceptance=None)` | generate ↔ review, unrolled | `generate_0, review_0, generate_1, ...` | `MAX_REVIEWER_ITERATIONS=10`, ≥1 |
| `council(members, judge, *, member_task="", judge_task="")` | members → judge | `member0, ...`, `judge` | `MAX_COUNCIL_MEMBERS=10`, ≥2 members |
| `planner_generator_evaluator(planner, generator, evaluator)` | P → G → E | `plan`, `generate`, `evaluate` | fixed 3 nodes |

Every factory raises `WorkflowError` immediately if a bound is violated (not
a silent truncation), and every graph is an ordinary compiled `Plan` — the
same `WorkflowResult`/`NodeResult` contract, `depends_on`-based output
handoff, bounded parallel chat waves, resume and cancel documented above all
apply unchanged. `council`'s and `supervisor_workers`' aggregation/synthesis
step is a real second/extra chat call whose cost is included in
`WorkflowResult.cost_usd` like any other node — nothing here is free.

**`reviewer_loop`'s bound is real, its "exit" is partial.** `PlanEngine` has
no conditional-skip primitive — a Plan is a static DAG, not a state machine
with branches — so `reviewer_loop` cannot implement a true early-exit loop
that stops once a review approves. It unrolls into a **fixed** chain of
`max_iterations` `generate_i → review_i` pairs that **always all execute**.
`exit_acceptance`, if supplied, is attached only to the *final* round's
`review_{max_iterations - 1}` node: earlier rounds carry no acceptance
(`Plan`'s `(DONE, VERIFIED)` transition auto-passes an empty acceptance
list, per `voly/plan/types.py::LEGAL_TRANSITIONS`), so the chain is never
blocked mid-way regardless of what an intermediate round produced.
`WorkflowResult.success` therefore answers "did the last round satisfy the
exit criteria," not "did any round satisfy them" — a caller who wants the
first passing round can inspect `result.node(f"review_{i}")` for each `i`
directly. Making this a real early-exit loop is future work that needs
conditional-skip support in `PlanEngine`, not in the SDK layer.

`council` and `supervisor_workers`' judge/synthesis output is evidence for
the caller to read from `WorkflowResult`, not an implicit authorization to
bypass human approval — neither preset adds a `human_review` gate; pass
`approval=True` by building the graph manually with `Workflow.add()` (or
post-process the preset's returned `Workflow` before calling `.run()`) if
one is required.

**Tests:** `tests/test_sdk_presets.py` — graph-shape snapshots, bound
enforcement, dependency-output handoff (`supervisor_workers`'
synthesis/`council`'s judge actually see prior outputs), failure
propagation (`sequential`), cost aggregation (`concurrent`), and both
`reviewer_loop` exit-gate outcomes (all-verified vs. final-round-fails).

## CLI, REST/SSE and UI (Phase 5)

`voly.sdk.loader.load_workflow_file`/`load_workflow_dict` build a `Workflow`
from a YAML/JSON **Workflow document** — distinct from a raw Plan YAML
(`voly.plan.loader.load_plan_file`, `voly plan run`): a Workflow document is
`Agent`-shaped (`name`, `instructions`, `model`/`provider`/`tier`, `mode`,
`executor`) per node, not already-resolved `PlanStep` fields.

```yaml
name: research-review
task: Compare two markets
nodes:
  - id: research
    agent: {name: researcher, instructions: Find verifiable facts}
  - id: review
    agent: {name: reviewer}
    depends_on: [research]
```

CLI (`voly/cli/commands/workflow_cmd.py`, alongside the pre-existing
`review-until-clean`/`stats` subcommands for the unrelated bounded-review
workflow concept):

```bash
voly workflow validate wf.yaml
voly workflow run wf.yaml [--task ...] [--cwd ...] [--mode active|shadow] [--timeout-seconds N] [--json-out]
voly workflow resume <plan_id> [--mode ...] [--timeout-seconds N] [--json-out]
voly workflow show <plan_id> [--json-out]
```

`resume`/`show` take a `plan_id`, not a file — resuming/inspecting operates
on the persisted Plan directly (`voly.plan.runner.PlanRunner`/`PlanStore`),
the same way `Workflow.resume(plan_id)` does in Python.

REST/SSE: `voly/web/routes/workflows.py` — `POST /api/workflows/validate`,
`POST /api/workflows/run`, `POST /api/workflows/{plan_id}/resume` (SSE, node
lifecycle events), `GET /api/workflows`, `GET /api/workflows/{plan_id}`,
`POST /api/workflows/{plan_id}/nodes/{node_id}/decide`. Full contract in
`docs/backend/api.md`'s "Workflow SDK" section. Node events are produced by
polling the same `PlanStore`-persisted Plan every ~1s (mirroring `/api/run`'s
existing heartbeat-polling SSE pattern in `voly/web/routes/run.py`, at
Phase 3's per-step persistence granularity) — not a push channel threaded
through `PlanRunner`'s internals, so the CLI, Python and UI never observe
divergent state (`docs/proposals/agent-workflow-sdk.md`'s "UI and SDK
disagree" risk mitigation).

UI: `ui/src/lib/components/workflows/WorkflowsPage.svelte` at `#/workflows`
— a read-only list + per-node detail view (status, role/model/provider,
`depends_on`, duration, cost) reading `GET /api/workflows`/`GET
/api/workflows/{plan_id}`, with Approve/Reject on a node paused in
`verifying` with a `human_review` acceptance check. It observes persisted
Plans only; it does not yet trigger `run`/`resume` itself (the proposal
defers drag-and-drop editing until "the read-only graph contract is
stable" — this ships that contract first). Docs: `docs/frontend/api-client.md`,
`docs/frontend/components.md`, `docs/frontend/overview.md`.

**Tests:** `tests/test_sdk_loader.py`, `tests/test_workflow_cli.py`
(Phase-5 subcommands), `tests/test_workflows_api.py`.

## Examples and benchmark (Phase 6)

`examples/workflows/` — see its own `README.md` for the full catalog and
`BENCHMARK.md` for the measured (not estimated) first-run-LOC / graph /
resume / evidence / failure-honesty comparison the proposal calls for. 7 of
the originally-scoped 10 examples are implemented; 3 (structured-output,
MCP-tool-allowlist, capability-routed) are blocked on `Agent` capabilities
that are accepted on the constructor but still raise `NotImplementedError`
(`tools`, `output_schema`) or don't exist yet (capability-registry routing)
— see the catalog README's "Not implemented" section rather than a faked
stand-in. `tests/test_examples_workflows.py` runs every implemented example
offline as a regression suite.

The benchmark surfaced one real, previously-undocumented gap: a
`Workflow`-compiled executor-mode node's `AgentRunner` evidence record is
written but not recoverable from `WorkflowResult`/`NodeResult` (no
`evidence_id` field on either) — unlike a direct `Agent.run(mode="executor")`
call, which does surface one. Left as a documented gap, not fixed here:
`NodeResult`'s field set is a frozen contract
(`tests/test_sdk_contracts.py::test_node_result_field_contract_is_frozen`)
and changing it is a deliberate future phase, not an examples/benchmark PR.

## Not yet implemented

Within Phase 5: the UI has no run/resume trigger of its own yet, and there
is no drag-and-drop graph editor (explicitly deferred by the proposal).

Within what's landed: `Agent(tools=...)` / `Agent(output_schema=...)` are
accepted on the constructor (frozen contract) but raise `NotImplementedError`
if actually set — a node built from such an `Agent` can therefore never
reach compilation with them either. `WorkflowNode.timeout_seconds` (a
*per-node* hint) is still accepted and stored but not enforced — distinct
from the *workflow-level* `run(timeout_seconds=...)`, which is enforced; no
phase currently owns per-node timeout enforcement specifically.
`Workflow.run(resume=True)` still raises `NotImplementedError` —
`Workflow.resume(plan_id)` (an explicit plan_id) is the real mechanism.
