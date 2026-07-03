"""P0 A2A fixes: recursion guard and context handoff."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from voly.a2a import A2AOrchestrator, A2ATask, TaskState
from voly.a2a.decomposer import Subtask, TaskDecomposer
from voly.pipeline import Pipeline
from voly.pipeline_server import _is_nested_a2a_request


def test_is_nested_a2a_request_from_task_id() -> None:
    nested, ctx = _is_nested_a2a_request({"task": "do work", "task_id": "sub-1"})
    assert nested is True
    assert ctx["a2a_parent_task_id"] == "sub-1"


def test_is_nested_a2a_request_from_explicit_parent() -> None:
    nested, ctx = _is_nested_a2a_request(
        {"task": "do work", "a2a_parent_task_id": "parent-9"}
    )
    assert nested is True
    assert ctx["a2a_parent_task_id"] == "parent-9"


def test_is_nested_a2a_request_plain_run() -> None:
    nested, ctx = _is_nested_a2a_request({"task": "hello", "agent": "developer"})
    assert nested is False
    assert ctx == {}


def test_inject_prior_context_appends_dependency_output() -> None:
    desc = TaskDecomposer.inject_prior_context(
        "Review implementation",
        [("developer", "def add(): return 1")],
    )
    assert "Review implementation" in desc
    assert "### developer" in desc
    assert "def add()" in desc


def test_decomposer_reviewer_depends_on_developer() -> None:
    analysis = MagicMock(
        requires_code_gen=True,
        requires_review=True,
        requires_testing=False,
        requires_deployment=False,
        complexity="medium",
    )
    subtasks = TaskDecomposer().decompose("add feature X", analysis)
    assert len(subtasks) == 2
    assert subtasks[0].agent == "developer"
    assert subtasks[1].agent == "reviewer"
    assert subtasks[1].depends_on == [0]


def test_should_dispatch_a2a_skips_when_nested() -> None:
    pipeline = Pipeline()
    analysis = MagicMock(
        requires_code_gen=True,
        requires_review=True,
        requires_testing=True,
        requires_deployment=False,
        complexity="high",
    )
    pipeline.config.a2a.enabled = True
    pipeline.config.a2a.auto_dispatch = True
    assert pipeline._should_dispatch_a2a(analysis, nested=True) is False


def test_is_a2a_nested_env_and_context() -> None:
    pipeline = Pipeline()
    assert pipeline._is_a2a_nested({"a2a_parent_task_id": "x"}) is True
    assert pipeline._is_a2a_nested({}) is False

    prev = os.environ.get("CODEOPS_A2A_NESTED")
    os.environ["CODEOPS_A2A_NESTED"] = "1"
    try:
        assert pipeline._is_a2a_nested({}) is True
    finally:
        if prev is None:
            os.environ.pop("CODEOPS_A2A_NESTED", None)
        else:
            os.environ["CODEOPS_A2A_NESTED"] = prev


def test_dispatch_parallel_injects_prior_results() -> None:
    orch = A2AOrchestrator()
    subtasks = [
        Subtask("Implement feature", "developer"),
        Subtask("Review code", "reviewer", depends_on=[0]),
    ]

    dev_task = A2ATask(
        id="dev-1",
        state=TaskState.COMPLETED,
        result="implemented add()",
        metadata={"agent": "developer"},
    )
    review_task = A2ATask(id="rev-1", state=TaskState.SUBMITTED, metadata={"agent": "reviewer"})
    captured: list[str] = []

    def fake_create(title: str, description: str, agent_name: str | None = None) -> A2ATask:
        captured.append(description)
        return review_task if "reviewer" in title else dev_task

    with patch.object(orch, "create_task", side_effect=fake_create), patch.object(
        orch, "route_and_delegate", side_effect=lambda t: t
    ), patch.object(orch, "collect_results", side_effect=lambda t: t):
        orch.dispatch_parallel(subtasks, timeout_seconds=1.0)

    assert len(captured) == 2
    assert "implemented add()" in captured[1]
    assert "### developer" in captured[1]


@pytest.mark.parametrize(
    "levels_input,expected",
    [
        (
            [Subtask("a", "architect"), Subtask("b", "developer", depends_on=[0])],
            [[0], [1]],
        ),
        (
            [
                Subtask("a", "developer"),
                Subtask("b", "tester", depends_on=[0]),
                Subtask("c", "reviewer", depends_on=[0, 1]),
            ],
            [[0], [1], [2]],
        ),
    ],
)
def test_dependency_levels(levels_input: list[Subtask], expected: list[list[int]]) -> None:
    assert A2AOrchestrator._dependency_levels(levels_input) == expected
