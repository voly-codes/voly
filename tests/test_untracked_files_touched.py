"""Untracked-file fingerprint deltas for files_touched honesty."""

from __future__ import annotations

import time
from pathlib import Path

from voly.a2a.context import delta_for_role
from voly.plan.verify_git import changed_paths, fingerprint_untracked, git_porcelain
from voly.runner.work_report import _build_work_report


def test_changed_paths_detects_untracked_content_edit(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / ".git").mkdir()
    target = repo / "tests" / "test_foo.py"
    target.parent.mkdir()
    target.write_text("def test_a():\n    assert True\n", encoding="utf-8")

    # Simulate porcelain: already untracked before and after.
    before = {"tests/test_foo.py": "??"}
    fp_before = fingerprint_untracked(str(repo), before)
    time.sleep(0.05)
    target.write_text("def test_a():\n    assert True\n\ndef test_b():\n    assert 1\n", encoding="utf-8")
    after = {"tests/test_foo.py": "??"}
    fp_after = fingerprint_untracked(str(repo), after)

    assert changed_paths(before, after) == set()
    assert changed_paths(
        before, after, fingerprints_before=fp_before, fingerprints_after=fp_after,
    ) == {"tests/test_foo.py"}


def test_delta_for_role_includes_edited_untracked(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    # Real git repo so git_porcelain works.
    import subprocess

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    target = repo / "helper.py"
    target.write_text("x = 1\n", encoding="utf-8")
    before = git_porcelain(str(repo))
    assert "helper.py" in before
    fp_before = fingerprint_untracked(str(repo), before)
    wall0 = time.time()
    time.sleep(0.05)
    target.write_text("x = 2\n", encoding="utf-8")

    delta = delta_for_role(
        str(repo), before, since=wall0, fingerprints_before=fp_before,
    )
    assert "helper.py" in delta


def test_work_report_marks_untracked_edit_as_changed(tmp_path: Path) -> None:
    before = {"app.py": "??"}
    after = {"app.py": "??"}
    fp_b = {"app.py": "aaa"}
    fp_a = {"app.py": "bbb"}
    report = _build_work_report(
        "done", before, after,
        fingerprints_before=fp_b, fingerprints_after=fp_a,
    )
    assert "app.py" in report.files_changed
