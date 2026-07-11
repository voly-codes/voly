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
    out = AgentRunner(cfg).run("demo task", "claude-code", cwd=str(tmp_path), emit_event=False)
    assert out.success is True

    recs = RunTracker(str(runs_dir)).list()
    assert len(recs) == 1
    assert recs[0].status == "completed"
    assert recs[0].task == "demo task"


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
