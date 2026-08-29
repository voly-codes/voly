"""Generic human_review approval gate (voly/plan/approval.py).

Resolves the gap flagged in docs/backend/sdk.md: Phase 2's Workflow approval
nodes need a human_review mechanism that works on any Plan, not only
Signal/Option "business_decision" Plans (voly.decisions.DecisionService).
"""

from __future__ import annotations

import pytest

from voly.config import PlanConfig, VOLYConfig
from voly.plan import (
    FAILED,
    MODE_CHAT,
    PENDING,
    PLAN_COMPLETED,
    PLAN_RUNNING,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    ApprovalConflictError,
    ApprovalError,
    PlanRunner,
    PlanStep,
    PlanStore,
    create_plan,
    decide_human_review,
)


def _config(tmp_path) -> VOLYConfig:
    cfg = VOLYConfig()
    cfg.plan = PlanConfig(enabled=True, mode="active", store_dir=str(tmp_path / "plans"))
    cfg.telemetry.enabled = False
    cfg.default_cwd = str(tmp_path)
    return cfg


def _approval_plan(plan_id: str, cwd: str):
    return create_plan(
        plan_id,
        [
            PlanStep(
                id="approve", role="reviewer", mode=MODE_CHAT, status=VERIFYING,
                acceptance=[AcceptanceCheck(type="human_review")],
            ),
            PlanStep(
                id="notify", role="operator", mode=MODE_CHAT,
                depends_on=["approve"], task="say done",
            ),
        ],
        cwd=cwd,
    )


def _chat_fn(step, plan, instruction):
    return True, "notified", ""


def test_runner_parks_a_pre_seeded_human_review_step_instead_of_failing_the_plan(tmp_path) -> None:
    """A step pre-seeded at `verifying` (the convention voly.decisions also
    uses — an approval gate has no task of its own to execute) must never be
    picked as runnable and must never turn the plan `failed`."""
    cfg = _config(tmp_path)
    plan = _approval_plan("wf-1", str(tmp_path))
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)

    result = PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="active")

    assert result.success is False
    assert result.plan.status == PLAN_RUNNING
    assert result.plan.error == ""
    assert result.plan.get_step("approve").status == VERIFYING
    assert result.plan.get_step("notify").status == PENDING


def test_verify_parks_a_step_that_reaches_verifying_through_execution(tmp_path) -> None:
    """Exercises PlanRunner._verify()'s short-circuit directly: a step that
    executes normally (pending → running → done → verifying) and only then
    hits a human_review check must park in `verifying` with a populated
    verify_log — not fail, and not force-verify."""
    cfg = _config(tmp_path)
    plan = create_plan(
        "wf-live",
        [PlanStep(id="draft", mode=MODE_CHAT, task="draft a proposal",
                   acceptance=[AcceptanceCheck(type="human_review")])],
        cwd=str(tmp_path),
    )
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)

    result = PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="active")

    step = result.plan.get_step("draft")
    assert step.status == VERIFYING
    assert step.verify_log
    assert step.verify_log[0]["ok"] is False
    assert "voly.plan.approval" in step.verify_log[0]["message"]
    assert result.plan.status == PLAN_RUNNING


def test_shadow_mode_never_bypasses_human_review(tmp_path) -> None:
    """Shadow mode's normal soft-open (force any failed check to verified) must
    not apply to human_review — a governance gate is not a quality signal."""
    cfg = _config(tmp_path)
    plan = create_plan(
        "wf-shadow",
        [PlanStep(id="approve", mode=MODE_CHAT, status=VERIFYING,
                   acceptance=[AcceptanceCheck(type="human_review")])],
        cwd=str(tmp_path),
    )
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)

    result = PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="shadow")

    assert result.plan.get_step("approve").status == VERIFYING


def test_decide_human_review_approve_unblocks_dependent_step(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = _approval_plan("wf-2", str(tmp_path))
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)
    runner = PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False)
    runner.run(plan, mode="active")

    approved = decide_human_review(store, "wf-2", "approve", "approve", comment="lgtm")
    assert approved.decision == "approved"
    assert approved.changed is True
    assert approved.plan.get_step("approve").status == VERIFIED

    resumed = runner.resume("wf-2")
    assert resumed.success is True
    assert resumed.plan.status == PLAN_COMPLETED
    assert resumed.plan.get_step("notify").status == VERIFIED


def test_decide_human_review_reject_keeps_dependent_blocked(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = _approval_plan("wf-3", str(tmp_path))
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)
    PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="active")

    rejected = decide_human_review(store, "wf-3", "approve", "reject")
    assert rejected.decision == "rejected"
    assert rejected.plan.get_step("approve").status == FAILED
    assert rejected.plan.get_step("notify").status == PENDING


def test_decide_human_review_is_idempotent_on_repeat(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = _approval_plan("wf-4", str(tmp_path))
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)
    PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="active")

    first = decide_human_review(store, "wf-4", "approve", "approve")
    second = decide_human_review(store, "wf-4", "approve", "approve")
    assert first.changed is True
    assert second.changed is False


def test_decide_human_review_fails_closed_on_conflicting_decision(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = _approval_plan("wf-5", str(tmp_path))
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)
    PlanRunner(cfg, chat_fn=_chat_fn, emit_event=False).run(plan, mode="active")

    decide_human_review(store, "wf-5", "approve", "approve")
    with pytest.raises(ApprovalConflictError):
        decide_human_review(store, "wf-5", "approve", "reject")


def test_decide_human_review_fails_closed_before_step_reaches_verifying(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = create_plan(
        "wf-6",
        [PlanStep(id="approve", mode=MODE_CHAT, acceptance=[AcceptanceCheck(type="human_review")])],
        cwd=str(tmp_path),
    )
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)

    with pytest.raises(ApprovalConflictError):
        decide_human_review(store, "wf-6", "approve", "approve")


def test_decide_human_review_rejects_step_without_the_check(tmp_path) -> None:
    cfg = _config(tmp_path)
    plan = create_plan(
        "wf-7", [PlanStep(id="only", mode=MODE_CHAT, task="hi")], cwd=str(tmp_path),
    )
    store = PlanStore(cfg.plan.store_dir)
    store.save(plan)

    with pytest.raises(ApprovalError):
        decide_human_review(store, "wf-7", "only", "approve")


def test_decide_human_review_rejects_unknown_plan(tmp_path) -> None:
    cfg = _config(tmp_path)
    store = PlanStore(cfg.plan.store_dir)
    with pytest.raises(FileNotFoundError):
        decide_human_review(store, "does-not-exist", "approve", "approve")
