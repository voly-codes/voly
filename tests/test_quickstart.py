from __future__ import annotations

import importlib
import json
from pathlib import Path

from click.testing import CliRunner

from voly.cli.commands.quickstart import quickstart
from voly.cli.main import main
from voly.config import VOLYConfig


def _disable_executors(monkeypatch) -> None:
    monkeypatch.setattr("voly.environment.shutil.which", lambda _name: None)
    monkeypatch.setattr("voly.environment._local_cli_candidates", lambda _name: [])
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)


def test_quickstart_check_is_read_only_and_reports_ready(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(
        "voly.environment.shutil.which",
        lambda name: "C:/tools/claude.cmd" if name == "claude.cmd" else None,
    )
    monkeypatch.setattr("voly.environment._local_cli_candidates", lambda _name: [])
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)

    result = CliRunner().invoke(
        quickstart,
        ["--check", "--json", "--cwd", str(repo)],
        obj={"config": VOLYConfig()},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is True
    assert payload["config"]["status"] == "missing"
    assert payload["recommended_executor"] == "claude-code"
    assert "--dry-run" in payload["next_command"]
    assert not (repo / "voly.yaml").exists()


def test_quickstart_blocks_without_executor(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    _disable_executors(monkeypatch)

    result = CliRunner().invoke(
        quickstart,
        ["--check", "--json", "--cwd", str(repo)],
        obj={"config": VOLYConfig()},
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["recommended_executor"] == ""
    assert payload["blockers"] == ["No supported file-capable executor was detected."]
    assert not (repo / "voly.yaml").exists()


def test_quickstart_yes_creates_config_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(
        "voly.environment.shutil.which",
        lambda name: "C:/tools/opencode.cmd" if name == "opencode.cmd" else None,
    )
    monkeypatch.setattr("voly.environment._local_cli_candidates", lambda _name: [])
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)

    created = CliRunner().invoke(
        quickstart,
        ["--yes", "--json", "--cwd", str(repo)],
        obj={"config": VOLYConfig()},
    )

    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["config"]["status"] == "created"
    config_path = repo / "voly.yaml"
    original = config_path.read_text(encoding="utf-8")

    repeated = CliRunner().invoke(
        quickstart,
        ["--yes", "--json", "--cwd", str(repo)],
        obj={"config": VOLYConfig()},
    )

    assert repeated.exit_code == 0, repeated.output
    assert json.loads(repeated.output)["config"]["status"] == "ready"
    assert config_path.read_text(encoding="utf-8") == original


def test_main_quickstart_skips_capability_startup_sync(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(
        "voly.environment.shutil.which",
        lambda name: "C:/tools/claude.cmd" if name == "claude.cmd" else None,
    )
    monkeypatch.setattr("voly.environment._local_cli_candidates", lambda _name: [])
    sync_calls: list[str] = []
    main_module = importlib.import_module("voly.cli.main")
    monkeypatch.setattr(main_module, "startup_sync", sync_calls.append)

    result = CliRunner().invoke(main, ["quickstart", "--check", "--cwd", str(repo)])

    assert result.exit_code == 0, result.output
    assert sync_calls == []
