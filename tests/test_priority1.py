"""Tests for cost policy, automation score, and agent runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codeops.automation import compute_automation_metrics
from codeops.config import VOLYConfig, CostPolicyConfig
from codeops.cost_policy import (
    apply_cost_policy,
    budget_status,
    detect_task_type,
    is_budget_exceeded,
)
from codeops.executor.base import ExecutorResult
from codeops.router import RouteDecision
from codeops.runner.agent_runner import resolve_executor


def test_detect_task_type_docs() -> None:
    assert detect_task_type("Update README documentation") == "docs"
    assert detect_task_type("Напиши документацию к API") == "docs"


def test_detect_task_type_tests() -> None:
    assert detect_task_type("Add pytest tests for auth") == "tests"


def test_detect_task_type_none() -> None:
    assert detect_task_type("Implement login form") is None


def test_apply_cost_policy_switches_model() -> None:
    config = VOLYConfig(
        cost_policy=CostPolicyConfig(
            enabled=True,
            prefer_cheaper_model_for=["docs"],
            cheaper_model="deepseek-v4-flash",
        ),
    )
    route = RouteDecision(agent="developer", model="claude-sonnet", provider="anthropic")
    result = apply_cost_policy(route, "Write README docs", config)
    assert result.task_type == "docs"
    assert result.model_override == "deepseek-v4-flash"
    assert result.provider_override == "opencode"


def test_apply_cost_policy_disabled() -> None:
    config = VOLYConfig(cost_policy=CostPolicyConfig(enabled=False))
    route = RouteDecision(agent="developer", model="claude-sonnet", provider="anthropic")
    result = apply_cost_policy(route, "Write docs", config)
    assert result.model_override is None


def test_budget_exceeded() -> None:
    config = VOLYConfig(
        cost_policy=CostPolicyConfig(
            enabled=True,
            max_task_cost_usd=0.5,
            stop_on_budget_exceeded=True,
        ),
    )
    assert is_budget_exceeded(0.6, config) is True
    assert is_budget_exceeded(0.3, config) is False
    assert budget_status(0.6, config) == "budget_exceeded"
    assert budget_status(0.3, config) == "completed"


def test_compute_automation_cursor() -> None:
    result = ExecutorResult(success=True, num_turns=5)
    score, steps = compute_automation_metrics("cursor", result)
    assert score >= 0.9
    assert steps == 20


def test_compute_automation_failed() -> None:
    result = ExecutorResult(success=False, num_turns=2)
    score, steps = compute_automation_metrics("cursor", result)
    assert score < 0.5
    assert steps == 0


def test_compute_automation_pipeline() -> None:
    result = ExecutorResult(success=True, num_turns=1)
    score, steps = compute_automation_metrics(
        "pipeline", result, task_type="docs", via_pipeline=True
    )
    assert 0.4 <= score <= 1.0
    assert steps >= 1


def test_resolve_executor_direct() -> None:
    config = VOLYConfig()
    executor, role = resolve_executor("cursor", config)
    assert executor == "cursor"
    assert role == "cursor"


def test_resolve_executor_alias() -> None:
    config = VOLYConfig()
    executor, role = resolve_executor("codex", config)
    assert executor == "claude-code"
    assert role == "codex"


def test_resolve_executor_from_config() -> None:
    from codeops.config import AgentConfig

    config = VOLYConfig(
        agents={"developer": AgentConfig(name="developer", executor="opencode")},
    )
    executor, role = resolve_executor("developer", config)
    assert executor == "opencode"
    assert role == "developer"


def test_agent_runner_emits_telemetry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from codeops.config import RTKConfig
    from codeops.runner.agent_runner import AgentRunner

    config = VOLYConfig(rtk=RTKConfig(enabled=False))
    mock_result = ExecutorResult(
        success=True,
        output="done",
        cost_usd=0.01,
        input_tokens=100,
        output_tokens=50,
        duration_ms=500,
        num_turns=3,
    )
    mock_executor = MagicMock()
    mock_executor.run.return_value = mock_result

    events: list = []

    def capture(event, events_dir=None):
        events.append(event)
        return tmp_path / "event.json"

    monkeypatch.setattr(
        "codeops.runner.agent_runner._build_executor",
        lambda name: mock_executor,
    )
    monkeypatch.setattr("codeops.runner.agent_runner.emit_event_from_config", capture)

    runner = AgentRunner(config)
    result = runner.run("fix bug", "cursor", cwd=str(tmp_path))

    assert result.success is True
    assert len(events) == 1
    assert events[0].executor == "cursor"
    assert events[0].automation_score > 0
    assert events[0].manual_steps_removed == 12
