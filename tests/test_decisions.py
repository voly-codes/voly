from __future__ import annotations

import pytest

from voly.decisions import DecisionConflictError, DecisionService, _build_business_executor
from voly.plan.store import PlanStore
from voly.sensing.schema import Option, Signal


def _signal() -> Signal:
    return Signal("rss-1", "rss", "https://example.com#1", "2026-08-29T10:00:00Z", "sha256:1", {"title": "Price cut"}, 0.8)


def _option() -> Option:
    return Option("opt-1", "rss-1", "Review pricing", "Competitor cut prices", "high", "Retention", "business")


def test_decision_approval_unblocks_action_and_is_idempotent(tmp_path) -> None:
    service = DecisionService(PlanStore(str(tmp_path / "plans")))
    plan = service.create(_signal(), _option())
    assert plan.get_step("approve-option").status == "verifying"
    assert not service.engine.can_start(plan, "execute-action")

    approved = service.decide(plan.plan_id, "approve", comment="Proceed")
    assert approved.changed is True
    assert approved.plan.metadata["decision"] == "approved"
    assert service.engine.can_start(approved.plan, "execute-action")
    assert service.decide(plan.plan_id, "approve").changed is False
    with pytest.raises(DecisionConflictError):
        service.decide(plan.plan_id, "reject")


def test_decision_rejection_keeps_action_blocked(tmp_path) -> None:
    service = DecisionService(PlanStore(str(tmp_path / "plans")))
    plan = service.create(_signal(), _option())
    rejected = service.decide(plan.plan_id, "reject")
    assert rejected.plan.get_step("approve-option").status == "failed"
    assert rejected.plan.get_step("execute-action").status == "pending"
    assert rejected.plan.status == "failed"
    assert not service.engine.can_start(rejected.plan, "execute-action")


def test_plan_metadata_round_trip(tmp_path) -> None:
    store = PlanStore(str(tmp_path / "plans"))
    plan = DecisionService(store).create(_signal(), _option())
    assert store.load(plan.plan_id).metadata["signal_id"] == "rss-1"


def test_decision_api_approve_and_conflict(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from voly.config import VOLYConfig
    from voly.web.server import create_app

    config = VOLYConfig()
    config.plan.store_dir = str(tmp_path / "plans")
    DecisionService(PlanStore(config.plan.store_dir)).create(_signal(), _option())
    client = TestClient(create_app(config=config))

    assert client.get("/api/decisions").json()["decisions"][0]["plan_id"] == "opt-1"
    approved = client.post("/api/decisions/opt-1/feedback", json={"decision": "approve"})
    assert approved.status_code == 200
    assert approved.json()["plan"]["metadata"]["decision"] == "approved"
    assert client.post("/api/decisions/opt-1/feedback", json={"decision": "reject"}).status_code == 409


def test_approved_action_executes_once_and_writes_evidence(tmp_path) -> None:
    from voly.config import VOLYConfig
    from voly.evidence.store import EvidenceStore
    from voly.executor.base import ExecutorResult

    config = VOLYConfig()
    config.evidence.store_dir = str(tmp_path / "evidence")
    service = DecisionService(PlanStore(str(tmp_path / "plans")), config=config)
    option = Option(
        "opt-action", "rss-1", "Update deal", "Approved change", "high", "Revenue", "business",
        {"kind": "http_call", "method": "PATCH", "url": "https://api.example.com/deal/1", "body": {}, "idempotency_key": "opt-action"},
    )
    service.create(_signal(), option)
    service.decide("opt-action", "approve")
    calls = []

    class FakeExecutor:
        def run(self, task):
            calls.append(task)
            return ExecutorResult(True, metadata={"action_report": {"action_kind": "http_call", "target": "https://api.example.com/deal/1", "result": "HTTP 200"}})

    completed = service.execute("opt-action", executor=FakeExecutor())
    assert completed.metadata["execution"] == "completed"
    assert completed.get_step("execute-action").status == "verified"
    assert len(calls) == 1
    service.execute("opt-action", executor=FakeExecutor())
    assert len(calls) == 1
    evidence = EvidenceStore(config.evidence.store_dir).load("opt-action")
    assert evidence.action_report["result"] == "HTTP 200"


def test_decision_and_execution_feed_enabled_learning_store(tmp_path) -> None:
    from voly.config import VOLYConfig
    from voly.executor.base import ExecutorResult
    from voly.learning import InstinctLifecycle, InstinctStore

    config = VOLYConfig()
    config.learning.enabled = True
    config.learning.store_path = str(tmp_path / "learning" / "instincts.json")
    service = DecisionService(PlanStore(str(tmp_path / "plans")), config=config)
    option = Option(
        "opt-learning", "rss-1", "Update deal", "Approved change", "high", "Revenue", "business",
        {"kind": "notify", "url": "https://hooks.example.com/business", "body": {}},
    )
    service.create(_signal(), option)
    service.decide(option.option_id, "approve")

    class FakeExecutor:
        def run(self, task):
            return ExecutorResult(True, metadata={"action_report": {"result": "HTTP 200"}})

    service.execute(option.option_id, executor=FakeExecutor())

    instincts = InstinctStore(config.learning.store_path).list()
    assert len(instincts) == 1
    assert [item.kind for item in instincts[0].evidence] == ["user_accepted", "verified_outcome"]
    assert instincts[0].lifecycle is InstinctLifecycle.CANDIDATE


def test_business_execution_emits_local_task_event_v4(tmp_path) -> None:
    import json

    from voly.config import VOLYConfig
    from voly.executor.base import ExecutorResult

    config = VOLYConfig()
    config.telemetry.events_dir = str(tmp_path / "events")
    config.telemetry.pipeline_enabled = False
    config.telemetry.r2_enabled = False
    service = DecisionService(PlanStore(str(tmp_path / "plans")), config=config)
    option = Option(
        "opt-event", "rss-1", "Notify sales", "Market changed", "high", "Revenue", "business",
        {"kind": "notify", "url": "https://hooks.example.com/business", "body": {}},
    )
    service.create(_signal(), option)
    service.decide(option.option_id, "approve")

    class FakeExecutor:
        def run(self, task):
            return ExecutorResult(True, metadata={"action_report": {"result": "HTTP 200"}})

    service.execute(option.option_id, executor=FakeExecutor())

    event = json.loads((tmp_path / "events" / "opt-event.json").read_text(encoding="utf-8"))
    assert event["schema_version"] == 4
    assert event["task_type"] == "business_decision"
    assert event["signal"] == {
        "signal_id": "rss-1",
        "source": "rss",
        "captured_at": "2026-08-29T10:00:00Z",
        "confidence": 0.8,
    }
    assert event["business_plan"]["decision"] == "approved"
    assert event["business_plan"]["execution"] == "completed"
    assert event["business_plan"]["executed_at"] is not None


def test_business_executor_selection_uses_capability_matcher_when_enabled(tmp_path) -> None:
    from voly.config import VOLYConfig
    from voly.executor.http_action import HttpActionExecutor
    from voly.executor.notify import NotifyExecutor

    config = VOLYConfig()
    config.capability.enabled = True
    config.capability.profiles_dir = str(tmp_path / "capability" / "profiles")

    assert isinstance(_build_business_executor("http_call", config), HttpActionExecutor)
    assert isinstance(_build_business_executor("notify", config), NotifyExecutor)


def test_business_executor_selection_ignores_off_kind_capability_match(tmp_path, monkeypatch) -> None:
    """A remote/local match outside the action-kind candidate set must not be honored."""
    from voly.capability.schema import ExecutorCapabilityProfile
    from voly.config import VOLYConfig
    from voly.executor.http_action import HttpActionExecutor

    class _FakeResult:
        recommended = ExecutorCapabilityProfile.unknown("some-other-executor")

    def _fake_find_executors(self, req):
        return _FakeResult()

    monkeypatch.setattr(
        "voly.capability.matcher.ExecutorMatcher.find_executors", _fake_find_executors
    )
    config = VOLYConfig()
    config.capability.enabled = True
    config.capability.profiles_dir = str(tmp_path / "capability" / "profiles")

    assert isinstance(_build_business_executor("http_call", config), HttpActionExecutor)


def test_business_executor_selection_falls_back_when_capability_disabled() -> None:
    from voly.config import VOLYConfig
    from voly.executor.http_action import HttpActionExecutor

    config = VOLYConfig()
    assert config.capability.enabled is False
    assert isinstance(_build_business_executor("http_call", config), HttpActionExecutor)


def test_business_executor_selection_rejects_unknown_action_kind() -> None:
    from voly.config import VOLYConfig

    with pytest.raises(ValueError):
        _build_business_executor("carrier_pigeon", VOLYConfig())


def test_rejected_business_decision_emits_terminal_event(tmp_path) -> None:
    import json

    from voly.config import VOLYConfig

    config = VOLYConfig()
    config.telemetry.events_dir = str(tmp_path / "events")
    config.telemetry.pipeline_enabled = False
    config.telemetry.r2_enabled = False
    service = DecisionService(PlanStore(str(tmp_path / "plans")), config=config)
    service.create(_signal(), _option())

    service.decide("opt-1", "reject")

    event = json.loads((tmp_path / "events" / "opt-1.json").read_text(encoding="utf-8"))
    assert event["status"] == "completed"
    assert event["agent"] == "human-reviewer"
    assert event["business_plan"]["decision"] == "rejected"
    assert event["business_plan"]["execution"] == "pending"
