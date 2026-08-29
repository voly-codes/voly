"""Workflow builder compiled to Plan (Phase 2 of docs/proposals/agent-workflow-sdk.md).

``Workflow`` is a builder, not a second runtime: ``compile()`` turns declared
nodes into an ordinary ``voly.plan.types.Plan``; ``run()``/``arun()`` hand
that Plan to the existing ``PlanRunner`` for execution and ``PlanStore`` for
persistence. Node-to-dependency validation (duplicate ids, missing deps,
cycles) is enforced by the existing ``PlanEngine`` — this module does not
reimplement graph validation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from voly.plan.types import AcceptanceCheck, PlanStep, PlanValidationError
from voly.sdk.agent import Agent


class WorkflowError(ValueError):
    """Usage error building/compiling a Workflow (not a node run-time failure)."""


@dataclass
class WorkflowNode:
    node_id: str
    agent: Agent
    task: str = ""
    depends_on: list[str] = field(default_factory=list)
    approval: bool = False
    acceptance: list[AcceptanceCheck] = field(default_factory=list)
    timeout_seconds: int | None = None


@dataclass
class NodeResult:
    """One compiled node's outcome, read back from the executed Plan's
    PlanStep — never a live AgentResult carried over from a previous
    process (see the proposal's "resume by contract" principle)."""

    node_id: str
    status: str
    success: bool
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    files_touched: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    plan: Any  # voly.plan.types.Plan
    success: bool
    status: str
    node_results: list[NodeResult] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str = ""

    def node(self, node_id: str) -> NodeResult | None:
        for r in self.node_results:
            if r.node_id == node_id:
                return r
        return None


class Workflow:
    def __init__(self, name: str, *, config: Any = None) -> None:
        if not name or not name.strip():
            raise WorkflowError("Workflow name is required")
        if "/" in name or "\\" in name:
            raise WorkflowError(f"Workflow name must not contain a path separator: {name!r}")
        self.name = name
        self._nodes: dict[str, WorkflowNode] = {}
        self._order: list[str] = []

        from voly.config import VOLYConfig

        self.config = config or VOLYConfig()

    def add(
        self,
        node_id: str,
        *,
        agent: Agent,
        task: str = "",
        depends_on: list[str] | None = None,
        approval: bool = False,
        acceptance: list[AcceptanceCheck] | None = None,
        timeout_seconds: int | None = None,
    ) -> Workflow:
        if not node_id or not node_id.strip():
            raise WorkflowError("node_id is required")
        if node_id in self._nodes:
            raise WorkflowError(f"duplicate node id: {node_id!r}")
        if agent is None:
            raise WorkflowError(f"node {node_id!r} requires an agent")
        self._nodes[node_id] = WorkflowNode(
            node_id=node_id,
            agent=agent,
            task=task,
            depends_on=list(depends_on or []),
            approval=approval,
            acceptance=list(acceptance or []),
            timeout_seconds=timeout_seconds,
        )
        self._order.append(node_id)
        return self

    def compile(self, task: str = "", *, cwd: str | None = None) -> Any:
        """Compile declared nodes into an ordinary Plan.

        Deterministic in topology: the same nodes/dependencies/task always
        compile to the same PlanStep shape. plan_id is a fresh id each call
        (a "runtime id", per the proposal's compilation-determinism note),
        so calling compile() twice never collides in PlanStore.
        """
        if not self._nodes:
            raise WorkflowError(f"workflow {self.name!r} has no nodes")

        steps = [self._compile_node(self._nodes[node_id], task) for node_id in self._order]

        from voly.plan.engine import create_plan
        from voly.telemetry import new_task_id

        try:
            plan = create_plan(
                f"{self.name}-{new_task_id()}",
                steps,
                cwd=cwd or "",
                task=task,
                validate=True,
            )
        except PlanValidationError as exc:
            raise WorkflowError(str(exc)) from exc
        plan.metadata["kind"] = "sdk_workflow"
        plan.metadata["workflow_name"] = self.name
        return plan

    def _compile_node(self, node: WorkflowNode, workflow_task: str) -> PlanStep:
        agent = node.agent
        instruction = node.task or workflow_task
        if agent.instructions:
            instruction = f"{agent.instructions}\n\n{instruction}".strip()

        if agent.tier:
            from voly.a2a.assignment import resolve_tier_model

            model, provider = resolve_tier_model(agent.tier)
        else:
            model, provider = agent.model or "", agent.provider or ""

        acceptance = list(node.acceptance)
        if node.approval:
            from voly.plan.verify_types import CHECK_HUMAN_REVIEW

            acceptance.append(AcceptanceCheck(type=CHECK_HUMAN_REVIEW))

        return PlanStep(
            id=node.node_id,
            role=agent.name,
            mode=agent.mode,
            depends_on=list(node.depends_on),
            acceptance=acceptance,
            task=instruction,
            executor=agent.executor or "",
            model=model,
            provider=provider,
            tier=agent.tier or "",
        )

    def run(
        self,
        task: str = "",
        *,
        cwd: str | None = None,
        resume: bool = False,
        mode: str | None = None,
        timeout_seconds: float | None = None,
    ) -> WorkflowResult:
        if resume:
            raise NotImplementedError(
                "Workflow.run(resume=True) is not implemented — it cannot "
                "identify which prior Plan to resume from task text alone "
                "(plan_id is a fresh id every compile() call; only node "
                "topology is deterministic). Use Workflow.resume(plan_id) "
                "with the plan_id from a prior WorkflowResult.plan.plan_id "
                "instead; see docs/backend/sdk.md."
            )

        plan = self.compile(task, cwd=cwd)

        from voly.plan.runner import PlanRunner

        runner = PlanRunner(self.config, emit_event=False)
        run_mode = mode or "active"
        plan_result = runner.run(plan, mode=run_mode, cwd=cwd, timeout_seconds=timeout_seconds)
        return self._build_result(plan_result)

    async def arun(
        self,
        task: str = "",
        *,
        cwd: str | None = None,
        resume: bool = False,
        mode: str | None = None,
        timeout_seconds: float | None = None,
    ) -> WorkflowResult:
        return await asyncio.to_thread(
            self.run, task, cwd=cwd, resume=resume, mode=mode, timeout_seconds=timeout_seconds
        )

    def resume(
        self,
        plan_id: str,
        *,
        mode: str | None = None,
        timeout_seconds: float | None = None,
    ) -> WorkflowResult:
        """Continue a previously compiled Plan by its ``plan_id`` (e.g. from
        a prior ``WorkflowResult.plan.plan_id``) — the practical alternative
        to ``run(resume=True)``, which cannot identify which Plan to resume
        from task text alone. Recovers any step stuck in ``running`` past
        ``workflow_sdk.stale_running_seconds`` before continuing.
        """
        from voly.plan.runner import PlanRunner

        runner = PlanRunner(self.config, emit_event=False)
        plan_result = runner.resume(plan_id, mode=mode, timeout_seconds=timeout_seconds)
        return self._build_result(plan_result)

    def cancel(self, plan_id: str, *, error: str = "cancelled") -> None:
        """Mark a persisted Plan aborted. Safe to call while a run()/resume()
        for the same plan_id is in flight elsewhere (another thread/process)
        — it stops cooperatively between waves/steps, not mid-call."""
        from voly.plan.runner import PlanRunner

        PlanRunner(self.config, emit_event=False).cancel(plan_id, error=error)

    def _build_result(self, plan_result: Any) -> WorkflowResult:
        from voly.plan.types import VERIFIED

        plan = plan_result.plan
        node_results = [
            NodeResult(
                node_id=step.id,
                status=step.status,
                success=step.status == VERIFIED,
                output=step.output,
                error=step.error,
                cost_usd=step.cost_usd,
                duration_ms=step.duration_ms,
                files_touched=list(step.files_touched),
            )
            for step in plan.steps
        ]
        return WorkflowResult(
            plan=plan,
            success=plan_result.success,
            status=plan.status,
            node_results=node_results,
            cost_usd=round(sum(r.cost_usd for r in node_results), 6),
            duration_ms=plan_result.duration_ms,
            error=plan_result.error,
        )
