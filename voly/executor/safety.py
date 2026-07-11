"""Executor safety policy: dry-run, protected paths, max-files-touched.

Phase 1 of the executor safety pack (docs/backend/executors.md § Safety
policy). Enforced in ``AgentRunner.run`` after the executor finishes, using
git state:

- a pre-run snapshot (``git stash create`` — does not touch the worktree)
  lets us restore the exact pre-run content of a file even when it already
  had uncommitted changes before the run;
- only files whose ``git status`` changed **during the run** are ever touched;
  pre-existing dirty files stay as they were.

Without a git repository in ``cwd`` the policy degrades to a no-op warning —
there is nothing safe to roll back to.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

_log = logging.getLogger("voly.executor.safety")

# Files an executor must never modify silently: env/secret material and git
# internals. Matched with fnmatch against the repo-relative path and basename.
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "*.p12",
    ".git/**",
)

_DIFF_PREVIEW_LIMIT = 20_000  # chars kept in metadata for UI preview


@dataclass
class SafetyOutcome:
    """What the policy did to a finished executor run."""

    violations: list[str] = field(default_factory=list)  # human-readable
    rolled_back: list[str] = field(default_factory=list)  # repo-relative paths
    dry_run: bool = False
    diff_preview: str = ""


def is_protected(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    norm = path.replace(os.sep, "/")
    base = norm.rsplit("/", 1)[-1]
    for pat in patterns:
        if fnmatch(norm, pat) or fnmatch(base, pat):
            return True
        # "dir/**" should also protect the dir itself and direct children
        if pat.endswith("/**") and (norm == pat[:-3] or norm.startswith(pat[:-2])):
            return True
    return False


def run_touched_files(
    before: dict[str, str], after: dict[str, str]
) -> tuple[list[str], list[str]]:
    """(touched, created) — paths whose git status changed during the run.

    ``created`` ⊆ ``touched``: paths that did not exist before the run and
    must be deleted on rollback (nothing to restore).
    """
    touched: list[str] = []
    created: list[str] = []
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        if b == a:
            continue
        touched.append(path)
        if b is None and a in ("?", "??", "A"):
            created.append(path)
    return touched, created


def content_touched_files(
    cwd: str,
    snapshot: str,
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[list[str], list[str]]:
    """(touched, created) by **content**, not porcelain status.

    A file that was already dirty before the run and modified again by the
    executor keeps the same porcelain status — only a content diff against
    the pre-run snapshot catches it. Tracked files: ``git diff <snapshot>``;
    untracked/staged-new ones still come from the porcelain delta.
    """
    touched: set[str] = set()
    if snapshot:
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", snapshot],
                cwd=cwd, capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                touched.update(p.strip() for p in proc.stdout.splitlines() if p.strip())
        except Exception:  # noqa: BLE001
            pass
    delta_touched, created = run_touched_files(before, after)
    touched.update(delta_touched)
    return sorted(touched), created


def git_snapshot(cwd: str) -> str:
    """Commit-ish capturing the pre-run worktree; "" when not a git repo.

    ``git stash create`` records tracked state without modifying anything;
    on a clean tree it prints nothing — fall back to HEAD.
    """
    try:
        proc = subprocess.run(
            ["git", "stash", "create", "voly-safety-snapshot"],
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return ""
        sha = proc.stdout.strip()
        if sha:
            return sha
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        return head.stdout.strip() if head.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def rollback_files(cwd: str, snapshot: str, files: list[str], created: list[str]) -> list[str]:
    """Restore ``files`` to the snapshot state; delete ``created`` ones.

    Returns the paths actually rolled back. Never raises — a rollback problem
    is reported, not fatal (the caller already marks the run failed).
    """
    done: list[str] = []
    created_set = set(created)
    for path in files:
        try:
            if path in created_set:
                target = os.path.join(cwd, path)
                if os.path.isfile(target):
                    os.remove(target)
                done.append(path)
                continue
            if not snapshot:
                continue
            proc = subprocess.run(
                ["git", "checkout", snapshot, "--", path],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                done.append(path)
            else:
                _log.warning("safety rollback failed for %s: %s", path, proc.stderr.strip()[:200])
        except Exception as exc:  # noqa: BLE001
            _log.warning("safety rollback failed for %s: %s", path, exc)
    return done


def capture_diff(cwd: str, snapshot: str, created: list[str]) -> str:
    """Textual preview of what the run changed (tracked diff + created files)."""
    parts: list[str] = []
    try:
        if snapshot:
            proc = subprocess.run(
                ["git", "diff", snapshot],
                cwd=cwd, capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                parts.append(proc.stdout)
    except Exception:  # noqa: BLE001
        pass
    for path in created:
        parts.append(f"+++ created: {path}")
    diff = "\n".join(parts)
    if len(diff) > _DIFF_PREVIEW_LIMIT:
        diff = diff[:_DIFF_PREVIEW_LIMIT] + "\n…(truncated)"
    return diff


def apply_safety_policy(
    *,
    cwd: str,
    policy: Any,
    snapshot: str,
    before: dict[str, str],
    after: dict[str, str],
    dry_run: bool = False,
) -> SafetyOutcome:
    """Evaluate + enforce the policy for a finished run. Mutates the worktree.

    ``policy`` is ``ExecutorSafetyConfig``-shaped (enabled, dry_run,
    protected_paths, max_files_touched). ``dry_run`` is the per-call override
    (CLI/API); config ``dry_run`` applies to every run.
    """
    out = SafetyOutcome()
    if policy is None or not getattr(policy, "enabled", True) or not cwd:
        return out

    effective_dry = dry_run or bool(getattr(policy, "dry_run", False))
    if not snapshot:
        if run_touched_files(before, after)[0]:
            _log.warning("safety policy skipped: %s is not a git repository", cwd)
        out.dry_run = effective_dry
        return out

    touched, created = content_touched_files(cwd, snapshot, before, after)
    if not touched:
        out.dry_run = effective_dry
        return out

    patterns = list(getattr(policy, "protected_paths", None) or DEFAULT_PROTECTED_PATHS)
    protected = [p for p in touched if is_protected(p, patterns)]
    max_files = int(getattr(policy, "max_files_touched", 0) or 0)
    over_limit = max_files > 0 and len(touched) > max_files

    if effective_dry:
        out.dry_run = True
        out.diff_preview = capture_diff(cwd, snapshot, created)

    if over_limit:
        # Runaway change: revert everything the run touched.
        out.violations.append(
            f"max_files_touched exceeded: {len(touched)} > {max_files}"
        )
        out.rolled_back = rollback_files(cwd, snapshot, touched, created)
        return out

    if protected:
        out.violations.append(
            "protected path(s) modified: " + ", ".join(protected[:10])
        )
        if effective_dry:
            # dry-run reverts everything anyway — fall through
            pass
        else:
            out.rolled_back = rollback_files(cwd, snapshot, protected, created=[
                p for p in created if p in set(protected)
            ])

    if effective_dry:
        out.rolled_back = rollback_files(cwd, snapshot, touched, created)

    return out
