from __future__ import annotations

from voly.a2a.assignment import Assignment
from voly.a2a.episode import (
    AgentTrace,
    EpisodeStore,
    MultiAgentEpisode,
    RoleMetric,
    TraceArtifact,
    TraceDecision,
    TraceMessage,
    TraceToolCall,
    episode_from_assignments,
)


def test_episode_round_trip_preserves_unified_trace(tmp_path) -> None:
    trace = AgentTrace.create(agent_id="agent-1", role="developer", task="Implement feature")
    trace.status = "completed"
    trace.messages.append(TraceMessage(role="assistant", content="Implemented"))
    trace.tool_calls.append(TraceToolCall(name="read_file", ok=True, result="source"))
    trace.artifacts.append(TraceArtifact(kind="file", uri="src/app.py"))
    trace.decisions.append(TraceDecision(kind="implementation", summary="Reuse service"))
    trace.metrics.append(
        RoleMetric(
            name="implementation_correctness",
            score=0.9,
            source="judge",
            evidence="Acceptance checks passed",
        )
    )
    episode = MultiAgentEpisode.create(
        task_id="task-1",
        task="Implement feature",
        environment="solver-judge",
        traces=[trace],
        acceptance_criteria=["Tests pass"],
    )

    store = EpisodeStore(tmp_path / "episodes")
    path = store.save(episode)
    loaded = store.load("task-1")

    assert path.name == "task-1.json"
    assert loaded is not None
    assert loaded.to_dict() == episode.to_dict()


def test_role_metrics_are_bounded_and_named() -> None:
    RoleMetric(name="test_coverage", score=1.0, source="deterministic")

    for kwargs in (
        {"name": "unknown", "score": 0.5},
        {"name": "test_coverage", "score": 1.1},
    ):
        try:
            RoleMetric(source="test", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid role metric must be rejected")


def test_assignment_adapter_links_dependency_traces_and_artifacts() -> None:
    architect = Assignment(0, "architect", "Plan", [], "strong", "m1", "p1", content="plan", ok=True)
    developer = Assignment(
        1,
        "developer",
        "Build",
        [0],
        "strong",
        "m2",
        "p2",
        content="done",
        ok=True,
        mode="executor",
        files_touched=["src/app.py"],
        cost_usd=0.1,
        chain_timelog=[{"executor": "cursor", "status": "success", "duration_ms": 12}],
    )

    episode = episode_from_assignments(task_id="t", task="Build", assignments=[architect, developer])

    assert developer.trace_id
    assert episode.traces[1].parent_trace_ids == [architect.trace_id]
    assert episode.traces[1].artifacts[0].uri == "src/app.py"
    assert episode.traces[1].tool_calls[0].name == "executor_attempt"
    assert developer.to_event_dict()["role_metrics"][0]["name"] == "cost_adjusted_contribution"
