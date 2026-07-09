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

KNOWN_CHECK_TYPES = frozenset({
    CHECK_COMMAND,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
})

DEFAULT_COMMAND_TIMEOUT = 120.0


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


_HANDLERS: dict[str, Callable[[AcceptanceCheck, VerifyContext], VerifyResult]] = {
    CHECK_COMMAND: _check_command,
    CHECK_FILES_EXIST: _check_files_exist,
    CHECK_FILES_MISSING: _check_files_missing,
    CHECK_GIT_DIFF_NONEMPTY: _check_git_diff_nonempty,
    CHECK_GIT_DIFF_CONTAINS: _check_git_diff_contains,
    CHECK_OUTPUT_NONEMPTY: _check_output_nonempty,
    CHECK_OUTPUT_REGEX: _check_output_regex,
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
