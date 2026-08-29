"""Reusable workflow topology presets (Phase 4 of docs/proposals/agent-workflow-sdk.md).

Each preset is a graph factory over ``Workflow``: a plain function that calls
``Workflow.add()`` some number of times and returns the (uncompiled) builder.
No preset subclasses ``Workflow``/``PlanRunner`` or runs its own loop — see
the proposal's "graph factories ... never subclasses with their own run
loops" constraint. Every bound below is enforced at build time (raises
``WorkflowError``); nothing is silently truncated.

Voting/judging output (``council``) and synthesis output
(``supervisor_workers``) are evidence for the caller to read from
``WorkflowResult``, not an authorization to bypass human approval — pass
``approval=True`` on a caller-added node if a gate is required; no preset
adds one implicitly.
"""

from __future__ import annotations

from typing import Any

from voly.plan.types import AcceptanceCheck
from voly.sdk.agent import Agent
from voly.sdk.workflow import Workflow, WorkflowError

MAX_SEQUENTIAL_NODES = 20
MAX_CONCURRENT_NODES = 20
MAX_WORKERS = 10
MAX_COUNCIL_MEMBERS = 10
MAX_REVIEWER_ITERATIONS = 10


def sequential(
    agents: list[Agent],
    *,
    name: str = "sequential",
    tasks: list[str] | None = None,
    config: Any = None,
) -> Workflow:
    """A -> B -> C -> ...

    Each node depends on the previous one and sees its output via
    ``PlanRunner``'s existing dependency-output handoff (see
    ``docs/backend/sdk.md``).
    """
    if len(agents) < 2:
        raise WorkflowError("sequential() requires at least 2 agents")
    if len(agents) > MAX_SEQUENTIAL_NODES:
        raise WorkflowError(f"sequential() supports at most {MAX_SEQUENTIAL_NODES} agents")
    if tasks is not None and len(tasks) != len(agents):
        raise WorkflowError("tasks must have the same length as agents")

    workflow = Workflow(name, config=config)
    previous: str | None = None
    for i, agent in enumerate(agents):
        node_id = f"n{i}"
        workflow.add(
            node_id,
            agent=agent,
            task=tasks[i] if tasks else "",
            depends_on=[previous] if previous else [],
        )
        previous = node_id
    return workflow


def concurrent(
    agents: list[Agent],
    *,
    name: str = "concurrent",
    tasks: list[str] | None = None,
    config: Any = None,
) -> Workflow:
    """A, B, C, ... run independently.

    ``PlanRunner`` schedules independent chat nodes in bounded parallel waves
    per ``workflow_sdk.max_parallel_nodes`` (``docs/backend/plan.md``);
    ``concurrent()`` itself only bounds node count, not actual parallelism.
    """
    if len(agents) < 2:
        raise WorkflowError("concurrent() requires at least 2 agents")
    if len(agents) > MAX_CONCURRENT_NODES:
        raise WorkflowError(f"concurrent() supports at most {MAX_CONCURRENT_NODES} agents")
    if tasks is not None and len(tasks) != len(agents):
        raise WorkflowError("tasks must have the same length as agents")

    workflow = Workflow(name, config=config)
    for i, agent in enumerate(agents):
        workflow.add(f"n{i}", agent=agent, task=tasks[i] if tasks else "")
    return workflow


def supervisor_workers(
    supervisor: Agent,
    workers: list[Agent],
    *,
    name: str = "supervisor-workers",
    dispatch_task: str = "",
    synthesis_task: str = "",
    config: Any = None,
) -> Workflow:
    """S -> workers -> S2.

    The supervisor dispatches (node ``supervise``), every worker runs
    independently off that output, then the *same* supervisor role
    synthesizes every worker's output — handed off automatically — into one
    result (node ``synthesize``). Cost is the sum of the supervisor's two
    calls plus every worker's call, like any other ``Workflow``.
    """
    if not workers:
        raise WorkflowError("supervisor_workers() requires at least 1 worker")
    if len(workers) > MAX_WORKERS:
        raise WorkflowError(f"supervisor_workers() supports at most {MAX_WORKERS} workers")

    workflow = Workflow(name, config=config)
    workflow.add("supervise", agent=supervisor, task=dispatch_task)
    worker_ids = []
    for i, worker in enumerate(workers):
        node_id = f"worker{i}"
        worker_ids.append(node_id)
        workflow.add(node_id, agent=worker, depends_on=["supervise"])
    workflow.add(
        "synthesize",
        agent=supervisor,
        task=synthesis_task or "Synthesize the workers' outputs above into one result.",
        depends_on=worker_ids,
    )
    return workflow


def reviewer_loop(
    generator: Agent,
    reviewer: Agent,
    *,
    name: str = "reviewer-loop",
    max_iterations: int = 3,
    exit_acceptance: list[AcceptanceCheck] | None = None,
    generate_task: str = "",
    review_task: str = "",
    config: Any = None,
) -> Workflow:
    """generate <-> review, unrolled into a fixed, bounded chain.

    ``PlanEngine`` has no conditional-skip primitive, so this cannot be a
    true early-exit loop: every one of ``max_iterations`` rounds always
    executes (see ``docs/backend/sdk.md``'s "Not yet implemented" section).
    ``exit_acceptance``, if given, gates only the *final* round's review
    node — the workflow reports success only if the last round's output
    satisfies it. Earlier rounds carry no acceptance (empty acceptance
    auto-verifies) so the chain is never blocked mid-way.
    """
    if max_iterations < 1:
        raise WorkflowError("reviewer_loop() requires max_iterations >= 1")
    if max_iterations > MAX_REVIEWER_ITERATIONS:
        raise WorkflowError(
            f"reviewer_loop() supports at most {MAX_REVIEWER_ITERATIONS} iterations"
        )

    workflow = Workflow(name, config=config)
    previous: str | None = None
    for i in range(max_iterations):
        gen_id, rev_id = f"generate_{i}", f"review_{i}"
        workflow.add(
            gen_id,
            agent=generator,
            task=generate_task,
            depends_on=[previous] if previous else [],
        )
        is_last = i == max_iterations - 1
        workflow.add(
            rev_id,
            agent=reviewer,
            task=review_task,
            depends_on=[gen_id],
            acceptance=list(exit_acceptance or []) if is_last else [],
        )
        previous = rev_id
    return workflow


def council(
    members: list[Agent],
    judge: Agent,
    *,
    name: str = "council",
    member_task: str = "",
    judge_task: str = "",
    config: Any = None,
) -> Workflow:
    """members -> judge.

    Every member runs independently; the judge sees every member's output
    (handed off automatically) and produces one aggregated decision — the
    explicit aggregation policy the proposal calls for is this single judge
    node, not an implicit vote count.
    """
    if len(members) < 2:
        raise WorkflowError("council() requires at least 2 members")
    if len(members) > MAX_COUNCIL_MEMBERS:
        raise WorkflowError(f"council() supports at most {MAX_COUNCIL_MEMBERS} members")

    workflow = Workflow(name, config=config)
    member_ids = []
    for i, member in enumerate(members):
        node_id = f"member{i}"
        member_ids.append(node_id)
        workflow.add(node_id, agent=member, task=member_task)
    workflow.add(
        "judge",
        agent=judge,
        task=judge_task
        or "Review every council member's output above and produce one aggregated decision.",
        depends_on=member_ids,
    )
    return workflow


def planner_generator_evaluator(
    planner: Agent,
    generator: Agent,
    evaluator: Agent,
    *,
    name: str = "planner-generator-evaluator",
    plan_task: str = "",
    generate_task: str = "",
    evaluate_task: str = "",
    config: Any = None,
) -> Workflow:
    """P -> G -> E: a fixed 3-role chain with a structured contract between
    roles — each role's default task states what it consumes and produces."""
    workflow = Workflow(name, config=config)
    workflow.add("plan", agent=planner, task=plan_task or "Produce a concrete plan for the task.")
    workflow.add(
        "generate",
        agent=generator,
        task=generate_task or "Execute the plan above and produce the result.",
        depends_on=["plan"],
    )
    workflow.add(
        "evaluate",
        agent=evaluator,
        task=evaluate_task or "Evaluate the result above against the plan above.",
        depends_on=["generate"],
    )
    return workflow
