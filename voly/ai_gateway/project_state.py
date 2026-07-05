"""Project-state fingerprint for cache-key scoping (VOLY risk R1).

Code generation is repo-sensitive: the same prompt on a changed codebase must
not serve a cached answer. ``AIGateway``'s cache key is content-based on the
request ``messages`` only — so two different projects (or the same project at
two different commits) with identical task text would collide on the persistent
cache. ``project_fingerprint`` produces a cheap, stable-per-state string that is
folded into the cache key so a repo change (or a different project) misses.

Granularity:

- **Repo-level (default):** git ``HEAD`` + a working-tree dirty signature. The
  dirty signature folds ``git diff HEAD`` + untracked list, so re-editing a
  tracked file to different content invalidates without a per-call file list.
- **File-level (opt-in):** pass ``files`` — a list of repo-relative paths — to
  also fold mtime+size+content of exactly those files. Reserved hook for the
  local-context path; the public signature does not change when unused.

Never raises: any git/FS failure degrades to a coarser-but-safe fingerprint
(project path identity) or ``""`` (no scope → current behaviour).
"""
from __future__ import annotations

import hashlib
import os
import subprocess


def _git(cwd: str, *args: str) -> str:
    """Run a git command in ``cwd``; return stripped stdout or ``""`` on failure."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _hash_files(base: str, files: list[str]) -> str:
    """16-hex digest over (path, size, mtime, content) of each file, order-stable."""
    h = hashlib.sha256()
    for rel in sorted(files):
        path = os.path.join(base, rel)
        try:
            st = os.stat(path)
            h.update(rel.encode())
            h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
            with open(path, "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(f"{rel}:missing".encode())
    return h.hexdigest()[:16]


def project_fingerprint(cwd: str, files: list[str] | None = None) -> str:
    """Return a cache-scoping fingerprint for the project rooted at ``cwd``.

    Empty string means "no project scope" — the cache key is unchanged, matching
    prior behaviour. See module docstring for granularity.
    """
    cwd = os.path.expanduser(cwd or "")
    if not cwd or not os.path.isdir(cwd):
        # No project dir: only an explicit file list can contribute (hashed
        # relative to the current working dir).
        return _hash_files(os.getcwd(), files) if files else ""

    parts: list[str] = []
    head = _git(cwd, "rev-parse", "HEAD")
    if head:
        parts.append(f"git:{head[:12]}")
        porcelain = _git(cwd, "status", "--porcelain")
        if porcelain:
            # Dirty tree: fold content (diff) + untracked so re-edits of the same
            # tracked file invalidate the cache even without a per-call file list.
            diff = _git(cwd, "diff", "HEAD")
            untracked = _git(cwd, "ls-files", "--others", "--exclude-standard")
            dirty = hashlib.sha256((porcelain + diff + untracked).encode()).hexdigest()[:16]
            parts.append(f"dirty:{dirty}")
    else:
        # Not a git repo: fall back to project-path identity. This still prevents
        # cross-project collisions; content precision needs the ``files`` hook.
        parts.append(f"path:{hashlib.sha256(cwd.encode()).hexdigest()[:12]}")

    if files:
        parts.append(f"files:{_hash_files(cwd, files)}")

    return "|".join(parts)
