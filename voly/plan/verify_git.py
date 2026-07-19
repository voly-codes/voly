"""Git + path helpers for plan acceptance verification."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from voly.plan.verify_types import VerifyError


def safe_join(cwd: str, rel: str) -> Path:
    """Resolve ``rel`` under ``cwd``; reject path escape."""
    if not cwd:
        raise VerifyError("cwd is required for path-based checks")
    base = Path(cwd).resolve()
    # Absolute paths must still land under cwd.
    candidate = Path(rel)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (base / candidate).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise VerifyError(f"path escapes cwd: {rel!r}") from exc
    return target


def _git_has_commits(cwd: str, timeout: float = 5.0) -> bool:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _git_seed_commit(cwd: str, timeout: float = 10.0) -> bool:
    """Create an empty root commit so stash/rev-parse work in a freshly init'd repo."""
    try:
        cfg = ["-c", "user.email=voly@local", "-c", "user.name=voly"]
        subprocess.run(
            ["git", *cfg, "commit", "--allow-empty", "-m", "chore: voly seed commit"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return _git_has_commits(cwd)
    except (OSError, subprocess.SubprocessError):
        return False


def _ensure_voly_gitignore(cwd: str) -> None:
    """Add .voly/ to the project's .gitignore so pipeline artifacts don't pollute git diff."""
    gitignore_path = os.path.join(cwd, ".gitignore")
    entry = ".voly/"
    try:
        if os.path.isfile(gitignore_path):
            lines = Path(gitignore_path).read_text().splitlines()
            if any(line.strip() == entry for line in lines):
                return
        with open(gitignore_path, "a") as f:
            f.write(f"\n{entry}\n")
    except OSError:
        pass


def ensure_git_repo(cwd: str, *, timeout: float = 10.0) -> bool:
    """Initialize git in ``cwd`` when missing so hybrid verify can track files.

    Also creates a seed commit when the repo has no commits yet so that
    ``git stash create`` and ``git rev-parse HEAD`` work for safety snapshots.
    Returns True if any initialization (init or seed commit) was performed.
    """
    if not cwd or not os.path.isdir(cwd):
        return False
    _ensure_voly_gitignore(cwd)
    did_work = False
    if not os.path.isdir(os.path.join(cwd, ".git")):
        try:
            proc = subprocess.run(
                ["git", "init"],
                cwd=cwd, capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                return False
            did_work = True
        except (OSError, subprocess.SubprocessError):
            return False
    if not _git_has_commits(cwd):
        did_work = _git_seed_commit(cwd, timeout=timeout) or did_work
    return did_work


def git_porcelain(cwd: str, *, timeout: float = 5.0) -> dict[str, str]:
    """Return {path: status_code} from ``git status --porcelain``."""
    if not cwd or not os.path.isdir(cwd):
        return {}
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        if len(line) < 4:
            continue
        xy, path = line[:2], line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        result[path] = xy.strip() or "?"
    return result


def changed_paths(
    git_before: dict[str, str],
    git_after: dict[str, str],
) -> set[str]:
    """Paths whose porcelain entry appeared, disappeared, or changed."""
    keys = set(git_before) | set(git_after)
    out: set[str] = set()
    for p in keys:
        if git_before.get(p) != git_after.get(p):
            out.add(p)
    return out
