"""Clone, cache, and report persistence helpers for repo analysis."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from voly.intelligence.admission import check as admission_check, parse_github_url
from voly.intelligence.schema import RepositoryIntelligence

_log = logging.getLogger("voly.intelligence.repo_analyzer_cache")
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")
_LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def slug(owner: str, repo: str) -> str:
    return f"{_SAFE.sub('_', owner)}__{_SAFE.sub('_', repo)}"


def get_report_path(reports_dir: str, owner: str, repo: str, sha: str) -> str:
    return str(Path(reports_dir) / f"{slug(owner, repo)}@{sha}.json")


def load_cached_report(path: str, max_age_days: int) -> RepositoryIntelligence | None:
    p = Path(path)
    if not p.is_file():
        return None
    age_days = (time.time() - p.stat().st_mtime) / 86400.0
    if age_days > max_age_days:
        return None
    try:
        return RepositoryIntelligence.from_json(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        _log.warning("invalid cached report %s: %s", path, exc)
        return None


def resolve_head_sha(clone_path: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=clone_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return (r.stdout or "").strip()[:8]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def shallow_clone(url: str, target_path: str) -> bool:
    if not shutil.which("git"):
        _log.warning("git not installed — cannot clone")
        return False
    target = Path(target_path)
    if target.exists() and (target / ".git").exists():
        return True
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", url, str(target)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _log.warning("shallow clone failed: %s", exc)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return False


def find_cached_report(
    reports_dir: str, owner: str, repo: str, max_age: int
) -> RepositoryIntelligence | None:
    pattern = f"{slug(owner, repo)}@*.json"
    hits = sorted(
        Path(reports_dir).glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in hits:
        report = load_cached_report(str(path), max_age)
        if report is not None:
            return report
    return None


def find_license(repo_root: str | Path) -> str | None:
    root = Path(repo_root)
    for name in _LICENSE_NAMES:
        path = root / name
        if path.is_file():
            return str(path)
    return None


def clone_repository(url: str, config) -> str:
    """Admission-checked shallow clone or local path resolution."""
    admission = admission_check(url, config.admission)
    if not admission.allowed:
        raise ValueError(admission.reason or "admission denied")
    local = Path(url)
    if local.is_dir():
        return str(local.resolve())
    parsed = parse_github_url(url)
    owner, repo = parsed if parsed else ("local", "repo")
    target = str(Path(config.cache_dir) / slug(owner, repo))
    if not shallow_clone(url, target):
        raise ValueError(f"failed to clone {url}")
    return target


def check_drift(report: RepositoryIntelligence, clone_path: str) -> bool:
    current = resolve_head_sha(clone_path)
    if current != "unknown" and report.commit != current:
        _log.warning("report drift: cached %s vs HEAD %s", report.commit, current)
        return True
    return False
