# Workflow SDK — comparison benchmark

Phase 6 of `docs/proposals/agent-workflow-sdk.md` asks for "a comparison
benchmark for first-run lines of code, graph construction, resume, evidence
completeness and failure honesty." This is that comparison. Every number
below was measured against the files in this repository at the time of
writing (commands included) — none are estimated. Per the proposal's own
warning, **this makes no claim about model output quality**; it is a
structural comparison between building on `voly.sdk.Workflow` and building
the equivalent by hand on top of `voly.plan`.

## 1. First-run lines of code

Measured: `voly.sdk.presets.sequential()` building example 1's graph vs. a
hand-written `voly.plan.types.Plan` YAML doing the same thing
(`examples/workflows/_plan_equivalent_01.yaml`, verified to load and pass
`PlanEngine().validate()`).

```bash
awk '/^def build_workflow/,/^    return/' examples/workflows/01_sequential_research_review.py | wc -l   # 8
grep -vc '^\s*#\|^\s*$' examples/workflows/_plan_equivalent_01.yaml                                       # 12 (16 incl. comments)
```

| | Lines |
|---|---|
| `sequential([researcher, reviewer])` (2 `Agent()` + 1 preset call) | 8 |
| Equivalent hand-written Plan YAML (content lines, comments excluded) | 12 |

The gap is bigger than 8-vs-12 suggests once dependencies compound: the YAML
needs one `depends_on:` line and one `id`/`role`/`mode`/`task` block *per
node*, so an N-node sequential chain grows the YAML linearly with no
compression, while the SDK version stays `sequential([a1, ..., aN])` — one
call regardless of N (see `voly/sdk/presets.py::sequential`, bounded at
`MAX_SEQUENTIAL_NODES = 20`). The gap widens further for `supervisor_workers`/
`council`/`reviewer_loop`, where the hand-written YAML equivalent must also
get every `depends_on` fan-in/fan-out list right by hand — `PlanEngine`
still validates it either way, but the human error surface for a large graph
is materially smaller with a preset.

## 2. Graph construction

Both paths converge on the same object: `Workflow.compile()` and a raw Plan
YAML both produce an ordinary `voly.plan.types.Plan`, validated by the same
`PlanEngine.validate()` (duplicate ids, missing dependencies, cycles — see
`tests/test_sdk_workflow.py::test_cycle_rejected` /
`test_missing_dependency_rejected`). The SDK adds nothing to this step
beyond ergonomics: `Workflow.add()`/preset factories are pure Python that
call `PlanStep(...)` for you (`voly/sdk/workflow.py::_compile_node`) — there
is no second graph representation, no second validator, and no drift risk
between what the SDK "means" and what the Plan FSM actually executes.

## 3. Resume

Demonstrated end-to-end by example 7
(`07_resumable_long_running_workflow.py`) and
`tests/test_sdk_workflow.py::test_workflow_resume_continues_a_prior_run_by_plan_id`:
a `run(timeout_seconds=...)` call that expires mid-chain leaves the Plan in
`status="running"` (resumable), not `"failed"`/`"aborted"`; the already-
`verified` node is never re-executed on `Workflow.resume(plan_id)` — the next
`run()` call recomputes runnable steps from whatever is currently persisted
(`docs/backend/sdk.md`'s "Resolved: human_review is now a generic approval
primitive" section). A hand-written Plan gets the identical guarantee for
free (`PlanRunner.resume()` doesn't know or care whether a Plan came from a
YAML file or `Workflow.compile()`) — resume is a `PlanRunner`/`PlanEngine`
property, not something the SDK adds.

## 4. Evidence completeness — a real, found gap

This is not a clean win for the SDK. `Agent.run(mode="executor")` sets
`AgentResult.evidence_id` from the underlying `AgentRunner`'s `task_id`
(`voly/sdk/agent.py:250`, gated on `config.evidence.enabled`). A
`Workflow`-compiled executor-mode node goes through a *different* path —
`PlanRunner._exec_executor()` (`voly/plan/runner.py:679`) — which also calls
`AgentRunner.run()` (so an `EvidenceStore` record is still written
internally) but never captures the `RunnerResult.task_id` it returns, and
`NodeResult` (`voly/sdk/workflow.py`) has no `evidence_id` field at all. In
practice: a `Workflow` executor node's evidence record exists in the
`EvidenceStore` but is **not recoverable** from `WorkflowResult`/`NodeResult`
— a caller would have to scan the store rather than being handed the id.
Example 3 (`03_repo_change_tester_reviewer.py`) exercises this exact path
and its offline test does not assert an `evidence_id` for that reason — there
is nothing to assert. This is left as a known gap for a future phase, not
silently patched here: fixing it needs a new `PlanStep.evidence_id` field
and a `NodeResult.evidence_id` field, and `NodeResult`'s field set is a
frozen contract (`tests/test_sdk_contracts.py::test_node_result_field_contract_is_frozen`)
— changing it deliberately, with the schema-version discipline the proposal
calls for, is out of scope for an examples/benchmark PR.

## 5. Failure honesty

`WorkflowResult.success` is `plan.status == PLAN_COMPLETED` — a plain
derived bool, not a value a node's own text output can spoof
(`tests/test_sdk_contracts.py::test_workflow_never_reports_success_when_a_required_node_is_pending_or_failed`
freezes the field's *type*; the functional guarantee is exercised by
`tests/test_sdk_workflow.py::test_run_never_reports_success_when_a_node_fails`
and this catalog's own
`tests/test_examples_workflows.py::test_03_repo_change_tester_reviewer` /
`test_01_sequential_research_review`, both of which assert `success is True`
only once every node reaches `verified`). `sequential()`'s own contract test
(`tests/test_sdk_presets.py::test_sequential_failure_blocks_downstream`)
confirms a mid-chain failure leaves the *rest* of the chain `pending`, not
silently skipped-and-reported-successful. A hand-written Plan gets the same
guarantee from `PlanEngine`/`PlanRunner` directly — again, not something the
SDK adds, but something it never weakens either: no code path in
`voly/sdk/` sets a step or Plan status directly; every status transition
still goes through `PlanEngine.transition()`.

## Bottom line

The SDK's real, measured wins are ergonomics and error-surface reduction at
construction time (§1, §2) — not a new execution guarantee, since resume
(§3) and failure honesty (§5) are `PlanEngine`/`PlanRunner` properties any
Plan gets regardless of how it was built. §4 is an honest regression to flag,
not a benchmark result to hide: building an executor-mode node through
`Workflow` today loses evidence traceability that direct `Agent.run()` calls
still have.
