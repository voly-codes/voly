"""Generic human-review approval gate for any Plan step.

``voly.decisions.DecisionService.decide()`` already implements this exact
idempotent-approve / fail-closed-on-conflict contract, but it is scoped to
Signal/Option "business_decision" Plans (see ``docs/backend/decisions.md``).
This module is the same contract generalized to any Plan/step pair that
declares a ``human_review`` acceptance check — the primitive a future
``Workflow`` approval node (docs/proposals/agent-workflow-sdk.md Phase 2)
needs, without a second implementation of the FSM edges
``DecisionService``/``PlanEngine`` already got right.

State is read directly off the step's status rather than a parallel
``metadata["decision"]`` field: a ``human_review`` step can only ever reach
``verified``/``failed`` through this module's ``decide()`` — see
``PlanRunner._verify()``, which deliberately never transitions such a step on
its own (neither on success nor, critically, under `mode: shadow`'s normal
soft-open).
"""

from __future__ import annotations

from dataclasses import dataclass

from voly.plan.engine import PlanEngine
from voly.plan.store import PlanStore
from voly.plan.types import FAILED, VERIFIED, VERIFYING, Plan
from voly.plan.verify_types import CHECK_HUMAN_REVIEW


class ApprovalError(ValueError):
    """Usage error: unknown plan/step, or the step has no human_review check."""


class ApprovalConflictError(ValueError):
    """The step is not awaiting review, or already carries the other decision."""


@dataclass(frozen=True)
class ApprovalResult:
    plan: Plan
    decision: str  # "approved" | "rejected"
    changed: bool


def _require_human_review_step(plan: Plan, step_id: str):
    step = plan.get_step(step_id)
    if not any(c.type == CHECK_HUMAN_REVIEW for c in step.acceptance):
        raise ApprovalError(
            f"step {step_id!r} on plan {plan.plan_id!r} has no human_review "
            "acceptance check"
        )
    return step


def decide(
    store: PlanStore,
    plan_id: str,
    step_id: str,
    decision: str,
    *,
    comment: str = "",
    engine: PlanEngine | None = None,
) -> ApprovalResult:
    """Approve/reject a ``human_review`` step on any Plan.

    Idempotent on a repeated identical decision (``changed=False``); fails
    closed with ``ApprovalConflictError`` on a conflicting one, or when the
    step has not yet reached ``verifying``.
    """
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")
    plan = store.load(plan_id)
    if plan is None:
        raise FileNotFoundError(plan_id)
    step = _require_human_review_step(plan, step_id)
    desired_status = VERIFIED if decision == "approve" else FAILED
    desired_label = "approved" if decision == "approve" else "rejected"

    if step.status == desired_status:
        return ApprovalResult(plan, desired_label, False)
    if step.status != VERIFYING:
        raise ApprovalConflictError(
            f"step {step_id!r} is {step.status!r}, not awaiting review "
            "(already decided the other way, or not yet reached verifying)"
        )

    eng = engine or PlanEngine()
    eng.transition(
        plan, step_id, desired_status,
        error="rejected by human" if decision == "reject" else "",
    )
    step.verify_log = [{
        "type": CHECK_HUMAN_REVIEW,
        "ok": decision == "approve",
        "message": f"human decision: {decision}" + (f" — {comment}" if comment else ""),
        "detail": {"comment": comment[:2000]},
    }]
    store.save(plan)
    return ApprovalResult(plan, desired_label, True)
