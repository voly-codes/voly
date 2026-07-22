from __future__ import annotations

from dataclasses import dataclass

import pytest

from voly.executor.base import ExecutorResult, WorkReport
from voly.runner.agent_runner import RunnerResult
from voly.runtime.runs import RunTracker
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
    assert result.laps[0].developer_cost_usd == 0.1
    assert result.laps[0].reviewer_cost_usd == 0.02
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


def test_parent_run_record_contains_causal_timeline(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    tracker = RunTracker(str(tmp_path / ".voly" / "runs"))
    runner = _FakeRunner([_run_result()])
    gateway = _FakeGateway([{
        "content": '{"verdict":"clean","findings":[],"summary":"ok"}',
    }])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), reviewer_model="m", reviewer_provider="p",
        tracker=tracker, workflow_id="workflow-1",
    )

    record = tracker.load("workflow-1")
    assert result.workflow_id == "workflow-1"
    assert record is not None
    assert record.workflow == "review-until-clean"
    assert record.latest_verdict == "clean"
    assert record.stop_reason == "clean"
    assert record.active_role == ""
    assert [item["to"] for item in record.timeline] == ["developer", "reviewer"]
    assert {node["id"] for node in record.graph_nodes} == {"developer", "reviewer"}
    assert next(node for node in record.graph_nodes if node["id"] == "reviewer")["status"] == "verified"
    assert {run["parent_task_id"] for run in runner.calls} == {"workflow-1"}
    assert record.workflow_metrics == {
        "laps": 1,
        "repair_laps": 0,
        "verified_completion": True,
        "manual_interventions": 0,
        "cost_usd": 0.1,
        "duration_ms": result.duration_ms,
        "files_touched": 1,
        "stop_reason": "clean",
    }


def test_cooperative_cancel_stops_before_next_developer_turn(tmp_path) -> None:
    class _CancelAfterVerdictTracker(RunTracker):
        def workflow_update(self, task_id, **kwargs):
            super().workflow_update(task_id, **kwargs)
            if kwargs.get("latest_verdict") == "blocking":
                self.request_cancel(task_id)

    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    tracker = _CancelAfterVerdictTracker(str(tmp_path / ".voly" / "runs"))
    runner = _FakeRunner([_run_result()])
    gateway = _FakeGateway([{
        "content": '{"verdict":"blocking","findings":["fix it"]}',
    }])

    result = ReviewUntilClean(runner=runner, gateway=gateway).run(
        "fix", cwd=str(tmp_path), max_rounds=3,
        reviewer_model="m", reviewer_provider="p",
        tracker=tracker, workflow_id="workflow-cancel",
    )

    assert result.stop_reason is ReviewStopReason.CANCELLED
    assert len(runner.calls) == 1
    assert tracker.load("workflow-cancel").stop_reason == "cancelled"
    assert tracker.load("workflow-cancel").workflow_metrics["manual_interventions"] == 1
