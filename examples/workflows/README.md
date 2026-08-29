# Workflow SDK examples

Phase 6 of `docs/proposals/agent-workflow-sdk.md`. Ten examples were
originally scoped; **seven are implemented** (1–7 below). 8–10 are not —
see "Not implemented" at the bottom for why, rather than a faked stand-in.

Every example is a standalone, runnable script:

```bash
python examples/workflows/01_sequential_research_review.py --offline
```

`--offline` patches `AIGateway.chat` (and, for example 3,
`AgentRunner.run`) with canned responses — no credentials, no network, no
file writes outside example 3's own offline-patched executor call. Drop
`--offline` for a live run using whatever `AIGateway`/executor credentials
`voly.yaml`/`.env` already configure for `voly run` — no example needs
extra setup beyond that (except example 3, which additionally needs a real
`--cwd` git repository, and example 4 and 7, which write to the configured
`plan.store_dir` like any other `voly workflow run`).

Every example's own docstring states its expected `--offline` output,
required credentials, and cost/safety notes — that detail isn't repeated
here. `tests/test_examples_workflows.py` runs all seven offline as a
regression suite and asserts each docstring actually contains those three
sections.

| # | Example | Builder style | Demonstrates |
|---|---|---|---|
| 1 | `01_sequential_research_review.py` | `presets.sequential()` | dependency-output handoff |
| 2 | `02_parallel_market_analysis.py` | `presets.supervisor_workers()` | bounded concurrent waves + synthesis |
| 3 | `03_repo_change_tester_reviewer.py` | manual `Workflow` | mixed chat/executor graph, `cwd` |
| 4 | `04_human_approved_action.py` | manual `Workflow` | `approval=True` gate, pause/decide/resume |
| 5 | `05_incident_triage_parallel_investigators.py` | manual `Workflow` | read-only parallel fan-in (no preset used, for contrast) |
| 6 | `06_planner_generator_evaluator.py` | `presets.planner_generator_evaluator()` | structured role contract |
| 7 | `07_resumable_long_running_workflow.py` | manual `Workflow` | workflow-level timeout + resume, zero re-execution |

`BENCHMARK.md` is the required "comparison benchmark for first-run lines of
code, graph construction, resume, evidence completeness and failure
honesty" — measured against these examples and the test suite, not
estimated, and including one found-and-documented gap (evidence
completeness) rather than only favorable numbers.

## Not implemented (8–10)

The original ten-example list included:

8. a structured-output workflow — needs `Agent(output_schema=...)`, which
   raises `NotImplementedError` today (Phase 1 accepted the constructor
   parameter but never implemented it; see `docs/backend/sdk.md`'s "Not yet
   implemented" section).
9. an MCP tool workflow with an explicit allowlist — needs
   `Agent(tools=...)`, same status: accepted, not implemented, raises
   `NotImplementedError`.
10. a capability-routed development workflow — `voly.capability`'s
    `ExecutorMatcher` (used by `voly.decisions.DecisionService` for business
    actions) is not wired into `Agent`/`Workflow` at all; an `Agent`'s
    `executor`/`model`/`provider` are fixed at construction, not resolved by
    the capability registry per-run.

Building a fake version of any of these would misrepresent what
`voly.sdk` can actually do today. They stay on the list as the natural next
examples once their underlying `Agent` capabilities land — not deleted from
the proposal, just honestly unimplemented here.
