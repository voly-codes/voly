# Public Agent and Workflow SDK

Proposal: `docs/proposals/agent-workflow-sdk.md`. This doc tracks what is
actually implemented; the proposal tracks the full multi-phase plan.

**Status: Phase 0 + Phase 1 landed**, plus the generic approval-gate
primitive Phase 2 needs (`voly/plan/approval.py`, `PlanRunner.resume()`) built
ahead of schedule to resolve a design gap found while planning Phase 2 (see
below). `Workflow`/`WorkflowResult` themselves do not exist yet.

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
- from Phase 2 on, `Workflow.compile()` produces an ordinary `voly.plan.Plan`
  and execution stays inside `PlanEngine`/`PlanRunner` — no second state
  machine.

No module under `voly/sdk/` constructs a provider client (`anthropic`,
`openai`, raw `httpx`/`requests`, …) or calls one directly —
`tests/test_sdk_contracts.py::test_sdk_source_never_imports_a_provider_client_directly`
freezes that invariant by scanning the package's imports.

## `Agent` → `PlanStep` / `Workflow` → `Plan` mapping

This mapping is normative for Phase 2 (`Workflow` does not exist yet, but the
mapping is fixed now so Phase 1's `Agent` fields need no renaming later):

| `Agent` field | `PlanStep` field (Phase 2) |
|---|---|
| `name` | `role` |
| `instructions` | folded into the chat `system` prompt at execution time, not stored on `PlanStep` |
| `model` / `provider` / `tier` | `model` / `provider` (tier is resolved to a concrete model/provider before compilation — `PlanStep` carries no tier concept) |
| `mode` (`chat`/`executor`) | `mode` (`voly.plan.types.MODE_CHAT` / `MODE_EXECUTOR`) |
| `executor` | `executor` |
| `tools`, `output_schema` | not yet representable on `PlanStep` — raises `NotImplementedError` today (see below) |

A `workflow.add(node_id, agent=..., depends_on=..., approval=..., acceptance=...)`
call is expected to compile to one `PlanStep` per node, with `approval=True`
adding a preceding step whose acceptance is `human_review` — resolved via
`voly.plan.approval.decide()`, see below.

## Schema-version policy

Phase 1 introduces no new persisted schema (no `Workflow`/`Plan` compilation
yet) and changes no existing one — `TaskEvent` stays at `schema_version=4`. A
chat call made through `Agent.run()` emits a plain `TaskEvent` with
`workflow="sdk-agent"` so it is visible in `voly runs list`/telemetry exactly
like every other chat call; it does not add fields to the frozen `TaskEvent`
contract (see `tests/test_protocol_contracts.py`).

When Phase 2 compiles `Workflow` to `Plan`, that `Plan` is a normal
`voly.plan.types.Plan` (current `SCHEMA_VERSION`) with `metadata["kind"]` set
to `"sdk_workflow"` (mirroring the `"business_decision"` convention already
used by `voly.decisions.DecisionService`) — not a new persisted format.

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
business-specific layer — a future `Workflow.add(..., approval=True)` would
compile to a Plan whose approval step's acceptance is `human_review`, and
resolve it through `voly.plan.approval.decide()` directly, exactly the way
this is tested today.

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

## Bug fixed alongside PR1: `PlanRunner`'s default chat path was ungoverned

While wiring `Agent`'s chat mode through the same gateway construction
`Pipeline.gateway` uses, `voly/plan/runner.py::_exec_chat`'s fallback path
(used whenever a `Plan` is run without an injected `chat_fn` — which is what
every `Workflow`-compiled chat node will do from Phase 2 on) was found
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
  tests/test_plan_runner.py tests/test_plan_approval.py \
  tests/test_protocol_contracts.py -q
ruff check voly/sdk voly/ai_gateway/factory.py voly/plan/approval.py
```

## Not yet implemented

`Workflow`/`WorkflowResult` themselves, parallel chat waves, the six topology
presets, CLI/API/UI surfaces, and the `examples/workflows/` catalog — see
Phase 2 onward in `docs/proposals/agent-workflow-sdk.md`. `Agent(tools=...)`
and `Agent(output_schema=...)` are accepted on the constructor (frozen
contract) but raise `NotImplementedError` if actually set. `PlanRunner.resume()`
is a minimal version — it does not yet implement Phase 3's stale-running
recovery policy or workflow-level timeout/cancellation.
