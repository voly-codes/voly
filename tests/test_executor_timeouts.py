"""Timeout semantics for subprocess executors (этап 1: таймауты CLI-обёрток).

The caller's ``timeout`` is a TOTAL deadline: internal model-fallback loops in
zen/opencode share it across attempts instead of granting each model the full
budget (8 models × 300s would silently turn a "300s" call into ~40 min).
"""

from __future__ import annotations

import subprocess

from click.testing import CliRunner

from voly.cli.main import main
from voly.executor.base import ExecutorResult, executor_failure_details, format_executor_failure
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


def test_executor_failure_details_structured_payload():
    result = ExecutorResult(success=False, error="invalid authentication credentials")
    details = executor_failure_details(result, executor_name="claude-code")
    assert details["error"] == "invalid authentication credentials"
    assert details["error_message"].startswith("Authentication failed:")
    assert details["error_class"] in {"unrecognized", "oauth_invalid_token"}
    assert details["error_hint"]


def test_format_executor_failure_returns_human_readable_message():
    result = ExecutorResult(success=False, error="invalid authentication credentials")
    message = format_executor_failure(result)
    assert "authentication" in message.lower()
    assert "invalid authentication credentials" in message


def test_format_executor_failure_includes_next_step_hint():
    result = ExecutorResult(success=False, error="[WinError 10038] not a socket")
    message = format_executor_failure(result, executor_name="cursor")
    assert "Cursor connection failed" in message
    assert "Hint:" in message
    assert "Cursor IDE" in message


def test_run_cmd_passes_model_to_executor(monkeypatch, tmp_path):
    from voly.runner import agent_runner as runner_mod

    captured: dict[str, str] = {}

    class _FakeExecutor:
        def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
            return ExecutorResult(success=True, output="ok")

    def _fake_build(name, model=None):
        captured["model"] = model or ""
        return _FakeExecutor()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *args, **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run", "do it",
            "--executor", "opencode",
            "--model", "mimo-v2.5-free",
            "--cwd", str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["model"] == "mimo-v2.5-free"


def test_runner_cmd_passes_model_to_executor(monkeypatch, tmp_path):
    from voly.runner import agent_runner as runner_mod

    captured: dict[str, str] = {}

    class _FakeExecutor:
        def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
            return ExecutorResult(success=True, output="ok")

    def _fake_build(name, model=None):
        captured["model"] = model or ""
        return _FakeExecutor()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *args, **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "runner", "opencode", "do it",
            "--model", "mimo-v2.5-free",
            "--cwd", str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["model"] == "mimo-v2.5-free"


def test_opencode_default_model_is_mimo():
    ex = OpenCodeExecutor()
    assert ex._model == "mimo-v2.5-free"


def test_cli_runner_displays_human_readable_executor_error(monkeypatch, tmp_path):
    from voly.runner import agent_runner as runner_mod

    class _FakeExecutor:
        def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
            return ExecutorResult(success=False, error="invalid authentication credentials")

    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: _FakeExecutor())
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *args, **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(main, ["runner", "claude-code", "do it", "--cwd", str(tmp_path)])

    assert result.exit_code == 1
    assert "Authentication failed" in result.output
    assert "invalid authentication credentials" in result.output
    assert "Hint:" in result.output
