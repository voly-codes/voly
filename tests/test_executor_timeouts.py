"""Timeout semantics for subprocess executors (этап 1: таймауты CLI-обёрток).

The caller's ``timeout`` is a TOTAL deadline: internal model-fallback loops in
zen/opencode share it across attempts instead of granting each model the full
budget (8 models × 300s would silently turn a "300s" call into ~40 min).
"""

from __future__ import annotations

import subprocess

from voly.executor.base import ExecutorResult
from voly.executor.opencode import OpenCodeExecutor
from voly.executor.zen import ZenExecutor
import voly.executor.claude_code as cc_mod
import voly.executor.opencode as oc_mod
import voly.executor.zen as zen_mod


class _FakeClock:
    """Deterministic stand-in for the `time` module (monotonic only)."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t


def _billing_failure() -> ExecutorResult:
    return ExecutorResult(success=False, error="insufficient credits", billing_error=True)


# ─── zen: timeout is a total deadline across the model loop ──────────────────
def test_zen_timeout_is_total_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(zen_mod, "time", clock)
    ex = ZenExecutor()
    attempt_timeouts: list[int] = []

    def fake_one(task, model_id, cwd=None, max_turns=20, timeout=600):
        attempt_timeouts.append(timeout)
        clock.t += 100.0  # each attempt consumes 100s
        return _billing_failure()

    monkeypatch.setattr(ex, "_run_cli_one", fake_one)
    result = ex._run_cli("do it", timeout=250)

    # 250s budget, 100s per attempt → 3 attempts with shrinking remaining time,
    # NOT all 9 models × 250s each.
    assert attempt_timeouts == [250, 150, 50]
    assert result.billing_error is True  # chain can still continue past zen
    assert result.metadata.get("deadline_exhausted") is True


def test_zen_deadline_too_short_for_any_attempt(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(zen_mod, "time", clock)
    ex = ZenExecutor()
    monkeypatch.setattr(
        ex, "_run_cli_one",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch a subprocess")),
    )
    result = ex._run_cli("do it", timeout=5)  # below the 10s attempt floor
    assert result.success is False
    assert result.metadata.get("timeout") is True


def test_zen_success_stops_iteration_within_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(zen_mod, "time", clock)
    ex = ZenExecutor()
    calls: list[str] = []

    def fake_one(task, model_id, cwd=None, max_turns=20, timeout=600):
        calls.append(model_id)
        clock.t += 30.0
        if len(calls) == 2:
            return ExecutorResult(success=True, output="done")
        return _billing_failure()

    monkeypatch.setattr(ex, "_run_cli_one", fake_one)
    result = ex._run_cli("do it", timeout=300)
    assert result.success is True
    assert len(calls) == 2


# ─── opencode: same deadline semantics ───────────────────────────────────────
def test_opencode_timeout_is_total_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(oc_mod, "time", clock)
    ex = OpenCodeExecutor()
    attempt_timeouts: list[int] = []

    def fake_one(task, model_id, cwd=None, timeout=600):
        attempt_timeouts.append(timeout)
        clock.t += 150.0
        return _billing_failure()

    monkeypatch.setattr(ex, "_run_cli_one", fake_one)
    result = ex._run_cli("do it", timeout=300)

    assert attempt_timeouts == [300, 150]
    assert result.billing_error is True
    assert result.metadata.get("deadline_exhausted") is True


# ─── claude-code: TimeoutExpired is marked for telemetry/watchdog ────────────
def test_claude_code_timeout_sets_marker(monkeypatch):
    ex = cc_mod.ClaudeCodeExecutor(claude_bin="claude")

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr(cc_mod.subprocess, "run", fake_run)
    result = ex.run("task", timeout=5)
    assert result.success is False
    assert "Timeout after 5s" in result.error
    assert result.metadata.get("timeout") is True
