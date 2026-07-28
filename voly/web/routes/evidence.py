"""Local EvidenceRecord inspection and explicit human-feedback API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from voly.evidence.store import (
    MAX_FEEDBACK_COMMENT_CHARS,
    EvidenceStore,
    validate_task_id,
)

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class FeedbackRequest(BaseModel):
    kind: Literal[
        "accepted",
        "edited",
        "major_rewrite",
        "reverted",
        "pr_rejected",
        "manual_fix",
    ]
    comment: str = Field(default="", max_length=MAX_FEEDBACK_COMMENT_CHARS)


def _store(request: Request) -> EvidenceStore:
    config = request.app.state.app.config
    store_dir = config.evidence.store_dir if config else ".voly/evidence"
    return EvidenceStore(store_dir)


def _safe_task_id(task_id: str) -> str:
    try:
        return validate_task_id(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{task_id}")
def get_evidence(task_id: str, request: Request) -> dict:
    """Return one complete local evidence record."""
    safe_task_id = _safe_task_id(task_id)
    record = _store(request).load(safe_task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="evidence record not found")
    return record.to_dict()


@router.post("/{task_id}/feedback")
def add_evidence_feedback(
    task_id: str,
    body: FeedbackRequest,
    request: Request,
) -> dict:
    """Append explicit human feedback to an existing local record."""
    safe_task_id = _safe_task_id(task_id)
    try:
        record = _store(request).add_human_feedback(
            safe_task_id,
            body.kind,
            source="api",
            comment=body.comment,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="evidence record not found",
        ) from exc
    return {
        "task_id": record.task_id,
        "feedback": record.human_feedback[-1].__dict__,
    }
