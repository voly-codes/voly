"""Acceptance verifiers for plan steps (Rung B, PR2).

Evidence over self-report: checks operate on ``cwd``, declared paths, git
porcelain snapshots, and agent ``output`` — not on free-form model claims.

See ``docs/proposals/plan-gate-verification.md``.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from voly.plan.types import (
    FAILED,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    IllegalTransition,
    Plan,
    PlanStep,
)

# Built-in check type ids (unknown types fail closed).
CHECK_COMMAND = "command"
CHECK_FILES_EXIST = "files_exist"
CHECK_FILES_MISSING = "files_missing"
CHECK_GIT_DIFF_NONEMPTY = "git_diff_nonempty"
CHECK_GIT_DIFF_CONTAINS = "git_diff_contains"
CHECK_OUTPUT_NONEMPTY = "output_nonempty"
CHECK_OUTPUT_REGEX = "output_regex"
CHECK_FILE_LINE_LIMIT = "file_line_limit"

KNOWN_CHECK_TYPES = frozenset({
    CHECK_COMMAND,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
    CHECK_FILE_LINE_LIMIT,
})

DEFAULT_COMMAND_TIMEOUT = 60.0

_LINE_LIMIT_MARKER = re.compile(r"(?im)^\s*FILE_LINE_LIMIT:\s*(\d+)\s*$")
_LINE_LIMIT_REASON = re.compile(
    r"(?im)^\s*FILE_LINE_LIMIT_REASON:\s*(\S.{9,})\s*$"
)


@dataclass
class VerifyResult:
    """Outcome of a single acceptance check."""

    type: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class VerifyContext:
    """Evidence available when verifying a step."""

    cwd: str = ""
    output: str = ""
    files_touched: list[str] = field(default_factory=list)
    # {path: status_code} from `git status --porcelain` (before/after step).
    git_before: dict[str, str] = field(default_factory=dict)
    git_after: dict[str, str] = field(default_factory=dict)
    command_timeout: float = DEFAULT_COMMAND_TIMEOUT
    # Raised from the default limit only by a strict architect plan marker.
    approved_file_line_limit: int = 0


class VerifyError(Exception):
    """Raised for programmer misuse (not a failed check)."""


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


def _check_files_exist(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.paths:
        return VerifyResult(CHECK_FILES_EXIST, False, "files_exist requires paths[]")
    missing: list[str] = []
    try:
        for rel in check.paths:
            target = safe_join(ctx.cwd, rel)
            if not target.exists():
                missing.append(rel)
    except VerifyError as exc:
        return VerifyResult(CHECK_FILES_EXIST, False, str(exc))
    if missing:
        return VerifyResult(
            CHECK_FILES_EXIST,
            False,
            f"missing: {missing}",
            {"missing": missing},
        )
    return VerifyResult(CHECK_FILES_EXIST, True, "all paths exist", {"paths": list(check.paths)})


def _check_files_missing(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.paths:
        return VerifyResult(CHECK_FILES_MISSING, False, "files_missing requires paths[]")
    present: list[str] = []
    try:
        for rel in check.paths:
            target = safe_join(ctx.cwd, rel)
            if target.exists():
                present.append(rel)
    except VerifyError as exc:
        return VerifyResult(CHECK_FILES_MISSING, False, str(exc))
    if present:
        return VerifyResult(
            CHECK_FILES_MISSING,
            False,
            f"still present: {present}",
            {"present": present},
        )
    return VerifyResult(CHECK_FILES_MISSING, True, "all paths absent", {"paths": list(check.paths)})


def _resolve_git_after(ctx: VerifyContext) -> dict[str, str]:
    if ctx.git_after:
        return ctx.git_after
    if ctx.cwd:
        return git_porcelain(ctx.cwd)
    return {}


def _check_git_diff_nonempty(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    after = _resolve_git_after(ctx)
    if ctx.git_before or ctx.git_after:
        changed = changed_paths(ctx.git_before, after)
    else:
        # No before snapshot: any dirty porcelain counts as change evidence.
        changed = set(after.keys())

    if check.paths:
        wanted = set(check.paths)
        changed = {p for p in changed if p in wanted or any(
            p == w or p.startswith(w.rstrip("/") + "/") for w in wanted
        )}

    if not changed:
        return VerifyResult(
            CHECK_GIT_DIFF_NONEMPTY,
            False,
            "no git changes detected",
            {"changed": []},
        )
    return VerifyResult(
        CHECK_GIT_DIFF_NONEMPTY,
        True,
        f"{len(changed)} path(s) changed",
        {"changed": sorted(changed)},
    )


def _check_git_diff_contains(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    after = _resolve_git_after(ctx)
    if ctx.git_before or ctx.git_after:
        changed = changed_paths(ctx.git_before, after)
    else:
        changed = set(after.keys())

    # Also consider files_touched as soft evidence when git is empty.
    if not changed and ctx.files_touched:
        changed = set(ctx.files_touched)

    hits: list[str] = []
    if check.paths:
        for w in check.paths:
            for p in changed:
                if p == w or p.startswith(w.rstrip("/") + "/") or w in p:
                    hits.append(p)
        hits = sorted(set(hits))
        if not hits:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"none of paths {check.paths} in changed={sorted(changed)}",
                {"changed": sorted(changed)},
            )
        return VerifyResult(
            CHECK_GIT_DIFF_CONTAINS,
            True,
            f"matched paths: {hits}",
            {"hits": hits, "changed": sorted(changed)},
        )

    if check.pattern:
        try:
            rx = re.compile(check.pattern)
        except re.error as exc:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"invalid pattern: {exc}",
            )
        hits = sorted(p for p in changed if rx.search(p))
        if not hits:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"no changed path matches {check.pattern!r}",
                {"changed": sorted(changed)},
            )
        return VerifyResult(
            CHECK_GIT_DIFF_CONTAINS,
            True,
            f"pattern matched: {hits}",
            {"hits": hits},
        )

    return VerifyResult(
        CHECK_GIT_DIFF_CONTAINS,
        False,
        "git_diff_contains requires paths[] or pattern",
    )


def _check_command(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.run or not str(check.run).strip():
        return VerifyResult(CHECK_COMMAND, False, "command requires run")
    if not ctx.cwd:
        return VerifyResult(CHECK_COMMAND, False, "command requires cwd")
    try:
        argv = shlex.split(check.run, posix=os.name != "nt")
    except ValueError as exc:
        return VerifyResult(CHECK_COMMAND, False, f"invalid run string: {exc}")
    if not argv:
        return VerifyResult(CHECK_COMMAND, False, "empty command after split")

    # Refuse shell metacharacters that only work with shell=True.
    # argv is already split; still block absolute weirdness by requiring cwd jail
    # only for relative first token paths that look like files — not PATH bins.
    timeout = ctx.command_timeout if ctx.command_timeout > 0 else DEFAULT_COMMAND_TIMEOUT
    try:
        proc = subprocess.run(
            argv,
            cwd=ctx.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        return VerifyResult(
            CHECK_COMMAND,
            False,
            f"executable not found: {exc}",
            {"argv": argv},
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            CHECK_COMMAND,
            False,
            f"timeout after {timeout}s",
            {"argv": argv, "timeout": timeout},
        )
    except OSError as exc:
        return VerifyResult(CHECK_COMMAND, False, f"os error: {exc}", {"argv": argv})

    expected = int(check.expect_exit)
    ok = proc.returncode == expected
    stdout = (proc.stdout or "")[-2000:]
    stderr = (proc.stderr or "")[-2000:]
    msg = (
        f"exit {proc.returncode} (expected {expected})"
        if not ok
        else f"exit {proc.returncode}"
    )
    return VerifyResult(
        CHECK_COMMAND,
        ok,
        msg,
        {
            "argv": argv,
            "returncode": proc.returncode,
            "expect_exit": expected,
            "stdout_tail": stdout,
            "stderr_tail": stderr,
        },
    )


def _check_output_nonempty(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    text = ctx.output or ""
    if text.strip():
        return VerifyResult(
            CHECK_OUTPUT_NONEMPTY,
            True,
            f"output length={len(text)}",
            {"length": len(text)},
        )
    return VerifyResult(CHECK_OUTPUT_NONEMPTY, False, "output is empty")


def _check_output_regex(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.pattern:
        return VerifyResult(CHECK_OUTPUT_REGEX, False, "output_regex requires pattern")
    try:
        rx = re.compile(check.pattern, re.MULTILINE)
    except re.error as exc:
        return VerifyResult(CHECK_OUTPUT_REGEX, False, f"invalid pattern: {exc}")
    text = ctx.output or ""
    if rx.search(text):
        return VerifyResult(CHECK_OUTPUT_REGEX, True, f"matched {check.pattern!r}")
    return VerifyResult(
        CHECK_OUTPUT_REGEX,
        False,
        f"output does not match {check.pattern!r}",
        {"output_len": len(text)},
    )


def _line_count(path: Path) -> int | None:
    """Count physical lines; return None for binary files."""
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    if not raw:
        return 0
    return raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)


def _line_limit_candidates(check: AcceptanceCheck, ctx: VerifyContext) -> list[str]:
    if check.paths:
        return list(dict.fromkeys(check.paths))
    if ctx.files_touched:
        return list(dict.fromkeys(ctx.files_touched))
    after = _resolve_git_after(ctx)
    changed = (
        changed_paths(ctx.git_before, after)
        if ctx.git_before or ctx.git_after
        else set(after)
    )
    return sorted(changed)


def _check_file_line_limit(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    """Enforce per-file line limits on files changed by an executor step."""
    base_limit = int(check.max_lines or 300)
    approved_cap = int(check.approved_max_lines or base_limit)
    if base_limit <= 0:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, "max_lines must be positive")
    if approved_cap < base_limit:
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            "approved_max_lines must be >= max_lines",
        )
    if not ctx.cwd:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, "file_line_limit requires cwd")

    approved = int(ctx.approved_file_line_limit or 0)
    effective_limit = (
        min(approved, approved_cap)
        if approved > base_limit
        else base_limit
    )
    candidates = _line_limit_candidates(check, ctx)
    if not candidates:
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            "no changed files available for line-limit verification",
            {"limit": effective_limit, "checked": {}},
        )

    checked: dict[str, int] = {}
    skipped_binary: list[str] = []
    violations: dict[str, int] = {}
    try:
        for rel in candidates:
            target = safe_join(ctx.cwd, rel)
            if not target.is_file():
                continue
            count = _line_count(target)
            if count is None:
                skipped_binary.append(rel)
                continue
            checked[rel] = count
            if count > effective_limit:
                violations[rel] = count
    except (OSError, VerifyError) as exc:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, str(exc))

    detail = {
        "limit": effective_limit,
        "base_limit": base_limit,
        "architect_approved": effective_limit > base_limit,
        "checked": checked,
        "skipped_binary": skipped_binary,
        "violations": violations,
    }
    if violations:
        summary = ", ".join(f"{path}={lines}" for path, lines in sorted(violations.items()))
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            f"file line limit {effective_limit} exceeded: {summary}",
            detail,
        )
    return VerifyResult(
        CHECK_FILE_LINE_LIMIT,
        True,
        f"{len(checked)} text file(s) within {effective_limit} lines",
        detail,
    )


_HANDLERS: dict[str, Callable[[AcceptanceCheck, VerifyContext], VerifyResult]] = {
    CHECK_COMMAND: _check_command,
    CHECK_FILES_EXIST: _check_files_exist,
    CHECK_FILES_MISSING: _check_files_missing,
    CHECK_GIT_DIFF_NONEMPTY: _check_git_diff_nonempty,
    CHECK_GIT_DIFF_CONTAINS: _check_git_diff_contains,
    CHECK_OUTPUT_NONEMPTY: _check_output_nonempty,
    CHECK_OUTPUT_REGEX: _check_output_regex,
    CHECK_FILE_LINE_LIMIT: _check_file_line_limit,
}


def run_check(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    """Run one acceptance check. Unknown types fail closed."""
    ctype = (check.type or "").strip()
    handler = _HANDLERS.get(ctype)
    if handler is None:
        return VerifyResult(
            ctype or "unknown",
            False,
            f"unknown check type: {ctype!r} (fail closed)",
            {"known": sorted(KNOWN_CHECK_TYPES)},
        )
    return handler(check, ctx)


def run_acceptance(
    checks: list[AcceptanceCheck],
    ctx: VerifyContext,
    *,
    stop_on_fail: bool = False,
) -> list[VerifyResult]:
    """Run all checks in order. Optionally stop after the first failure."""
    results: list[VerifyResult] = []
    for check in checks:
        result = run_check(check, ctx)
        results.append(result)
        if stop_on_fail and not result.ok:
            break
    return results


def all_passed(results: list[VerifyResult]) -> bool:
    return bool(results) and all(r.ok for r in results)


def _architect_approved_line_limit(plan: Plan, step: PlanStep) -> int:
    """Find a strict line-limit approval marker in transitive architect dependencies."""
    by_id = {item.id: item for item in plan.steps}
    pending = list(step.depends_on)
    visited: set[str] = set()
    approved = 0
    while pending:
        step_id = pending.pop()
        if step_id in visited:
            continue
        visited.add(step_id)
        prior = by_id.get(step_id)
        if prior is None:
            continue
        pending.extend(prior.depends_on)
        if (prior.role or "").strip().lower() != "architect":
            continue
        output = prior.output or ""
        marker = _LINE_LIMIT_MARKER.search(output)
        reason = _LINE_LIMIT_REASON.search(output)
        if marker and reason:
            approved = max(approved, int(marker.group(1)))
    return approved


def verify_step(
    plan: Plan,
    step_id: str,
    ctx: VerifyContext | None = None,
    *,
    stop_on_fail: bool = False,
) -> list[VerifyResult]:
    """Run acceptance for a step; write ``verify_log``; do not transition status.

    Builds context from step fields when ``ctx`` omits output/files_touched.
    """
    step = plan.get_step(step_id)
    if not step.acceptance:
        return []

    base = ctx or VerifyContext()
    # Prefer explicit ctx values; fall back to step evidence.
    merged = VerifyContext(
        cwd=base.cwd or plan.cwd,
        output=base.output if base.output else step.output,
        files_touched=list(base.files_touched or step.files_touched),
        git_before=dict(base.git_before),
        git_after=dict(base.git_after),
        command_timeout=base.command_timeout,
        approved_file_line_limit=(
            base.approved_file_line_limit
            or _architect_approved_line_limit(plan, step)
        ),
    )
    results = run_acceptance(step.acceptance, merged, stop_on_fail=stop_on_fail)
    step.verify_log = [r.to_dict() for r in results]
    return results


def complete_verification(
    plan: Plan,
    step_id: str,
    ctx: VerifyContext | None = None,
    *,
    engine: Any | None = None,
    stop_on_fail: bool = False,
) -> tuple[PlanStep, list[VerifyResult]]:
    """Run checks and transition ``verifying → verified|failed``.

    Step must already be in ``verifying`` (use ``engine.advance_after_done`` first).
    """
    from voly.plan.engine import PlanEngine

    eng = engine or PlanEngine()
    step = plan.get_step(step_id)
    if step.status != VERIFYING:
        raise IllegalTransition(
            step_id,
            step.status,
            VERIFIED,
            "complete_verification requires status=verifying",
        )

    results = verify_step(plan, step_id, ctx, stop_on_fail=stop_on_fail)
    if not results:
        # Should not happen if advance_after_done sent us here, but stay safe.
        eng.transition(plan, step_id, VERIFIED)
        return plan.get_step(step_id), results

    if all_passed(results):
        eng.transition(plan, step_id, VERIFIED)
    else:
        failed = [r for r in results if not r.ok]
        summary = "; ".join(f"{r.type}: {r.message}" for r in failed)[:2000]
        eng.transition(plan, step_id, FAILED, error=summary or "verification failed")
    return plan.get_step(step_id), results
