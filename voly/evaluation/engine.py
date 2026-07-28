"""Deterministic post-run Eval Engine."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from voly.evaluation.markdown import validate_markdown_links
from voly.evaluation.schema import (
    EvalCheckResult,
    EvalPolicy,
    EvalReport,
    EvalRequirement,
)
from voly.evaluation.security import scan_changed_security
from voly.evaluation.testing import validate_test_artifacts
from voly.evaluation.trajectory import evaluate_trajectory
from voly.plan.types import AcceptanceCheck
from voly.plan.verify_checks import run_check, run_command_argv
from voly.plan.verify_types import VerifyContext


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(
    requirement: EvalRequirement,
    status: str,
    message: str,
    *,
    started: float,
    detail: dict[str, Any] | None = None,
    result_id: str | None = None,
) -> EvalCheckResult:
    return EvalCheckResult(
        id=result_id or requirement.id,
        evaluator=requirement.evaluator,
        status=status,
        required=requirement.required,
        message=message,
        duration_ms=(time.monotonic() - started) * 1000,
        detail=detail or {},
    )


def _final_state(checks: list[EvalCheckResult]) -> str:
    required = [check for check in checks if check.required]
    if any(check.status in {"failed", "error"} for check in required):
        return "soft_failure"
    if not required or any(
        check.status in {"pending", "skipped"} for check in required
    ):
        return "partial_success"
    return "verified_success"


def evaluate_run(
    policy: EvalPolicy,
    *,
    result: Any,
    baseline: Any,
    cwd: str,
    git_before: dict[str, str],
    git_after: dict[str, str],
    files_touched: list[str],
    command_timeout_seconds: float = 120.0,
) -> EvalReport:
    """Evaluate one completed executor run without changing its visible result."""
    started_at = _now()
    checks: list[EvalCheckResult] = []
    context = VerifyContext(
        cwd=cwd,
        output=str(getattr(result, "output", "") or ""),
        files_touched=files_touched,
        git_before=git_before,
        git_after=git_after,
        command_timeout=max(1.0, float(command_timeout_seconds)),
        scope_pytest_to_files=False,
    )

    for requirement in policy.requirements:
        started = time.monotonic()
        if requirement.evaluator == "executor_success":
            ok = bool(getattr(result, "success", False))
            checks.append(
                _result(
                    requirement,
                    "passed" if ok else "failed",
                    "executor reported success" if ok else "executor failed",
                    started=started,
                )
            )
            if not ok:
                break
        elif requirement.evaluator == "safety_policy":
            metadata = getattr(result, "metadata", None) or {}
            violation = str(metadata.get("safety_violation") or "")
            hard = bool(violation and not metadata.get("safety_soft"))
            checks.append(
                _result(
                    requirement,
                    "failed" if hard else "passed",
                    violation or "no safety-policy violation",
                    started=started,
                    detail={"soft_rollback": bool(metadata.get("safety_soft"))},
                )
            )
        elif requirement.evaluator == "file_changes":
            verified = run_check(AcceptanceCheck(type="git_diff_nonempty"), context)
            checks.append(
                _result(
                    requirement,
                    "passed" if verified.ok else "failed",
                    verified.message,
                    started=started,
                    detail=verified.detail,
                )
            )
        elif requirement.evaluator == "trajectory_policy":
            ok, message, detail = evaluate_trajectory(result)
            checks.append(
                _result(
                    requirement,
                    "passed" if ok else "failed",
                    message,
                    started=started,
                    detail=detail,
                )
            )
        elif requirement.evaluator == "baseline_replay":
            baseline_checks = list(getattr(baseline, "checks", None) or [])
            if not baseline_checks:
                checks.append(
                    _result(
                        requirement,
                        "skipped",
                        "no deterministic baseline commands to replay",
                        started=started,
                    )
                )
                continue
            for original in baseline_checks:
                check_started = time.monotonic()
                result_id = f"{requirement.id}:{original.name}"
                if original.status != "passed":
                    checks.append(
                        _result(
                            requirement,
                            "skipped",
                            f"baseline status was {original.status}",
                            started=check_started,
                            result_id=result_id,
                            detail={"baseline_status": original.status},
                        )
                    )
                    continue
                if not original.argv:
                    checks.append(
                        _result(
                            requirement,
                            "skipped",
                            "legacy baseline has no exact argv",
                            started=check_started,
                            result_id=result_id,
                        )
                    )
                    continue
                verified = run_command_argv(list(original.argv), context)
                checks.append(
                    _result(
                        requirement,
                        "passed" if verified.ok else "failed",
                        verified.message,
                        started=check_started,
                        result_id=result_id,
                        detail=verified.detail,
                    )
                )
        elif requirement.evaluator == "markdown_links":
            ok, message, detail = validate_markdown_links(cwd, files_touched)
            checks.append(
                _result(
                    requirement,
                    "passed" if ok else "failed",
                    message,
                    started=started,
                    detail=detail,
                )
            )
        elif requirement.evaluator == "test_artifacts":
            ok, message, detail = validate_test_artifacts(files_touched)
            checks.append(
                _result(
                    requirement,
                    "passed" if ok else "failed",
                    message,
                    started=started,
                    detail=detail,
                )
            )
        elif requirement.evaluator == "changed_security_scan":
            status, message, detail = scan_changed_security(cwd, files_touched)
            checks.append(
                _result(
                    requirement,
                    status,
                    message,
                    started=started,
                    detail=detail,
                )
            )
        elif requirement.evaluator == "human_review":
            checks.append(
                _result(
                    requirement,
                    "pending",
                    "explicit human review required",
                    started=started,
                )
            )
        else:
            checks.append(
                _result(
                    requirement,
                    "error",
                    f"unknown evaluator: {requirement.evaluator}",
                    started=started,
                )
            )

    return EvalReport(
        policy_id=policy.id,
        policy_version=policy.version,
        state=_final_state(checks),
        started_at=started_at,
        completed_at=_now(),
        checks=checks,
    )


def apply_human_feedback(report: EvalReport, kind: str) -> bool:
    """Resolve pending human-review checks from explicit feedback."""
    review_checks = [
        check for check in report.checks if check.evaluator == "human_review"
    ]
    if not review_checks:
        return False
    accepted = kind == "accepted"
    for check in review_checks:
        check.status = "passed" if accepted else "failed"
        check.message = f"explicit human feedback: {kind}"
        check.detail = {"kind": kind}
    report.state = _final_state(report.checks)
    report.completed_at = _now()
    return True
