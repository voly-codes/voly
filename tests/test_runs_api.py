"""/api/runs — in-flight run visibility (RunTracker heartbeats in the web)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from voly.config import RTKConfig, TelemetryConfig, VOLYConfig
from voly.executor.base import ExecutorResult
from voly.runtime.runs import RunTracker
from voly.web.server import create_app


@pytest.fixture()
def voly_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".voly"
    (d / "events").mkdir(parents=True)
    return d


@pytest.fixture()
def client(voly_dir: Path) -> TestClient:
    app = create_app(config=VOLYConfig(), events_dir=voly_dir / "events")
    return TestClient(app)


def test_list_runs_empty(client: TestClient) -> None:
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == {"runs": [], "active": 0}


def test_list_and_get_run(client: TestClient, voly_dir: Path) -> None:
    tracker = RunTracker(str(voly_dir / "runs"))
    tracker.start("run-1", "fix the bug", ["claude-code"])
    tracker.heartbeat("run-1", "claude-code", 0)
    tracker.start("run-2", "old finished run", ["zen"])
    tracker.finish("run-2", status="completed")

    data = client.get("/api/runs").json()
    assert data["active"] == 1
    assert {r["task_id"] for r in data["runs"]} == {"run-1", "run-2"}

    active = client.get("/api/runs?active=1").json()
    assert [r["task_id"] for r in active["runs"]] == ["run-1"]
    rec = active["runs"][0]
    assert rec["status"] == "running"
    assert rec["current_role"] == "claude-code"
    assert "elapsed_seconds" in rec and "age_seconds" in rec

    one = client.get("/api/runs/run-1")
    assert one.status_code == 200
    assert one.json()["task"] == "fix the bug"
    assert client.get("/api/runs/nope").status_code == 404


def test_list_runs_groups_children_under_one_root(client: TestClient, voly_dir: Path) -> None:
    tracker = RunTracker(str(voly_dir / "runs"))
    tracker.start("root", "shared flow", ["developer", "reviewer"])
    tracker.start(
        "child", "developer call", ["claude-code"], parent_task_id="root",
    )
    tracker.graph_update(
        "root",
        node={"id": "developer", "role": "developer", "status": "running"},
    )

    roots = client.get("/api/runs?active=1").json()
    assert [record["task_id"] for record in roots["runs"]] == ["root"]
    assert roots["runs"][0]["graph_nodes"][0]["status"] == "running"

    all_records = client.get("/api/runs?active=1&include_children=1").json()
    assert {record["task_id"] for record in all_records["runs"]} == {"root", "child"}
    assert client.get("/api/runs/child").json()["parent_task_id"] == "root"


def test_cancel_active_run_is_cooperative(client: TestClient, voly_dir: Path) -> None:
    tracker = RunTracker(str(voly_dir / "runs"))
    tracker.start("workflow-1", "fix", ["developer", "reviewer"])
    tracker.workflow_update(
        "workflow-1", workflow="review-until-clean", lap=1,
        active_role="reviewer",
    )

    response = client.post("/api/runs/workflow-1/cancel")

    assert response.status_code == 200
    assert response.json()["cancel_requested"] is True
    assert response.json()["interrupts_active_subprocess"] is False
    assert tracker.load("workflow-1").cancel_requested is True
    tracker.finish("workflow-1")
    assert client.post("/api/runs/workflow-1/cancel").status_code == 409


def test_review_workflow_uses_explicit_api_route(client: TestClient, monkeypatch) -> None:
    from voly.web.routes import run as run_route

    captured = {}

    def _fake(req, config, runs_dir):
        captured.update({"workflow": req.workflow, "runs_dir": runs_dir})
        return {
            "success": True,
            "workflow": "review-until-clean",
            "task_id": "wf-1",
            "stop_reason": "clean",
            "laps": [],
        }

    monkeypatch.setattr(run_route, "_review_workflow_run", _fake)
    response = client.post("/api/run", json={
        "task": "fix app",
        "cwd": ".",
        "workflow": "review-until-clean",
        "max_rounds": 2,
    })

    assert response.status_code == 200
    assert '"workflow": "review-until-clean"' in response.text
    assert '"stop_reason": "clean"' in response.text
    assert captured["workflow"] == "review-until-clean"


def test_agent_runner_writes_run_record(tmp_path: Path, monkeypatch) -> None:
    """Executor runs (incl. CLI-launched) leave a RunRecord: start → finish."""
    from voly.runner import agent_runner as runner_mod
    from voly.runner.agent_runner import AgentRunner

    runs_dir = tmp_path / "runs"

    def _fake_build(name, model=None):
        class _E:
            def run(self, task, *, cwd, max_turns=30, timeout=300, **kw):
                # mid-run the record must already exist and be running
                recs = RunTracker(str(runs_dir)).list()
                assert recs and recs[0].status == "running"
                assert recs[0].current_role == "claude-code"
                return ExecutorResult(success=True, output="done")
        return _E()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *a, **k: None)

    cfg = VOLYConfig(
        rtk=RTKConfig(enabled=False),
        telemetry=TelemetryConfig(runs_dir=str(runs_dir)),
    )
    out = AgentRunner(cfg).run(
        "demo task", "claude-code", cwd=str(tmp_path), emit_event=False,
        parent_task_id="parent-1",
    )
    assert out.success is True

    recs = RunTracker(str(runs_dir)).list()
    assert len(recs) == 1
    assert recs[0].status == "completed"
    assert recs[0].task == "demo task"
    assert recs[0].parent_task_id == "parent-1"


def test_agent_runner_run_record_marks_failure(tmp_path: Path, monkeypatch) -> None:
    from voly.runner import agent_runner as runner_mod
    from voly.runner.agent_runner import AgentRunner

    runs_dir = tmp_path / "runs"

    def _fake_build(name, model=None):
        class _E:
            def run(self, task, *, cwd, max_turns=30, timeout=300, **kw):
                return ExecutorResult(success=False, error="boom")
        return _E()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *a, **k: None)

    cfg = VOLYConfig(
        rtk=RTKConfig(enabled=False),
        telemetry=TelemetryConfig(runs_dir=str(runs_dir)),
    )
    AgentRunner(cfg).run("t", "zen", cwd=str(tmp_path), emit_event=False)
    recs = RunTracker(str(runs_dir)).list()
    assert recs[0].status == "failed"
    assert "boom" in recs[0].error
