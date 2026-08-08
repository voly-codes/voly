"""Deterministic product-proof cases for externally stated VOLY claims.

These tests intentionally separate verified capabilities from roadmap claims.
They use no model provider, network access, or mutable user configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from voly.a2a.assignment import Assignment
from voly.a2a.environments import AgentRequest, SolverJudgeEnv
from voly.a2a.episode import (
    AgentTrace,
    RoleMetric,
    TraceArtifact,
    TraceDecision,
    episode_from_assignments,
)
from voly.config import CostPolicyConfig, VOLYConfig
from voly.cost_policy import budget_status


def test_proof_episode_preserves_multi_agent_cost_and_lineage() -> None:
    """One episode keeps role costs, fallback attempts, artifacts and parents."""
    architect = Assignment(
        0,
        "architect",
        "Design the change",
        [],
        "standard",
        "model-a",
        "provider-a",
        content="plan",
        ok=True,
        cost_usd=0.03,
    )
    developer = Assignment(
        1,
        "developer",
        "Implement the change",
        [0],
        "standard",
        "model-b",
        "provider-b",
        content="implemented",
        ok=True,
        mode="executor",
        executor="opencode",
        files_touched=["src/app.py"],
        cost_usd=0.07,
        chain_timelog=[
            {"executor": "claude-code", "status": "billing_error", "duration_ms": 10},
            {"executor": "opencode", "status": "success", "duration_ms": 20},
        ],
    )

    episode = episode_from_assignments(
        task_id="proof-cost-lineage",
        task="Implement a bounded change",
        assignments=[architect, developer],
        acceptance_criteria=["src/app.py exists"],
    )

    assert episode.status == "completed"
    assert sum(trace.cost_usd for trace in episode.traces) == pytest.approx(0.10)
    assert episode.traces[1].parent_trace_ids == [episode.traces[0].trace_id]
    assert [call.arguments["executor"] for call in episode.traces[1].tool_calls] == [
        "claude-code",
        "opencode",
    ]
    assert episode.traces[1].tool_calls[0].ok is False
    assert episode.traces[1].tool_calls[1].ok is True
    assert episode.traces[1].artifacts[0].uri == "src/app.py"


@dataclass
class _ProofAgent:
    agent_id: str
    role: str
    verdict: str = ""
    requests: list[AgentRequest] = field(default_factory=list)

    async def run(self, request: AgentRequest) -> AgentTrace:
        self.requests.append(request)
        trace = AgentTrace.create(
            agent_id=self.agent_id,
            role=self.role,
            task=request.task,
            parent_trace_ids=list(request.parent_trace_ids),
        )
        trace.status = "completed"
        if self.role == "developer":
            trace.artifacts.append(TraceArtifact(kind="file", uri="src/app.py"))
        else:
            trace.metadata["verdict"] = self.verdict
            trace.decisions.append(
                TraceDecision(
                    kind="verdict",
                    summary=self.verdict,
                    rationale="Independent acceptance check",
                )
            )
            trace.metrics.append(
                RoleMetric(
                    name="implementation_correctness",
                    score=1.0 if self.verdict == "pass" else 0.0,
                    source="deterministic-proof-judge",
                    evidence="Acceptance criterion evaluated independently",
                )
            )
        return trace


@pytest.mark.asyncio
async def test_proof_solver_judge_is_read_only_and_trace_linked() -> None:
    """The judge receives the solver trace through a read-only tool boundary."""
    solver = _ProofAgent(agent_id="solver-1", role="developer")
    judge = _ProofAgent(agent_id="judge-1", role="judge", verdict="pass")

    episode = await SolverJudgeEnv().run(
        "Implement answer",
        [solver, judge],
        task_id="proof-solver-judge",
        acceptance_criteria=["src/app.py contains the answer"],
    )

    judge_request = judge.requests[0]
    assert judge_request.read_only is True
    assert set(judge_request.allowed_tools) == {
        "list_files",
        "read_file",
        "search_text",
        "git_diff",
    }
    assert judge_request.parent_trace_ids == (episode.traces[0].trace_id,)
    assert judge_request.context["solver_trace"]["trace_id"] == episode.traces[0].trace_id
    assert episode.decisions[0].summary == "pass"
    assert episode.metrics[0].name == "implementation_correctness"


def test_proof_completed_run_cost_can_be_classified_over_budget() -> None:
    """Current policy truthfully detects over-budget cost after it is known."""
    config = VOLYConfig(
        cost_policy=CostPolicyConfig(
            enabled=True,
            max_task_cost_usd=0.50,
            stop_on_budget_exceeded=True,
        )
    )

    assert budget_status(0.49, config) == "completed"
    assert budget_status(0.51, config) == "budget_exceeded"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Roadmap contract: atomic parent/child pre-dispatch budget inheritance is "
        "not implemented; current max_task_cost_usd is evaluated post-run"
    ),
)
def test_contract_tree_wide_budget_is_inherited_before_child_dispatch() -> None:
    """Do not market tree-wide budget inheritance until this contract passes."""
    config = VOLYConfig(
        cost_policy=CostPolicyConfig(
            enabled=True,
            max_task_cost_usd=0.50,
            stop_on_budget_exceeded=True,
        )
    )

    # The desired API must reserve child spend atomically before dispatch.
    reservation = config.cost_policy.reserve_child_budget(  # type: ignore[attr-defined]
        task_id="parent",
        child_id="developer",
        projected_cost_usd=0.30,
    )
    assert reservation.remaining_task_budget_usd == pytest.approx(0.20)
