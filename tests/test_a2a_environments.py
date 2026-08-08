from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from voly.a2a.environments import (
    AgentRequest,
    DebateEnv,
    IterativeRepairEnv,
    ParallelSolutionsEnv,
    PipelineEnv,
    SolverJudgeEnv,
)
from voly.a2a.episode import AgentTrace, RoleMetric, TraceDecision


@dataclass
class FakeAgent:
    agent_id: str
    role: str
    verdicts: list[str] = field(default_factory=list)
    requests: list[AgentRequest] = field(default_factory=list)

    async def run(self, request: AgentRequest) -> AgentTrace:
        self.requests.append(request)
        trace = AgentTrace.create(agent_id=self.agent_id, role=self.role, task=request.task)
        trace.status = "completed"
        if self.role == "judge":
            verdict = self.verdicts.pop(0) if self.verdicts else "pass"
            trace.metadata["verdict"] = verdict
            trace.metrics.append(RoleMetric(name="implementation_correctness", score=0.9, source="judge"))
            trace.decisions.append(TraceDecision(kind="verdict", summary=verdict))
        return trace


@pytest.mark.asyncio
async def test_solver_judge_receives_trace_and_read_only_tools() -> None:
    solver = FakeAgent("solver-1", "developer")
    judge = FakeAgent("judge-1", "judge")

    episode = await SolverJudgeEnv().run(
        "Implement feature", [solver, judge], task_id="task-1", acceptance_criteria=["tests pass"]
    )

    request = judge.requests[0]
    assert episode.environment == "solver-judge"
    assert request.read_only is True
    assert set(request.allowed_tools) == {"list_files", "read_file", "search_text", "git_diff"}
    assert request.context["solver_trace"]["role"] == "developer"
    assert episode.metrics[0].name == "implementation_correctness"


@pytest.mark.asyncio
async def test_builtin_interaction_patterns_produce_episodes() -> None:
    agents = [FakeAgent("a", "architect"), FakeAgent("b", "developer")]
    pipeline = await PipelineEnv().run("task", agents, task_id="pipeline")
    parallel = await ParallelSolutionsEnv().run("task", agents, task_id="parallel")
    debate = await DebateEnv(rounds=2).run("task", agents, task_id="debate")

    assert len(pipeline.traces) == 2
    assert len(parallel.traces) == 2
    assert len(debate.traces) == 4


@pytest.mark.asyncio
async def test_iterative_repair_stops_after_passing_judgement() -> None:
    solver = FakeAgent("solver", "developer")
    judge = FakeAgent("judge", "judge", verdicts=["fail", "pass"])

    episode = await IterativeRepairEnv(max_repairs=3).run("task", [solver, judge])

    assert len(solver.requests) == 2
    assert len(judge.requests) == 2
    assert len(episode.traces) == 4
