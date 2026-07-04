"""Tests for the project-state cache-scoping fingerprint (VOLY risk R1)."""

from __future__ import annotations

import subprocess

import pytest

from voly.ai_gateway.project_state import project_fingerprint


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("print('one')\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


# ─── Empty / non-project ─────────────────────────────────────────────────────
def test_empty_cwd_yields_no_scope():
    assert project_fingerprint("") == ""
    assert project_fingerprint("/nonexistent/path/xyz") == ""


def test_non_git_dir_uses_path_identity(tmp_path):
    fp = project_fingerprint(str(tmp_path))
    assert fp.startswith("path:")
    # Same path → stable; different path → different scope.
    assert fp == project_fingerprint(str(tmp_path))
    assert fp != project_fingerprint(str(tmp_path.parent))


# ─── Git repo: HEAD-based, invalidates on change ─────────────────────────────
def test_clean_repo_is_stable_and_head_based(git_repo):
    fp = project_fingerprint(str(git_repo))
    assert fp.startswith("git:")
    assert "dirty:" not in fp
    assert fp == project_fingerprint(str(git_repo))  # deterministic


def test_new_commit_changes_fingerprint(git_repo):
    before = project_fingerprint(str(git_repo))
    (git_repo / "b.py").write_text("print('two')\n")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-qm", "second")
    assert project_fingerprint(str(git_repo)) != before


def test_dirty_tree_changes_fingerprint_and_tracks_content(git_repo):
    clean = project_fingerprint(str(git_repo))
    (git_repo / "a.py").write_text("print('edited')\n")
    dirty_one = project_fingerprint(str(git_repo))
    assert dirty_one != clean
    assert "dirty:" in dirty_one
    # Re-editing the SAME file to different content must invalidate again —
    # the dirty signature folds `git diff HEAD`, not just the porcelain status.
    (git_repo / "a.py").write_text("print('edited differently')\n")
    assert project_fingerprint(str(git_repo)) != dirty_one


# ─── File-level hook (opt-in) ────────────────────────────────────────────────
def test_files_hook_adds_content_precision(git_repo):
    base = project_fingerprint(str(git_repo))
    with_files = project_fingerprint(str(git_repo), files=["a.py"])
    assert "files:" in with_files
    assert with_files != base
    # Stable for identical content, changes when the listed file changes.
    assert with_files == project_fingerprint(str(git_repo), files=["a.py"])
    (git_repo / "a.py").write_text("print('changed')\n")
    assert project_fingerprint(str(git_repo), files=["a.py"]) != with_files
