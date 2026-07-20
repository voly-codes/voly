"""Git + path helpers for plan acceptance verification."""

from __future__ import annotations

import hashlib
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


def path_fingerprint(cwd: str, rel: str) -> str:
    """Cheap content fingerprint: size + mtime_ns + sha256 of file bytes.

    Used to detect edits to paths that stay ``??`` / ``A`` across a role run
    (porcelain status alone is unchanged for already-untracked files).
    """
    if not cwd or not rel:
        return ""
    path = os.path.join(cwd, rel)
    try:
        st = os.stat(path)
        if not os.path.isfile(path):
            return f"d:{st.st_size}:{st.st_mtime_ns}"
        h = hashlib.sha256()
        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        with open(path, "rb") as fh:
            # Cap read — large assets still change size/mtime in the prefix.
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
                if h.digest_size and fh.tell() > 2_000_000:
                    h.update(b"#truncated")
                    break
        return h.hexdigest()
    except OSError:
        return ""


def fingerprint_untracked(cwd: str, porcelain: dict[str, str]) -> dict[str, str]:
    """Fingerprints for untracked / newly-added paths in a porcelain snapshot."""
    out: dict[str, str] = {}
    for rel, status in (porcelain or {}).items():
        st = status or ""
        if "?" not in st and "A" not in st:
            continue
        fp = path_fingerprint(cwd, rel)
        if fp:
            out[rel] = fp
    return out


def changed_paths(
    git_before: dict[str, str],
    git_after: dict[str, str],
    *,
    fingerprints_before: dict[str, str] | None = None,
    fingerprints_after: dict[str, str] | None = None,
) -> set[str]:
    """Paths whose porcelain entry appeared, disappeared, or changed.

    When fingerprint maps are provided, also include already-untracked / added
    paths whose content fingerprint changed even if the status code stayed
    the same (``??`` → ``??`` after an in-place edit).
    """
    keys = set(git_before) | set(git_after)
    out: set[str] = set()
    for p in keys:
        if git_before.get(p) != git_after.get(p):
            out.add(p)
    if fingerprints_before is not None and fingerprints_after is not None:
        for p in set(fingerprints_before) | set(fingerprints_after):
            if p in out:
                continue
            before_st = git_before.get(p, "")
            after_st = git_after.get(p, "")
            # Only apply fingerprint compare when the path stayed untracked/new.
            if before_st and after_st and before_st == after_st:
                if "?" in after_st or "A" in after_st:
                    if fingerprints_before.get(p) != fingerprints_after.get(p):
                        out.add(p)
            elif p in fingerprints_after and p not in fingerprints_before:
                # New untracked file created during the run (also caught by
                # porcelain when it appears, but keep for empty-before edge).
                if "?" in after_st or "A" in after_st:
                    out.add(p)
    return out
