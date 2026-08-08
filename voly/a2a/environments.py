"""Programmable interaction patterns for multi-agent episodes."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from voly.a2a.episode import AgentTrace, MultiAgentEpisode, TraceDecision, utc_now

READ_ONLY_JUDGE_TOOLS = ("list_files", "read_file", "search_text", "git_diff")


@dataclass(frozen=True)
class AgentRequest:
    task: str
    acceptance_criteria: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    parent_trace_ids: tuple[str, ...] = ()
    read_only: bool = False
    allowed_tools: tuple[str, ...] = ()


class EpisodeAgent(Protocol):
    agent_id: str
    role: str

    async def run(self, request: AgentRequest) -> AgentTrace: ...


class MultiAgentEnvironment(ABC):
    """Interaction pattern independent from concrete role implementations."""

    name = "base"

    @abstractmethod
    async def run(
        self,
        task: str,
        agents: list[EpisodeAgent],
        *,
        task_id: str = "",
        acceptance_criteria: list[str] | None = None,
    ) -> MultiAgentEpisode:
        raise NotImplementedError

    def _episode(
        self,
        task: str,
        task_id: str,
        acceptance_criteria: list[str] | None,
    ) -> MultiAgentEpisode:
        return MultiAgentEpisode.create(
            task_id=task_id,
            task=task,
            environment=self.name,
            acceptance_criteria=list(acceptance_criteria or []),
        )

    @staticmethod
    def _finish(episode: MultiAgentEpisode) -> MultiAgentEpisode:
        episode.completed_at = utc_now()
        episode.status = (
            "completed"
            if episode.traces and all(trace.status == "completed" for trace in episode.traces)
            else "partial" if any(trace.status == "completed" for trace in episode.traces)
            else "failed"
        )
        return episode


class PipelineEnv(MultiAgentEnvironment):
    name = "pipeline"

    async def run(self, task: str, agents: list[EpisodeAgent], *, task_id: str = "", acceptance_criteria: list[str] | None = None) -> MultiAgentEpisode:
        episode = self._episode(task, task_id, acceptance_criteria)
        parents: list[str] = []
        for agent in agents:
            trace = await agent.run(
                AgentRequest(
                    task=task,
                    acceptance_criteria=tuple(episode.acceptance_criteria),
                    context={"prior_traces": [item.to_dict() for item in episode.traces]},
                    parent_trace_ids=tuple(parents[-1:]),
                )
            )
            episode.traces.append(trace)
            parents.append(trace.trace_id)
            if trace.status != "completed":
                episode.decisions.append(TraceDecision(kind="pipeline_stop", summary=f"Stopped after {agent.role}", rationale=trace.error))
                break
        return self._finish(episode)


class ParallelSolutionsEnv(MultiAgentEnvironment):
    name = "parallel-solutions"

    async def run(self, task: str, agents: list[EpisodeAgent], *, task_id: str = "", acceptance_criteria: list[str] | None = None) -> MultiAgentEpisode:
        episode = self._episode(task, task_id, acceptance_criteria)
        request = AgentRequest(task=task, acceptance_criteria=tuple(episode.acceptance_criteria))
        episode.traces.extend(await asyncio.gather(*(agent.run(request) for agent in agents)))
        return self._finish(episode)


class SolverJudgeEnv(MultiAgentEnvironment):
    """Run one solver, then an independent judge with read-only repository tools."""

    name = "solver-judge"

    async def run(self, task: str, agents: list[EpisodeAgent], *, task_id: str = "", acceptance_criteria: list[str] | None = None) -> MultiAgentEpisode:
        if len(agents) != 2:
            raise ValueError("SolverJudgeEnv requires exactly [solver, judge]")
        episode = self._episode(task, task_id, acceptance_criteria)
        solver, judge = agents
        solver_trace = await solver.run(
            AgentRequest(task=task, acceptance_criteria=tuple(episode.acceptance_criteria))
        )
        episode.traces.append(solver_trace)
        judge_trace = await judge.run(
            AgentRequest(
                task="Independently evaluate the solver result",
                acceptance_criteria=tuple(episode.acceptance_criteria),
                parent_trace_ids=(solver_trace.trace_id,),
                read_only=True,
                allowed_tools=READ_ONLY_JUDGE_TOOLS,
                context={
                    "original_task": task,
                    "solver_trace": solver_trace.to_dict(),
                    "diff_artifacts": [item.to_dict() if hasattr(item, "to_dict") else item.__dict__ for item in solver_trace.artifacts],
                },
            )
        )
        episode.traces.append(judge_trace)
        episode.metrics.extend(judge_trace.metrics)
        episode.decisions.extend(judge_trace.decisions)
        return self._finish(episode)


class DebateEnv(MultiAgentEnvironment):
    name = "debate"

    def __init__(self, rounds: int = 2) -> None:
        if rounds < 1:
            raise ValueError("debate rounds must be positive")
        self.rounds = rounds

    async def run(self, task: str, agents: list[EpisodeAgent], *, task_id: str = "", acceptance_criteria: list[str] | None = None) -> MultiAgentEpisode:
        episode = self._episode(task, task_id, acceptance_criteria)
        for round_index in range(self.rounds):
            snapshot = [trace.to_dict() for trace in episode.traces]
            traces = await asyncio.gather(
                *(
                    agent.run(
                        AgentRequest(
                            task=task,
                            acceptance_criteria=tuple(episode.acceptance_criteria),
                            context={"round": round_index + 1, "debate": snapshot},
                            parent_trace_ids=tuple(trace.trace_id for trace in episode.traces),
                        )
                    )
                    for agent in agents
                )
            )
            episode.traces.extend(traces)
        return self._finish(episode)


class IterativeRepairEnv(MultiAgentEnvironment):
    name = "iterative-repair"

    def __init__(self, max_repairs: int = 2) -> None:
        if max_repairs < 0:
            raise ValueError("max_repairs cannot be negative")
        self.max_repairs = max_repairs

    async def run(self, task: str, agents: list[EpisodeAgent], *, task_id: str = "", acceptance_criteria: list[str] | None = None) -> MultiAgentEpisode:
        if len(agents) != 2:
            raise ValueError("IterativeRepairEnv requires exactly [solver, judge]")
        episode = self._episode(task, task_id, acceptance_criteria)
        solver, judge = agents
        feedback: dict[str, Any] = {}
        for attempt in range(self.max_repairs + 1):
            solver_trace = await solver.run(
                AgentRequest(
                    task=task,
                    acceptance_criteria=tuple(episode.acceptance_criteria),
                    context={"attempt": attempt + 1, "judge_feedback": feedback},
                    parent_trace_ids=tuple(trace.trace_id for trace in episode.traces[-1:]),
                )
            )
            episode.traces.append(solver_trace)
            judge_trace = await judge.run(
                AgentRequest(
                    task="Evaluate the latest repair",
                    acceptance_criteria=tuple(episode.acceptance_criteria),
                    context={"original_task": task, "solver_trace": solver_trace.to_dict()},
                    parent_trace_ids=(solver_trace.trace_id,),
                    read_only=True,
                    allowed_tools=READ_ONLY_JUDGE_TOOLS,
                )
            )
            episode.traces.append(judge_trace)
            feedback = judge_trace.metadata
            if judge_trace.metadata.get("verdict") == "pass":
                break
        episode.metrics.extend(metric for trace in episode.traces for metric in trace.metrics)
        episode.decisions.extend(decision for trace in episode.traces for decision in trace.decisions)
        return self._finish(episode)
