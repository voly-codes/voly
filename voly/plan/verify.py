"""Acceptance verifiers for plan steps (Rung B, PR2).

Evidence over self-report: checks operate on ``cwd``, declared paths, git
porcelain snapshots, and agent ``output`` — not on free-form model claims.

See ``docs/proposals/plan-gate-verification.md``.

Module layout (behaviour unchanged — split for size/maintainability):

- ``verify_types.py``   — VerifyResult/Context, check-type constants
- ``verify_git.py``     — safe_join, ensure_git_repo, porcelain helpers
- ``verify_checks.py``  — built-in check handlers + run_check/run_acceptance
- ``verify.py``         — step orchestration + stable re-exports
"""

from __future__ import annotations

import re
from typing import Any

from voly.plan.types import (
    FAILED,
    VERIFIED,
    VERIFYING,
    IllegalTransition,
    Plan,
    PlanStep,
)
from voly.plan.verify_checks import all_passed, run_acceptance, run_check
from voly.plan.verify_git import (
    _git_has_commits,
    changed_paths,
    ensure_git_repo,
    fingerprint_untracked,
    git_porcelain,
    path_fingerprint,
    safe_join,
)
from voly.plan.verify_types import (
    CHECK_COMMAND,
    CHECK_FILE_LINE_LIMIT,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
    DEFAULT_COMMAND_TIMEOUT,
    KNOWN_CHECK_TYPES,
    VerifyContext,
    VerifyError,
    VerifyResult,
)

_LINE_LIMIT_MARKER = re.compile(r"(?im)^\s*FILE_LINE_LIMIT:\s*(\d+)\s*$")
_LINE_LIMIT_REASON = re.compile(
    r"(?im)^\s*FILE_LINE_LIMIT_REASON:\s*(\S.{9,})\s*$"
)

__all__ = [
    "CHECK_COMMAND",
    "CHECK_FILE_LINE_LIMIT",
    "CHECK_FILES_EXIST",
    "CHECK_FILES_MISSING",
    "CHECK_GIT_DIFF_CONTAINS",
    "CHECK_GIT_DIFF_NONEMPTY",
    "CHECK_OUTPUT_NONEMPTY",
    "CHECK_OUTPUT_REGEX",
    "DEFAULT_COMMAND_TIMEOUT",
    "KNOWN_CHECK_TYPES",
    "VerifyContext",
    "VerifyError",
    "VerifyResult",
    "all_passed",
    "changed_paths",
    "complete_verification",
    "ensure_git_repo",
    "fingerprint_untracked",
    "git_porcelain",
    "path_fingerprint",
    "run_acceptance",
    "run_check",
    "safe_join",
    "verify_step",
    # private helpers re-exported for existing tests
    "_git_has_commits",
]


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
