from __future__ import annotations

import pytest

from voly.decisions import DecisionConflictError, DecisionService
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
    from types import SimpleNamespace
    from voly.config import VOLYConfig
    from voly.executor.base import ExecutorResult
    from voly.evidence.store import EvidenceStore

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
