"""Business Decision orchestration over the existing Plan FSM."""

from __future__ import annotations

import time
from dataclasses import dataclass

from voly.plan.engine import PlanEngine
from voly.plan.store import PlanStore
from voly.plan.types import (
    FAILED, PENDING, VERIFIED, VERIFYING, AcceptanceCheck, Plan, PlanStep,
    MODE_BUSINESS,
)
from voly.sensing.schema import Option, Signal


@dataclass(frozen=True)
class DecisionResult:
    plan: Plan
    decision: str
    changed: bool


class DecisionConflictError(ValueError):
    pass


class DecisionService:
    def __init__(self, store: PlanStore) -> None:
        self.store = store
        self.engine = PlanEngine()

    def create(self, signal: Signal, option: Option) -> Plan:
        plan_id = option.option_id
        existing = self.store.load(plan_id)
        if existing is not None:
            return existing
        plan = Plan(
            plan_id=plan_id,
            task=option.title,
            status="running",
            metadata={
                "kind": "business_decision",
                "signal_id": signal.signal_id,
                "option_id": option.option_id,
                "urgency": option.urgency,
                "action_kind": option.action_kind,
                "rationale": option.rationale,
                "estimated_impact": option.estimated_impact,
                "decision": "pending",
            },
            steps=[
                PlanStep(
                    id="approve-option", role="reviewer", mode=MODE_BUSINESS,
                    status=VERIFYING, task=option.title,
                    acceptance=[AcceptanceCheck(type="human_review")],
                ),
                PlanStep(
                    id="execute-action", role="operator", mode=MODE_BUSINESS,
                    status=PENDING, depends_on=["approve-option"], task=option.title,
                    acceptance=[AcceptanceCheck(type="action_succeeded")],
                ),
            ],
        )
        self.store.save(plan)
        return plan

    def decide(self, plan_id: str, decision: str, *, comment: str = "") -> DecisionResult:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        plan = self.store.load(plan_id)
        if plan is None or plan.metadata.get("kind") != "business_decision":
            raise FileNotFoundError(plan_id)
        desired = "approved" if decision == "approve" else "rejected"
        current = str(plan.metadata.get("decision") or "pending")
        if current == desired:
            return DecisionResult(plan, desired, False)
        if current != "pending":
            raise DecisionConflictError(f"decision already recorded as {current}")
        step = plan.get_step("approve-option")
        self.engine.transition(plan, step.id, VERIFIED if decision == "approve" else FAILED,
                               error="rejected by human" if decision == "reject" else "")
        plan.metadata.update({
            "decision": desired,
            "decision_comment": comment[:2000],
            "decided_at": time.time(),
        })
        if decision == "reject":
            plan.status = "failed"
        self.store.save(plan)
        return DecisionResult(plan, desired, True)

    def list(self) -> list[Plan]:
        return [p for p in self.store.list() if p.metadata.get("kind") == "business_decision"]
