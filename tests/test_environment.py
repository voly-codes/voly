"""Environment readiness report (keys, PATH, cwd, cloud)."""

from __future__ import annotations

from pathlib import Path

import pytest

from voly.environment import collect_environment_report


def test_report_ready_with_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = collect_environment_report(None)
    assert report.ready is True
    assert "anthropic" in report.providers_configured
    assert report.executors["pipeline"]["available"] is True


def test_report_not_ready_without_keys_or_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENCODE_API_KEY",
        "MIMO_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CURSOR_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    # Force no CLI binaries
    monkeypatch.setattr("voly.environment.shutil.which", lambda _name: None)
    monkeypatch.setattr("voly.environment._local_cli_candidates", lambda _name: [])

    report = collect_environment_report(None)
    assert report.ready is False
    assert any(c.id == "providers" and c.status == "error" for c in report.checks)


def test_cwd_git_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    (tmp_path / ".git").mkdir()
    report = collect_environment_report(None, cwd=str(tmp_path))
    cwd_check = next(c for c in report.checks if c.id == "cwd")
    assert cwd_check.status == "ok"


def test_cwd_missing_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    report = collect_environment_report(None, cwd="/no/such/path/voly-env-test")
    cwd_check = next(c for c in report.checks if c.id == "cwd")
    assert cwd_check.status == "error"


def test_executor_claude_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def fake_which(name: str):
        if name == "claude":
            return "/usr/bin/claude"
        return None

    monkeypatch.setattr("voly.environment.shutil.which", fake_which)
    report = collect_environment_report(None)
    assert report.executors["claude-code"]["available"] is True
    assert report.executors["opencode"]["available"] is False


def test_executor_wrangler_detects_local_windows_npm_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr("voly.environment.shutil.which", lambda _name: None)
    wrapper = tmp_path / "wrangler.cmd"
    wrapper.write_text("@echo off\n", encoding="utf-8")

    def fake_candidates(name: str):
        return [wrapper] if name == "wrangler" else []

    monkeypatch.setattr("voly.environment._local_cli_candidates", fake_candidates)
    report = collect_environment_report(None)

    assert report.executors["wrangler"]["available"] is True
    assert report.executors["wrangler"]["path"] == str(wrapper.resolve())


def test_windows_command_names_include_npm_cmd_wrapper(
) -> None:
    from voly.environment import _command_names

    assert "wrangler.cmd" in _command_names("wrangler", windows=True)


def test_api_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from voly.config import VOLYConfig
    from voly.web.server import create_app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    ev = tmp_path / "events"
    ev.mkdir()
    app = create_app(events_dir=ev, config=VOLYConfig())
    client = TestClient(app)
    r = client.get("/api/environment")
    assert r.status_code == 200
    body = r.json()
    assert "ready" in body
    assert "checks" in body
    assert "executors" in body
    assert body["ready"] is True

    r2 = client.get("/api/environment", params={"cwd": str(tmp_path)})
    assert r2.status_code == 200
    assert any(c["id"] == "cwd" for c in r2.json()["checks"])
