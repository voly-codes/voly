"""Phase 1 (docs/proposals/agent-workflow-sdk.md): public Agent SDK facade.

Agent must remain a thin facade: chat mode delegates exclusively to
AIGateway.chat(), executor mode delegates exclusively to AgentRunner.run().
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from voly import Agent, AgentError, AgentResult
from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult, WorkReport
from voly.runner.agent_runner import RunnerResult


def _config() -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    return config


def _fake_chat(content: str = "hello", model: str = "claude-x", error: str = "", **usage):
    def _chat(self, **kwargs):  # noqa: ANN001
        result = {
            "content": content,
            "model": model,
            "usage": {
                "input_tokens": usage.get("input_tokens", 10),
                "output_tokens": usage.get("output_tokens", 5),
            },
        }
        if error:
            result["error"] = error
        return result

    return _chat


def test_import_smoke() -> None:
    from voly import Agent as ImportedAgent

    assert ImportedAgent is Agent


def test_chat_mode_delegates_to_gateway_and_returns_typed_result() -> None:
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat("Paris is the capital")):
        agent = Agent("researcher", instructions="Find facts", config=_config())
        result = agent.run("What is the capital of France?")

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.content == "Paris is the capital"
    assert result.model == "claude-x"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15
    assert result.cost_usd >= 0
    assert result.task_id


def test_chat_mode_surfaces_gateway_error_as_unsuccessful_result() -> None:
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat(error="DLP blocked: secret")):
        agent = Agent("researcher", config=_config())
        result = agent.run("leak a secret")

    assert result.success is False
    assert "DLP blocked" in result.error


def test_chat_call_is_attributable_to_the_gateway_invocation() -> None:
    """No-direct-provider invariant: the SDK must go through AIGateway.chat(),
    never construct/call a provider client itself."""
    calls = []

    def spy_chat(self, **kwargs):
        calls.append(kwargs)
        return {"content": "ok", "model": "claude-x", "usage": {"input_tokens": 1, "output_tokens": 1}}

    with patch("voly.ai_gateway.gateway.AIGateway.chat", spy_chat):
        Agent("researcher", instructions="be terse", config=_config()).run("hi")

    assert len(calls) == 1
    assert calls[0]["agent"] == "researcher"
    assert calls[0]["system"] == "be terse"


def test_executor_mode_requires_explicit_cwd() -> None:
    agent = Agent("coder", mode="executor", config=_config())
    with pytest.raises(AgentError, match="requires an explicit cwd"):
        agent.run("write a file")


def test_executor_mode_delegates_to_agent_runner(tmp_path) -> None:
    report = WorkReport(files_created=["a.py"], files_changed=["b.py"])
    er = ExecutorResult(
        success=True, output="done", cost_usd=0.02, input_tokens=100,
        output_tokens=50, duration_ms=42.0, report=report,
    )
    runner_result = RunnerResult(
        success=True, executor="claude-code", agent="coder", task_id="tid-1", result=er,
    )

    with patch("voly.runner.agent_runner.AgentRunner.run", return_value=runner_result) as run_mock:
        agent = Agent("coder", mode="executor", config=_config())
        result = agent.run("write a file", cwd=str(tmp_path))

    run_mock.assert_called_once()
    assert result.success is True
    assert result.executor == "claude-code"
    assert result.cost_usd == 0.02
    assert result.duration_ms == 42.0
    assert sorted(result.files_touched) == ["a.py", "b.py"]
    assert result.task_id == "tid-1"


def test_executor_mode_folds_instructions_into_the_task() -> None:
    """Regression: _run_executor used to drop self.instructions entirely —
    only _run_chat threaded it through (as the `system` prompt). An
    Agent(instructions=..., mode="executor") must not silently lose it."""
    er = ExecutorResult(success=True, output="done")
    runner_result = RunnerResult(
        success=True, executor="claude-code", agent="coder", task_id="tid-3", result=er,
    )
    with patch(
        "voly.runner.agent_runner.AgentRunner.run", return_value=runner_result
    ) as run_mock:
        agent = Agent("coder", instructions="Follow house style", mode="executor", config=_config())
        agent.run("write a file", cwd="/tmp/project")

    sent_task = run_mock.call_args.args[0]
    assert "Follow house style" in sent_task
    assert "write a file" in sent_task


def test_executor_mode_surfaces_failure() -> None:
    er = ExecutorResult(success=False, error="executor failed")
    runner_result = RunnerResult(
        success=False, executor="claude-code", agent="coder", task_id="tid-2", result=er,
    )
    with patch("voly.runner.agent_runner.AgentRunner.run", return_value=runner_result):
        agent = Agent("coder", mode="executor", config=_config())
        result = agent.run("break something", cwd="/tmp/project")

    assert result.success is False
    assert result.error == "executor failed"


def test_arun_returns_the_same_result_as_run() -> None:
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat("async hello")):
        agent = Agent("researcher", config=_config())
        result = asyncio.run(agent.arun("hi"))

    assert isinstance(result, AgentResult)
    assert result.content == "async hello"


def test_invalid_mode_raises_agent_error() -> None:
    with pytest.raises(AgentError):
        Agent("x", mode="bogus")  # type: ignore[arg-type]


def test_tools_not_yet_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Agent("x", tools=["search"])


def test_output_schema_not_yet_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Agent("x", output_schema=dict)
