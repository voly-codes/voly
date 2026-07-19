"""Shallow git clone into .voly/reuse/cache/<owner>__<repo>@<sha>/."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger("voly.reuse.clone")

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


class CloneError(RuntimeError):
    pass


def _slug(full_name: str) -> str:
    owner, _, repo = full_name.partition("/")
    return f"{_SAFE.sub('_', owner)}__{_SAFE.sub('_', repo)}"


def resolve_head_sha(repo_dir: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return (r.stdout or "").strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def clone_repo(
    clone_url: str,
    *,
    full_name: str,
    cache_dir: str | Path,
    depth: int = 1,
) -> Path:
    """Shallow-clone into cache. Reuses existing checkout if present."""
    if not shutil.which("git"):
        raise CloneError("git is not installed")

    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    slug = _slug(full_name)

    # Prefer an existing matching directory (any sha suffix).
    existing = sorted(cache_root.glob(f"{slug}@*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for cand in existing:
        if (cand / ".git").exists():
            _log.info("reuse cache hit: %s", cand)
            return cand

    staging = cache_root / f".staging_{slug}"
    if staging.exists():
        shutil.rmtree(staging)

    try:
        subprocess.run(
            ["git", "clone", f"--depth={depth}", clone_url, str(staging)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e))[:400]
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise CloneError(f"git clone failed for {full_name}: {err}") from e
    except subprocess.TimeoutExpired as e:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise CloneError(f"git clone timed out for {full_name}") from e

    sha = resolve_head_sha(staging)
    dest = cache_root / f"{slug}@{sha}"
    if dest.exists():
        shutil.rmtree(staging, ignore_errors=True)
        return dest
    staging.rename(dest)
    _log.info("cloned %s → %s", full_name, dest)
    return dest
