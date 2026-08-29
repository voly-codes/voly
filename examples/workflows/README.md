# Workflow SDK examples

Phase 6 of `docs/proposals/agent-workflow-sdk.md`. Ten examples were
originally scoped; **seven have a runnable example script** (1–7 below).
8–10 don't yet, though the `Agent` capabilities they'd demonstrate
(structured output, tool-calling, capability routing) have since landed —
see "Not implemented" at the bottom for the current, narrower gap.

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

8. a structured-output workflow — `Agent(output_schema=...)` **is now
   implemented** (prompt-based validation against a pydantic model or a raw
   JSON schema dict; see `docs/backend/sdk.md`'s "Structured output"
   section). No example script for it exists in this catalog yet — writing
   one is now a small, unblocked follow-up, not blocked engineering work.
9. a tool-allowlist workflow — `Agent(tools=[...])` **is now implemented**
   (a bounded tool-call loop against `voly.sdk.tools`'s explicit allowlist
   registry; see `docs/backend/sdk.md`'s "Tool calling" section). It is
   *not* a Model Context Protocol (MCP) client — see that section for why —
   so this stays named "tool-allowlist," not "MCP tool," going forward. No
   example script for it exists yet either.
10. a capability-routed development workflow — `voly.capability.routing.
    capability_route()` **is now implemented** and wired into both
    standalone `Agent.run()` and `PlanRunner`'s default `_exec_chat`/
    `_exec_executor` paths (so it applies to `Workflow`-compiled graphs and
    hand-written Plan YAML alike), gated on `config.capability.enabled`
    (default `False`) and only consulted when the caller left
    `model`/`tier`/`executor` unset; see `docs/backend/capability.md`'s
    "Agent/Workflow SDK integration" section. No example script yet.

All three underlying gaps this section originally described are closed —
what remains is writing the example scripts themselves (8, 9, 10), each a
small addition once picked up, not new capability. `tests/test_sdk_agent.py`,
`tests/test_sdk_tools.py` and `tests/test_capability_routing.py` /
`tests/test_plan_runner.py`'s capability-routing tests already cover the
underlying behavior these three examples would demonstrate.
