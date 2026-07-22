from __future__ import annotations

from dataclasses import dataclass

import pytest

from voly.executor.base import ExecutorResult, WorkReport
from voly.runner.agent_runner import RunnerResult
from voly.workflow.review_until_clean import (
    ReviewStopReason,
    ReviewUntilClean,
    ReviewVerdict,
    parse_review_verdict,
)


@dataclass
class _FakeRunner:
    results: list[RunnerResult]

    def __post_init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, task, executor, **kwargs):
        self.calls.append({"task": task, "executor": executor, **kwargs})
        return self.results.pop(0)


class _FakeGateway:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.responses.pop(0)


def _run_result(*, success=True, task_id="run-1", cost=0.1, error=""):
    result = ExecutorResult(
        success=success,
        output="developer output",
        error=error,
        cost_usd=cost,
        report=WorkReport(files_changed=["app.py"]),
    )
    return RunnerResult(
        success=success,
        executor="claude-code",
        agent="developer",
        task_id=task_id,
        result=result,
    )


def test_clean_first_lap(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    runner = _FakeRunner([_run_result()])
    gateway = _FakeGateway([{
        "content": '{"verdict":"clean","findings":[],"summary":"ok"}',
        "cost_usd": 0.02,
    }])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix app", cwd=str(tmp_path), reviewer_model="review-model",
        reviewer_provider="review-provider",
    )

    assert result.success is True
    assert result.stop_reason is ReviewStopReason.CLEAN
    assert result.laps[0].verdict is ReviewVerdict.CLEAN
    assert result.total_cost_usd == 0.12
    assert runner.calls[0]["emit_event"] is False
    assert gateway.calls[0]["agent"] == "reviewer"


def test_blocking_review_reactivates_developer(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    runner = _FakeRunner([
        _run_result(task_id="run-1"),
        _run_result(task_id="run-2"),
    ])
    gateway = _FakeGateway([
        {"content": '{"verdict":"blocking","findings":["Handle None"],"summary":"bug"}'},
        {"content": '{"verdict":"clean","findings":[],"summary":"fixed"}'},
    ])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix app", cwd=str(tmp_path), max_rounds=3,
        reviewer_model="m", reviewer_provider="p",
    )

    assert result.success is True
    assert len(result.laps) == 2
    assert "Handle None" in runner.calls[1]["task"]
    assert "original task" in runner.calls[1]["task"].lower()


def test_stops_at_max_rounds(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    runner = _FakeRunner([_run_result(), _run_result(task_id="run-2")])
    blocking = {"content": '{"verdict":"blocking","findings":["still broken"]}'}
    gateway = _FakeGateway([blocking.copy(), blocking.copy()])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), max_rounds=2,
        reviewer_model="m", reviewer_provider="p",
    )

    assert result.success is False
    assert result.stop_reason is ReviewStopReason.MAX_ROUNDS
    assert len(result.laps) == 2


def test_executor_failure_stops_before_review(tmp_path) -> None:
    runner = _FakeRunner([_run_result(success=False, error="executor failed")])
    gateway = _FakeGateway([])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), reviewer_model="m", reviewer_provider="p",
    )

    assert result.stop_reason is ReviewStopReason.EXECUTOR_FAILED
    assert result.error == "executor failed"
    assert gateway.calls == []


def test_invalid_review_fails_closed(tmp_path) -> None:
    runner = _FakeRunner([_run_result()])
    gateway = _FakeGateway([{"content": "looks good"}])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), reviewer_model="m", reviewer_provider="p",
    )

    assert result.stop_reason is ReviewStopReason.REVIEW_FAILED
    assert "invalid JSON" in result.error


def test_spend_limited_review_has_explicit_stop_reason(tmp_path) -> None:
    runner = _FakeRunner([_run_result()])
    gateway = _FakeGateway([{
        "content": "", "error": "Spend limit exceeded", "spend_limited": True,
    }])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), reviewer_model="m", reviewer_provider="p",
    )

    assert result.stop_reason is ReviewStopReason.SPEND_LIMIT


def test_parse_review_verdict_accepts_json_fence() -> None:
    verdict, findings = parse_review_verdict(
        '```json\n{"verdict":"blocking","findings":["Fix race"]}\n```'
    )
    assert verdict is ReviewVerdict.BLOCKING
    assert findings == ["Fix race"]


@pytest.mark.parametrize(
    "payload",
    [
        '{"verdict":"clean","findings":["contradiction"]}',
        '{"verdict":"blocking","findings":[]}',
        '{"verdict":"maybe","findings":[]}',
    ],
)
def test_parse_review_verdict_rejects_ambiguous_payload(payload) -> None:
    with pytest.raises(ValueError):
        parse_review_verdict(payload)
