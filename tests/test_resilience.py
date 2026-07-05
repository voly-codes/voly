"""Rung A resilience: run heartbeat tracking + watchdog (Этап 2)."""

from __future__ import annotations

import time

import pytest

from voly.runtime.runs import COMPLETED, RUNNING, STALE, RunTracker, Watchdog


@pytest.fixture()
def runs_dir(tmp_path):
    return str(tmp_path / "runs")


def test_start_writes_running_record(runs_dir):
    t = RunTracker(runs_dir)
    rec = t.start("task-1", "build auth", ["architect", "developer", "tester"])
    assert rec.status == RUNNING
    assert rec.total_roles == 3
    assert rec.done_roles == 0
    assert rec.current_role == "architect"
    loaded = t.load("task-1")
    assert loaded is not None and loaded.status == RUNNING


def test_heartbeat_advances_progress(runs_dir):
    t = RunTracker(runs_dir)
    t.start("task-2", "x", ["a", "b"])
    t.heartbeat("task-2", "a", 1)
    rec = t.load("task-2")
    assert rec.done_roles == 1
    assert rec.current_role == "a"


def test_finish_marks_completed_and_fills_progress(runs_dir):
    t = RunTracker(runs_dir)
    t.start("task-3", "x", ["a", "b"])
    t.finish("task-3", status=COMPLETED)
    rec = t.load("task-3")
    assert rec.status == COMPLETED
    assert rec.done_roles == rec.total_roles
    assert rec.current_role == ""


def test_list_sorted_newest_first(runs_dir):
    t = RunTracker(runs_dir)
    t.start("old", "x", ["a"])
    time.sleep(0.01)
    t.start("new", "x", ["a"])
    ids = [r.task_id for r in t.list()]
    assert ids[:2] == ["new", "old"]


# ── Watchdog ──────────────────────────────────────────────────────────────
def test_watchdog_flags_stale_running_run(runs_dir):
    t = RunTracker(runs_dir)
    rec = t.start("hung", "x", ["a", "b"])
    # Backdate the heartbeat beyond the stale threshold.
    rec.heartbeat_at = time.time() - 1000
    t._write(rec)
    wd = Watchdog(runs_dir, task_timeout=10.0, stale_factor=2.0)  # stale after 20s
    stale = wd.scan()
    assert [r.task_id for r in stale] == ["hung"]


def test_watchdog_ignores_fresh_and_finished(runs_dir):
    t = RunTracker(runs_dir)
    t.start("fresh", "x", ["a"])  # just started → fresh heartbeat
    t.start("done", "x", ["a"])
    t.finish("done", status=COMPLETED)
    wd = Watchdog(runs_dir, task_timeout=10.0, stale_factor=2.0)
    assert wd.scan() == []


def test_reap_marks_stale(runs_dir):
    t = RunTracker(runs_dir)
    rec = t.start("hung", "x", ["a"])
    rec.heartbeat_at = time.time() - 1000
    t._write(rec)
    wd = Watchdog(runs_dir, task_timeout=10.0, stale_factor=2.0)
    reaped = wd.reap()
    assert len(reaped) == 1
    assert t.load("hung").status == STALE
    # After reaping it is no longer "running", so a second scan is clean.
    assert wd.scan() == []


def test_tracking_is_best_effort_on_bad_dir(tmp_path):
    # Point at a path that cannot be a directory (a file) → writes must not raise.
    bad = tmp_path / "afile"
    bad.write_text("x")
    t = RunTracker(str(bad))
    t.start("t", "x", ["a"])  # should swallow OSError
    assert t.load("t") is None


# ── Integration with run_local ──────────────────────────────────────────────
def test_run_local_writes_and_finishes_record(runs_dir):
    from voly.a2a.multiagent import Assignment, run_local

    class FakeGateway:
        def chat(self, *a, **k):
            return {"content": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}

    assignments = [
        Assignment(idx=0, role="architect", description="design", tier="premium",
                   model="m", provider="p", skills=[], depends_on=[]),
        Assignment(idx=1, role="developer", description="build", tier="standard",
                   model="m", provider="p", skills=[], depends_on=[0]),
    ]
    tracker = RunTracker(runs_dir)
    run_local(
        "build a thing", assignments, FakeGateway(),
        task_id="run-int", tracker=tracker,
    )
    rec = tracker.load("run-int")
    assert rec is not None
    assert rec.status == COMPLETED
    assert rec.total_roles == 2
    assert rec.done_roles == 2
