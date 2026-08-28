from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from voly.decisions import DecisionConflictError, DecisionService
from voly.plan.store import PlanStore

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DecisionFeedback(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=2000)


def _service(request: Request) -> DecisionService:
    config = request.app.state.app.config
    path = config.plan.store_dir if config else ".voly/plans"
    return DecisionService(PlanStore(path), config=config)


@router.get("")
def list_decisions(request: Request) -> dict:
    return {"decisions": [plan.to_dict() for plan in _service(request).list()]}


@router.get("/{plan_id}")
def get_decision(plan_id: str, request: Request) -> dict:
    plan = _service(request).store.load(plan_id)
    if plan is None or plan.metadata.get("kind") != "business_decision":
        raise HTTPException(status_code=404, detail="decision not found")
    return plan.to_dict()


@router.post("/{plan_id}/feedback")
def decide(plan_id: str, body: DecisionFeedback, request: Request) -> dict:
    try:
        result = _service(request).decide(plan_id, body.decision, comment=body.comment)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="decision not found") from exc
    except DecisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"decision": result.decision, "changed": result.changed, "plan": result.plan.to_dict()}


@router.post("/{plan_id}/execute")
def execute_decision(plan_id: str, request: Request) -> dict:
    try:
        plan = _service(request).execute(plan_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="decision not found") from exc
    except (DecisionConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return plan.to_dict()
