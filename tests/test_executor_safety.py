"""Executor safety policy: dry-run rollback, protected paths, max files touched."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from voly.config import ExecutorSafetyConfig, VOLYConfig, load_config
from voly.executor.base import ExecutorResult
from voly.executor.safety import (
    DEFAULT_PROTECTED_PATHS,
    apply_safety_policy,
    git_snapshot,
    is_protected,
    run_touched_files,
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "proj"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "src").mkdir()
    (d / "src" / "a.py").write_text("original a\n", encoding="utf-8")
    (d / ".env").write_text("SECRET=original\n", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def test_is_protected_defaults() -> None:
    for p in (".env", ".env.local", "config/.env", "certs/server.pem",
              "id_rsa", ".git/config", "keys/private.key"):
        assert is_protected(p, DEFAULT_PROTECTED_PATHS), p
    for p in ("src/a.py", "docs/env.md", "environment.py"):
        assert not is_protected(p, DEFAULT_PROTECTED_PATHS), p


def test_run_touched_files_delta_only() -> None:
    before = {"dirty.py": "M"}
    after = {"dirty.py": "M", "src/a.py": "M", "new.py": "??"}
    touched, created = run_touched_files(before, after)
    assert touched == ["new.py", "src/a.py"]
    assert created == ["new.py"]


def test_work_report_classification() -> None:
    """Clean-tracked files modified during the run are 'changed', not 'created'."""
    from voly.runner.agent_runner import _build_work_report

    report = _build_work_report(
        "",
        before={"pre_dirty.py": "M"},
        after={
            "pre_dirty.py": "M",        # unchanged status → not in the report
            "tracked_clean.py": "M",    # clean before, modified during run
            "brand_new.py": "??",       # untracked → created
            "staged_new.py": "A",       # staged add → created
            "removed.py": "D",          # deleted during run
        },
    )
    assert report.files_changed == ["tracked_clean.py"]
    assert report.files_created == ["brand_new.py", "staged_new.py"]
    assert report.files_deleted == ["removed.py"]


def _policy(**kw) -> ExecutorSafetyConfig:
    return ExecutorSafetyConfig(**kw)


def _simulate_run(repo: Path, writes: dict[str, str]):
    """Snapshot → 'executor' writes files → returns (snapshot, before, after)."""
    from voly.runner.agent_runner import _git_porcelain

    before = _git_porcelain(str(repo))
    snap = git_snapshot(str(repo))
    for rel, content in writes.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    after = _git_porcelain(str(repo))
    return snap, before, after


def test_protected_path_rolled_back_others_kept(repo: Path) -> None:
    snap, before, after = _simulate_run(repo, {
        ".env": "SECRET=stolen\n",
        "src/a.py": "modified a\n",
        "server.pem": "FAKEPEM\n",
    })
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(), snapshot=snap,
        before=before, after=after,
    )
    assert out.violations and "protected path" in out.violations[0]
    assert ".env" in out.violations[0] and "server.pem" in out.violations[0]
    # protected files restored/removed; legit change kept
    assert (repo / ".env").read_text(encoding="utf-8") == "SECRET=original\n"
    assert not (repo / "server.pem").exists()
    assert (repo / "src" / "a.py").read_text(encoding="utf-8") == "modified a\n"


def test_dirty_before_content_restored_not_head(repo: Path) -> None:
    """A file dirty before AND modified during the run is caught by content
    diff (porcelain status alone can't see it) and restored to the pre-run
    dirty content — not to HEAD."""
    (repo / ".env").write_text("SECRET=my-local-edit\n", encoding="utf-8")
    snap, before, after = _simulate_run(repo, {".env": "SECRET=agent-overwrote\n"})
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(), snapshot=snap,
        before=before, after=after,
    )
    assert out.violations and ".env" in out.violations[0]
    assert (repo / ".env").read_text(encoding="utf-8") == "SECRET=my-local-edit\n"


def test_dry_run_rolls_back_dirty_before_file(repo: Path) -> None:
    """Dry-run contract: changes to a pre-dirty file are also rolled back."""
    (repo / "src" / "a.py").write_text("my local wip\n", encoding="utf-8")
    snap, before, after = _simulate_run(repo, {"src/a.py": "my local wip\nagent line\n"})
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(), snapshot=snap,
        before=before, after=after, dry_run=True,
    )
    assert out.dry_run and "src/a.py" in out.rolled_back
    assert (repo / "src" / "a.py").read_text(encoding="utf-8") == "my local wip\n"


def test_dirty_before_protected_change_detected_via_hash(repo: Path) -> None:
    """A tracked file modified during the run (clean before) is restored to snapshot."""
    (repo / "src" / "a.py").write_text("pre-run local edit\n", encoding="utf-8")
    # commit .env change? no — modify a *clean* protected file during run:
    snap, before, after = _simulate_run(repo, {".env": "SECRET=agent\n"})
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(), snapshot=snap, before=before, after=after,
    )
    assert out.violations
    assert (repo / ".env").read_text(encoding="utf-8") == "SECRET=original\n"
    # unrelated pre-run dirty file untouched
    assert (repo / "src" / "a.py").read_text(encoding="utf-8") == "pre-run local edit\n"


def test_max_files_touched_rolls_back_everything(repo: Path) -> None:
    snap, before, after = _simulate_run(repo, {
        "src/a.py": "m1\n", "src/b.py": "new\n", "src/c.py": "new\n",
    })
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(max_files_touched=2), snapshot=snap,
        before=before, after=after,
    )
    assert out.violations and "max_files_touched" in out.violations[0]
    assert (repo / "src" / "a.py").read_text(encoding="utf-8") == "original a\n"
    assert not (repo / "src" / "b.py").exists()
    assert not (repo / "src" / "c.py").exists()


def test_dry_run_rolls_back_and_keeps_diff(repo: Path) -> None:
    snap, before, after = _simulate_run(repo, {
        "src/a.py": "dry change\n", "src/new.py": "created\n",
    })
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(), snapshot=snap,
        before=before, after=after, dry_run=True,
    )
    assert out.dry_run is True
    assert not out.violations
    assert "dry change" in out.diff_preview
    assert "created: src/new.py" in out.diff_preview
    assert (repo / "src" / "a.py").read_text(encoding="utf-8") == "original a\n"
    assert not (repo / "src" / "new.py").exists()


def test_disabled_policy_is_noop(repo: Path) -> None:
    snap, before, after = _simulate_run(repo, {".env": "SECRET=agent\n"})
    out = apply_safety_policy(
        cwd=str(repo), policy=_policy(enabled=False), snapshot=snap,
        before=before, after=after,
    )
    assert not out.violations and not out.rolled_back
    assert (repo / ".env").read_text(encoding="utf-8") == "SECRET=agent\n"


def test_non_git_cwd_is_noop(tmp_path: Path) -> None:
    d = tmp_path / "plain"
    d.mkdir()
    (d / "x.txt").write_text("x", encoding="utf-8")
    out = apply_safety_policy(
        cwd=str(d), policy=_policy(), snapshot="",
        before={}, after={"x.txt": "??"},
    )
    assert not out.rolled_back
    assert (d / "x.txt").exists()


def test_config_defaults_and_yaml(tmp_path: Path) -> None:
    cfg = VOLYConfig()
    assert cfg.executor_safety.enabled is True
    assert cfg.executor_safety.dry_run is False
    assert cfg.executor_safety.max_files_touched == 0

    p = tmp_path / "voly.yaml"
    p.write_text(
        "executor_safety:\n  dry_run: true\n  max_files_touched: 5\n"
        "  protected_paths:\n    - 'infra/**'\n",
        encoding="utf-8",
    )
    loaded = load_config(p)
    assert loaded.executor_safety.dry_run is True
    assert loaded.executor_safety.max_files_touched == 5
    assert loaded.executor_safety.protected_paths == ["infra/**"]


def test_agent_runner_enforces_policy(repo: Path, monkeypatch) -> None:
    """End-to-end: runner marks the run failed and rolls back a protected write."""
    from voly.runner import agent_runner as runner_mod
    from voly.runner.agent_runner import AgentRunner

    def _fake_build(name, model=None):
        class _E:
            def run(self, task, *, cwd, max_turns=30, timeout=300, **kw):
                Path(cwd, ".env").write_text("SECRET=agent\n", encoding="utf-8")
                Path(cwd, "src", "ok.py").write_text("fine\n", encoding="utf-8")
                return ExecutorResult(success=True, output="done")
        return _E()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *a, **k: None)

    from voly.config import RTKConfig
    r = AgentRunner(VOLYConfig(rtk=RTKConfig(enabled=False)))
    out = r.run("t", "claude-code", cwd=str(repo), emit_event=False)
    assert out.success is False
    assert "protected path" in (out.result.error or "")
    assert (repo / ".env").read_text(encoding="utf-8") == "SECRET=original\n"
    assert (repo / "src" / "ok.py").exists()
    assert out.result.metadata.get("safety_rolled_back") == [".env"]


def test_agent_runner_dry_run_flag(repo: Path, monkeypatch) -> None:
    from voly.runner import agent_runner as runner_mod
    from voly.runner.agent_runner import AgentRunner

    def _fake_build(name, model=None):
        class _E:
            def run(self, task, *, cwd, max_turns=30, timeout=300, **kw):
                Path(cwd, "src", "gen.py").write_text("generated\n", encoding="utf-8")
                return ExecutorResult(success=True, output="done")
        return _E()

    monkeypatch.setattr(runner_mod, "_build_executor", _fake_build)
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda *a, **k: None)

    from voly.config import RTKConfig
    r = AgentRunner(VOLYConfig(rtk=RTKConfig(enabled=False)))
    out = r.run("t", "claude-code", cwd=str(repo), emit_event=False, dry_run=True)
    assert out.success is True
    assert out.result.metadata.get("dry_run") is True
    assert "gen.py" in out.result.metadata.get("dry_run_diff", "")
    assert not (repo / "src" / "gen.py").exists()
    # WorkReport still lists what would change
    assert "src/gen.py" in (out.result.report.files_created if out.result.report else [])