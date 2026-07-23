"""Fixes: opencode/zen honor --dir for cwd; a2a call uses force_agent."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from voly.executor.base import _build_opencode_run_cmd
from voly.executor.opencode import OpenCodeExecutor
from voly.executor.zen import ZenExecutor


def test_build_opencode_run_cmd_includes_dir(tmp_path: Path) -> None:
    cmd = _build_opencode_run_cmd("do work", model_id="opencode/foo", cwd=str(tmp_path))
    assert cmd[:5] == ["opencode", "run", "--format", "json", "-m"]
    assert "foo" in cmd[5] or cmd[5].endswith("foo")
    assert "--dir" in cmd
    dir_idx = cmd.index("--dir")
    assert Path(cmd[dir_idx + 1]) == tmp_path.resolve()
    assert cmd[-1] == "do work"


def test_build_opencode_run_cmd_without_cwd() -> None:
    cmd = _build_opencode_run_cmd("hi", model_id="opencode/bar")
    assert "--dir" not in cmd
    assert cmd == ["opencode", "run", "--format", "json", "-m", "opencode/bar", "--auto", "hi"]


def test_build_opencode_run_cmd_expands_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    nested = tmp_path / "proj"
    nested.mkdir()
    # simulate ~/proj
    cmd = _build_opencode_run_cmd("t", model_id="m", cwd="~/proj")
    assert Path(cmd[cmd.index("--dir") + 1]) == nested.resolve()


def test_zen_run_cli_one_passes_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return SimpleNamespace(returncode=0, stdout='{"type":"text","part":{"text":"ok"}}\n', stderr="")

    monkeypatch.setattr("voly.executor.zen.subprocess.run", fake_run)
    # avoid full parse complexity if empty
    monkeypatch.setattr(
        ZenExecutor,
        "_parse_json_events",
        lambda self, *a, **k: __import__("voly.executor.base", fromlist=["ExecutorResult"]).ExecutorResult(
            success=True, output="ok"
        ),
    )

    ZenExecutor()._run_cli_one("task", model_id="opencode/m", cwd=str(tmp_path), timeout=30)
    assert "--dir" in captured["cmd"]
    assert Path(captured["cmd"][captured["cmd"].index("--dir") + 1]) == tmp_path.resolve()
    assert Path(captured["cwd"]) == tmp_path.resolve()


def test_opencode_run_cli_one_passes_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("voly.executor.opencode.subprocess.run", fake_run)
    monkeypatch.setattr(
        OpenCodeExecutor,
        "_parse_json_events",
        lambda self, *a, **k: __import__("voly.executor.base", fromlist=["ExecutorResult"]).ExecutorResult(
            success=True, output="ok"
        ),
    )

    OpenCodeExecutor(use_cli=True)._run_cli_one("task", model_id="opencode/m", cwd=str(tmp_path), timeout=30)
    assert "--dir" in captured["cmd"]
    assert Path(captured["cwd"]) == tmp_path.resolve()


def test_a2a_call_local_uses_force_agent(tmp_path: Path) -> None:
    """voly a2a call must call Pipeline.run(force_agent=..., context=cwd)."""
    from click.testing import CliRunner

    from voly.cli.commands.a2a import a2a
    from voly.config import VOLYConfig
    from voly.pipeline.types import PipelineResult, PipelineStage

    mock_pipeline = MagicMock()
    mock_orch = MagicMock()
    mock_task = SimpleNamespace(id="t-1", state=SimpleNamespace(value="submitted"))
    mock_orch.create_task.return_value = mock_task
    mock_orch._federation = None
    mock_pipeline.a2a = mock_orch
    mock_pipeline.run.return_value = PipelineResult(
        success=True,
        stage=PipelineStage.DONE if hasattr(PipelineStage, "DONE") else list(PipelineStage)[-1],
        response=SimpleNamespace(content="hello from agent"),
    )

    cfg = VOLYConfig()
    with patch("voly.pipeline.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        result = runner.invoke(
            a2a,
            ["call", "developer", "say hi", "--cwd", str(tmp_path)],
            obj={"config": cfg},
        )

    assert result.exit_code == 0, result.output
    mock_pipeline.run.assert_called_once()
    args, kwargs = mock_pipeline.run.call_args
    assert args[0] == "say hi"
    assert "agent" not in kwargs
    assert kwargs.get("force_agent") == "developer"
    ctx = kwargs.get("context") or {}
    assert ctx.get("cwd") == str(tmp_path)
    assert ctx.get("project_cwd") == str(tmp_path)
