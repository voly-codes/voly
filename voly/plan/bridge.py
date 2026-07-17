"""Bridge multi-agent Assignments ↔ Plan steps (Rung B PR4)."""

from __future__ import annotations

from typing import Any, Iterable

from voly.config import PlanConfig
from voly.plan.types import (
    MODE_CHAT,
    MODE_EXECUTOR,
    AcceptanceCheck,
    Plan,
    PlanStep,
)


def assignment_step_id(idx: int, role: str) -> str:
    return f"{idx}:{role}"


def default_acceptance_for_role(
    role: str,
    mode: str,
    *,
    plan_cfg: PlanConfig | None = None,
) -> list[AcceptanceCheck]:
    """Build default acceptance checks for an A2A role.

    Defaults are conservative: chat requires non-empty output when configured;
    executor git-diff and tester command are opt-in via PlanConfig.
    """
    cfg = plan_cfg or PlanConfig()
    role_key = (role or "").strip().lower()
    mode_key = (mode or MODE_CHAT).strip().lower()
    checks: list[AcceptanceCheck] = []

    if mode_key == MODE_CHAT and cfg.chat_require_output:
        checks.append(AcceptanceCheck(type="output_nonempty"))

    if mode_key == MODE_EXECUTOR and cfg.executor_require_git_diff:
        checks.append(AcceptanceCheck(type="git_diff_nonempty"))

    if mode_key == MODE_EXECUTOR and cfg.executor_file_line_limit > 0:
        checks.append(
            AcceptanceCheck(
                type="file_line_limit",
                max_lines=cfg.executor_file_line_limit,
                approved_max_lines=max(
                    cfg.executor_file_line_limit,
                    cfg.architect_approved_file_line_limit,
                ),
            )
        )

    if role_key == "tester" and (cfg.tester_command or "").strip():
        checks.append(
            AcceptanceCheck(
                type="command",
                run=cfg.tester_command.strip(),
                expect_exit=0,
            )
        )
    return checks


def assignments_to_plan(
    task: str,
    assignments: Iterable[Any],
    *,
    plan_id: str,
    task_id: str = "",
    cwd: str = "",
    plan_cfg: PlanConfig | None = None,
    role_modes: dict[int, str] | None = None,
) -> Plan:
    """Convert lead ``Assignment`` list into a runnable Plan.

    ``role_modes`` maps assignment idx → ``chat|executor`` (from hybrid resolve).
    ``depends_on`` on assignments are integer indices into the same list.
    """
    items = list(assignments)
    by_idx = {int(a.idx): a for a in items}
    steps: list[PlanStep] = []

    for a in items:
        idx = int(a.idx)
        role = str(getattr(a, "role", "developer") or "developer")
        mode = (role_modes or {}).get(idx) or getattr(a, "mode", "") or MODE_CHAT
        if mode not in (MODE_CHAT, MODE_EXECUTOR):
            mode = MODE_CHAT
        dep_ids: list[str] = []
        for d in getattr(a, "depends_on", None) or []:
            try:
                di = int(d)
            except (TypeError, ValueError):
                continue
            prior = by_idx.get(di)
            if prior is not None:
                dep_ids.append(
                    assignment_step_id(di, str(getattr(prior, "role", "agent")))
                )

        sid = assignment_step_id(idx, role)
        acceptance = default_acceptance_for_role(role, mode, plan_cfg=plan_cfg)
        steps.append(
            PlanStep(
                id=sid,
                role=role,
                mode=mode,
                depends_on=dep_ids,
                acceptance=acceptance,
                task=str(getattr(a, "description", "") or task),
                executor=str(getattr(a, "executor", "") or ""),
                model=str(getattr(a, "model", "") or ""),
                provider=str(getattr(a, "provider", "") or ""),
                tier=str(getattr(a, "tier", "") or ""),
            )
        )

    return Plan(
        plan_id=plan_id or f"a2a-{task_id or 'run'}",
        task_id=task_id,
        cwd=cwd or "",
        task=task[:2000] if task else "",
        steps=steps,
    )


def plan_gates_enabled(plan_cfg: PlanConfig | None) -> bool:
    if plan_cfg is None:
        return False
    if not plan_cfg.enabled:
        return False
    if not getattr(plan_cfg, "a2a_attach", True):
        return False
    mode = (plan_cfg.mode or "off").lower()
    return mode in ("shadow", "active")


def sync_assignment_plan_fields(assignment: Any, step: PlanStep) -> None:
    """Copy plan step status / verify outcome onto Assignment for telemetry/UI."""
    assignment.plan_status = step.status
    if step.verify_log:
        assignment.plan_verify_ok = all(bool(e.get("ok")) for e in step.verify_log)
    else:
        assignment.plan_verify_ok = None if not step.acceptance else True
    if step.error and not getattr(assignment, "error", ""):
        assignment.error = step.error
