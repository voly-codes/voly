"""Phase 5 (docs/proposals/agent-workflow-sdk.md): /api/workflows REST surface.

Every endpoint delegates to voly.sdk.loader / voly.plan.runner / voly.plan.store
/ voly.plan.approval — these tests check the HTTP contract (status codes,
SSE event shape, persisted-Plan visibility), not a second implementation of
any of those. _POLL_INTERVAL_SECONDS is patched down so SSE tests don't pay
the real 1s poll cadence.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from voly.config import VOLYConfig
from voly.web import routes as _routes_pkg  # noqa: F401  (ensures package import works)
from voly.web.routes import workflows as workflows_module
from voly.web.server import create_app


def _config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    monkeypatch.setattr(workflows_module, "_POLL_INTERVAL_SECONDS", 0.01)


_DOC = {
    "name": "research-review",
    "task": "Compare two markets",
    "nodes": [
        {"id": "research", "agent": {"name": "researcher"}},
        {"id": "review", "agent": {"name": "reviewer"}, "depends_on": ["research"]},
    ],
}


def _chat_ok(self, **kwargs):
    return {"content": f"ok:{kwargs.get('agent')}", "model": "x", "usage": {}}


def _sse_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def test_validate_ok(tmp_path) -> None:
    client = TestClient(create_app(config=_config(tmp_path)))
    resp = client.post("/api/workflows/validate", json=_DOC)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "name": "research-review", "node_ids": ["research", "review"]}


def test_validate_rejects_cycle(tmp_path) -> None:
    doc = {
        "name": "bad",
        "nodes": [
            {"id": "a", "agent": {"name": "x"}, "depends_on": ["b"]},
            {"id": "b", "agent": {"name": "y"}, "depends_on": ["a"]},
        ],
    }
    client = TestClient(create_app(config=_config(tmp_path)))
    resp = client.post("/api/workflows/validate", json=doc)
    assert resp.status_code == 400
    assert "cycle" in resp.json()["detail"]


def test_run_streams_node_events_then_done(tmp_path) -> None:
    config = _config(tmp_path)
    client = TestClient(create_app(config=config))

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        with client.stream("POST", "/api/workflows/run", json=_DOC) as resp:
            assert resp.status_code == 200
            events = _sse_events(resp)

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert types[-1] == "done"
    assert "node" in types
    node_events = [e for e in events if e["type"] == "node"]
    assert {e["node_id"] for e in node_events} == {"research", "review"}
    assert any(e["event"] == "completed" for e in node_events if e["node_id"] == "review")
    done = events[-1]
    assert done["success"] is True
    assert done["status"] == "completed"


def test_get_and_list_after_run(tmp_path) -> None:
    config = _config(tmp_path)
    client = TestClient(create_app(config=config))

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        with client.stream("POST", "/api/workflows/run", json=_DOC) as resp:
            events = _sse_events(resp)
    plan_id = events[0]["plan_id"]

    listing = client.get("/api/workflows").json()["workflows"]
    assert any(w["plan_id"] == plan_id for w in listing)

    got = client.get(f"/api/workflows/{plan_id}")
    assert got.status_code == 200
    assert got.json()["plan_id"] == plan_id

    assert client.get("/api/workflows/no-such-plan").status_code == 404


def test_approval_pause_decide_and_resume(tmp_path) -> None:
    config = _config(tmp_path)
    client = TestClient(create_app(config=config))
    doc = {
        "name": "gated",
        "nodes": [
            {"id": "decide", "agent": {"name": "manager"}, "approval": True},
            {"id": "notify", "agent": {"name": "notifier"}, "depends_on": ["decide"]},
        ],
    }

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        with client.stream("POST", "/api/workflows/run", json=doc) as resp:
            events = _sse_events(resp)
    plan_id = events[0]["plan_id"]
    done = events[-1]
    assert done["success"] is False
    assert done["status"] == "running"  # paused, not failed

    not_a_review_node = client.post(
        f"/api/workflows/{plan_id}/nodes/notify/decide", json={"decision": "approve"},
    )
    assert not_a_review_node.status_code == 400  # "notify" has no human_review check

    unknown_node = client.post(
        f"/api/workflows/{plan_id}/nodes/nonexistent/decide", json={"decision": "approve"},
    )
    assert unknown_node.status_code == 404

    approve = client.post(
        f"/api/workflows/{plan_id}/nodes/decide/decide", json={"decision": "approve"},
    )
    assert approve.status_code == 200
    assert approve.json()["decision"] == "approved"

    # Idempotent re-approval: changed=False, still 200.
    again = client.post(
        f"/api/workflows/{plan_id}/nodes/decide/decide", json={"decision": "approve"},
    )
    assert again.status_code == 200
    assert again.json()["changed"] is False

    # Conflicting decision after approval: 409.
    conflict = client.post(
        f"/api/workflows/{plan_id}/nodes/decide/decide", json={"decision": "reject"},
    )
    assert conflict.status_code == 409

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        with client.stream("POST", f"/api/workflows/{plan_id}/resume", json={}) as resp:
            resume_events = _sse_events(resp)

    resume_done = resume_events[-1]
    assert resume_done["success"] is True
    assert resume_done["status"] == "completed"


def test_decide_unknown_plan_is_404(tmp_path) -> None:
    client = TestClient(create_app(config=_config(tmp_path)))
    resp = client.post(
        "/api/workflows/no-such-plan/nodes/x/decide", json={"decision": "approve"},
    )
    assert resp.status_code == 404


def test_resume_unknown_plan_is_404(tmp_path) -> None:
    client = TestClient(create_app(config=_config(tmp_path)))
    resp = client.post("/api/workflows/no-such-plan/resume", json={})
    assert resp.status_code == 404
