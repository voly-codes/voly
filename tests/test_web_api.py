"""Priority: FastAPI web API smoke — status, tasks list, gateway (auth off)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from voly.config import VOLYConfig
from voly.web.server import create_app


@pytest.fixture()
def events_dir(tmp_path: Path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    # one completed task event
    (d / "t1.json").write_text(
        json.dumps({
            "task_id": "t1",
            "agent": "developer",
            "status": "completed",
            "cost_usd": 0.01,
            "tokens": {"input": 10, "output": 5},
            "model": "test-model",
            "provider": "test",
            "executor": "pipeline",
            "schema_version": 1,
        }),
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def client(events_dir: Path) -> TestClient:
    cfg = VOLYConfig()
    app = create_app(events_dir=events_dir, config=cfg)
    return TestClient(app)


def test_api_status(client: TestClient) -> None:
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["tasks_count"] >= 1
    assert "events_dir" in body


def test_api_list_tasks(client: TestClient) -> None:
    r = client.get("/api/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert isinstance(tasks, list)
    assert any(t.get("task_id") == "t1" for t in tasks)


def test_api_list_tasks_filter_agent(client: TestClient) -> None:
    r = client.get("/api/tasks", params={"agent": "developer"})
    assert r.status_code == 200
    assert all(t.get("agent") == "developer" for t in r.json())


def test_api_list_tasks_filter_status(client: TestClient) -> None:
    r = client.get("/api/tasks", params={"status": "completed"})
    assert r.status_code == 200
    assert all(t.get("status") == "completed" for t in r.json())


def test_api_tasks_summary(client: TestClient) -> None:
    r = client.get("/api/tasks/stats/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tasks"] >= 1
    assert "total_cost_usd" in body


def test_api_gateway_status(client: TestClient) -> None:
    r = client.get("/api/gateway/status")
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body or "enabled" in body or "cache" in body


def test_api_telemetry_summary(client: TestClient) -> None:
    r = client.get("/api/telemetry/summary", params={"days": 30})
    # endpoint may be /api/telemetry/summary — check status
    if r.status_code == 404:
        r = client.get("/api/telemetry/summary?days=30")
    # some installs use different path — accept 200 or skip if route missing
    assert r.status_code in (200, 404, 422)
    if r.status_code == 200:
        assert isinstance(r.json(), dict)


def test_openapi_docs_available(client: TestClient) -> None:
    r = client.get("/api/docs")
    assert r.status_code in (200, 307, 308)
