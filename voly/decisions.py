"""Business Decision orchestration over the existing Plan FSM."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from voly.plan.engine import PlanEngine
from voly.plan.store import PlanStore
from voly.plan.types import (
    FAILED,
    MODE_BUSINESS,
    PENDING,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    Plan,
    PlanStep,
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
    def __init__(self, store: PlanStore, config=None) -> None:  # type: ignore[no-untyped-def]
        self.store = store
        self.config = config
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
                "action_spec": dict(option.action_spec),
                "execution": "pending",
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
        self._learn(plan)
        return DecisionResult(plan, desired, True)

    def list(self) -> list[Plan]:
        return [p for p in self.store.list() if p.metadata.get("kind") == "business_decision"]

    def execute(self, plan_id: str, *, executor=None) -> Plan:  # type: ignore[no-untyped-def]
        plan = self.store.load(plan_id)
        if plan is None or plan.metadata.get("kind") != "business_decision":
            raise FileNotFoundError(plan_id)
        if plan.metadata.get("decision") != "approved":
            raise DecisionConflictError("decision must be approved before execution")
        state = str(plan.metadata.get("execution") or "pending")
        if state == "completed":
            return plan
        if state != "pending":
            raise DecisionConflictError(f"action execution already {state}")
        action = dict(plan.metadata.get("action_spec") or {})
        if action.get("kind") not in {"http_call", "notify"}:
            raise ValueError("approved action_spec.kind must be http_call or notify")
        if self.config is None and executor is None:
            raise ValueError("business executor config is required")
        step = plan.get_step("execute-action")
        self.engine.transition(plan, step.id, "running")
        plan.metadata["execution"] = "running"
        self.store.save(plan)
        if executor is None:
            if action["kind"] == "notify":
                from voly.executor.notify import NotifyExecutor
                executor = NotifyExecutor(self.config)
            else:
                from voly.executor.http_action import HttpActionExecutor
                executor = HttpActionExecutor(self.config)
        result = executor.run(json.dumps({k: v for k, v in action.items() if k != "kind"}))
        if result.success:
            self.engine.transition(plan, step.id, "done")
            self.engine.transition(plan, step.id, "verifying")
            self.engine.transition(plan, step.id, "verified")
            plan.status = "completed"
            plan.metadata["execution"] = "completed"
        else:
            self.engine.transition(plan, step.id, "failed", error=result.error)
            plan.status = "failed"
            plan.metadata["execution"] = "failed"
        plan.metadata["action_report"] = dict(result.metadata.get("action_report") or {})
        self.store.save(plan)
        if self.config is not None:
            self._save_evidence(plan, result)
        self._learn(plan)
        return plan

    def _learn(self, plan: Plan) -> None:
        if self.config is None or not self.config.learning.enabled:
            return
        from voly.learning.instincts import InstinctStore
        InstinctStore(self.config.learning.store_path).ingest_business_decision(plan)

    def _save_evidence(self, plan: Plan, result) -> None:  # type: ignore[no-untyped-def]
        from datetime import datetime, timezone

        from voly.evidence.schema import (
            EvidenceOutcome,
            EvidenceRecord,
            ExecutionBundle,
            RepositoryBaseline,
        )
        from voly.evidence.store import EvidenceStore

        EvidenceStore(self.config.evidence.store_dir).save(EvidenceRecord(
            task_id=plan.plan_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            task_type="business_action",
            task_fingerprint=str(plan.metadata.get("option_id") or plan.plan_id),
            baseline=RepositoryBaseline(captured_at=datetime.now(timezone.utc).isoformat(), health="not_applicable"),
            execution=ExecutionBundle(agent="operator", executor=str((plan.metadata.get("action_spec") or {}).get("kind") or "business-action")),
            outcome=EvidenceOutcome(success=result.success, state="passed" if result.success else "failed", error_class="" if result.success else "business_action"),
            action_report=dict(result.metadata.get("action_report") or {}),
        ))
