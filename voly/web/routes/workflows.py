"""Routes: /api/workflows (Phase 5 of docs/proposals/agent-workflow-sdk.md).

REST surface for the Workflow SDK: validate a document without running it,
run/resume one via SSE (node lifecycle events), list/get persisted
sdk_workflow Plans, and decide a paused approval node. Every endpoint
delegates to the existing voly.sdk / voly.plan machinery — no new state
machine, no provider client here.

Node-lifecycle events are produced by polling the same PlanStore-persisted
Plan the CLI's ``voly workflow show`` and Python's ``Workflow.resume()``
read (see "UI and SDK disagree" mitigation in the proposal's Risks table:
"both read the same stored Plan and event stream") — not a push channel
threaded through PlanRunner's internals. This mirrors ``/api/run``'s existing
heartbeat-polling SSE pattern in ``voly/web/routes/run.py``, at Phase 3's
per-step persistence granularity instead of whole-task granularity.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Workflow runs are I/O-bound (chat/executor calls), like /api/run's pool —
# a small fixed pool queues concurrent SSE requests behind whatever is
# already running rather than spawning unbounded threads.
_THREAD_POOL = ThreadPoolExecutor(
    max_workers=int(os.environ.get("VOLY_WORKFLOW_POOL_WORKERS", "8"))
)
_POLL_INTERVAL_SECONDS = 1.0

# PlanStep status -> AG-UI lifecycle event name (proposal: "node queued/
# running/verifying/completed/failed"). "done" (mid-transition, about to be
# verified) is folded into "running" — it is never observably stable long
# enough to matter to a UI poller.
_STATUS_EVENT = {
    "pending": "queued",
    "running": "running",
    "done": "running",
    "verifying": "verifying",
    "verified": "completed",
    "failed": "failed",
    "skipped": "completed",
}


class WorkflowDoc(BaseModel):
    """Same shape ``voly.sdk.loader.load_workflow_dict`` accepts — see
    ``docs/backend/sdk.md``'s Workflow-document schema."""

    name: str = "workflow"
    task: str = ""
    cwd: str | None = None
    nodes: list[dict[str, Any]]


class WorkflowRunRequest(WorkflowDoc):
    mode: Literal["shadow", "active"] | None = None
    timeout_seconds: float | None = None


class WorkflowResumeRequest(BaseModel):
    mode: Literal["shadow", "active"] | None = None
    timeout_seconds: float | None = None


class WorkflowApprovalFeedback(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = ""


def _config(request: Request) -> Any:
    return request.app.state.app.config


def _store_dir(config: Any) -> str:
    return getattr(getattr(config, "plan", None), "store_dir", ".voly/plans")


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def _plan_summary(plan: Any) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "workflow_name": plan.metadata.get("workflow_name", ""),
        "status": plan.status,
        "cost_usd": round(sum(s.cost_usd for s in plan.steps), 6),
        "nodes": len(plan.steps),
        "verified": sum(1 for s in plan.steps if s.status == "verified"),
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


@router.post("/validate")
def validate_workflow(doc: WorkflowDoc, request: Request) -> dict[str, Any]:
    """Compile a Workflow document without running it."""
    from voly.sdk.loader import load_workflow_dict
    from voly.sdk.workflow import WorkflowError

    try:
        workflow, task, cwd = load_workflow_dict(doc.model_dump(), config=_config(request))
        plan = workflow.compile(task, cwd=cwd)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": workflow.name, "node_ids": [s.id for s in plan.steps]}


@router.get("")
def list_workflows(request: Request) -> dict[str, Any]:
    """List persisted Workflow-compiled Plans (``metadata.kind == 'sdk_workflow'``)."""
    from voly.plan.store import PlanStore

    config = _config(request)
    store = PlanStore(_store_dir(config))
    plans = [p for p in store.list() if p.metadata.get("kind") == "sdk_workflow"]
    return {"workflows": [_plan_summary(p) for p in plans]}


@router.get("/{plan_id}")
def get_workflow(plan_id: str, request: Request) -> dict[str, Any]:
    """Full persisted Plan for one workflow run — the same document
    ``voly workflow show --json-out`` prints."""
    from voly.plan.store import PlanStore

    config = _config(request)
    plan = PlanStore(_store_dir(config)).load(plan_id)
    if plan is None or plan.metadata.get("kind") != "sdk_workflow":
        raise HTTPException(status_code=404, detail="workflow not found")
    return plan.to_dict()


def _stream_plan_execution(config: Any, plan_id: str, submit: Any):
    """Return an SSE generator that submits ``submit()`` to the thread pool,
    polls ``PlanStore`` for ``plan_id`` and yields a ``node`` event for every
    observed PlanStep status change, then one final ``done`` event."""
    from voly.plan.store import PlanStore

    def generate():
        store = PlanStore(_store_dir(config))
        future: Future = submit()
        yield _sse("start", {"plan_id": plan_id})
        last_status: dict[str, str] = {}
        while True:
            current = store.load(plan_id)
            if current is not None:
                for step in current.steps:
                    if last_status.get(step.id) != step.status:
                        last_status[step.id] = step.status
                        yield _sse("node", {
                            "plan_id": plan_id,
                            "node_id": step.id,
                            "status": step.status,
                            "event": _STATUS_EVENT.get(step.status, step.status),
                            "role": step.role,
                            "cost_usd": step.cost_usd,
                            "duration_ms": step.duration_ms,
                        })
            if future.done():
                result = future.result()
                yield _sse("done", {
                    "plan_id": plan_id,
                    "success": result.success,
                    "status": result.plan.status,
                    "cost_usd": round(sum(s.cost_usd for s in result.plan.steps), 6),
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                })
                return
            time.sleep(_POLL_INTERVAL_SECONDS)

    return generate


@router.post("/run")
def run_workflow(req: WorkflowRunRequest, request: Request) -> StreamingResponse:
    """Compile and run a Workflow document, streaming node lifecycle events."""
    from voly.plan.runner import PlanRunner
    from voly.sdk.loader import load_workflow_dict
    from voly.sdk.workflow import WorkflowError

    config = _config(request)
    doc = req.model_dump(exclude={"mode", "timeout_seconds"})
    try:
        workflow, task, cwd = load_workflow_dict(doc, config=config)
        plan = workflow.compile(task, cwd=cwd)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def submit() -> Future:
        runner = PlanRunner(config, emit_event=False)
        return _THREAD_POOL.submit(
            runner.run, plan, mode=req.mode, cwd=cwd, timeout_seconds=req.timeout_seconds
        )

    generate = _stream_plan_execution(config, plan.plan_id, submit)
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{plan_id}/resume")
def resume_workflow(
    plan_id: str, body: WorkflowResumeRequest, request: Request
) -> StreamingResponse:
    """Continue a paused/interrupted persisted workflow, streaming node
    lifecycle events for the remaining run."""
    from voly.plan.runner import PlanRunner
    from voly.plan.store import PlanStore

    config = _config(request)
    existing = PlanStore(_store_dir(config)).load(plan_id)
    if existing is None or existing.metadata.get("kind") != "sdk_workflow":
        raise HTTPException(status_code=404, detail="workflow not found")

    def submit() -> Future:
        runner = PlanRunner(config, emit_event=False)
        return _THREAD_POOL.submit(
            runner.resume, plan_id, mode=body.mode, timeout_seconds=body.timeout_seconds
        )

    generate = _stream_plan_execution(config, plan_id, submit)
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{plan_id}/nodes/{node_id}/decide")
def decide_workflow_node(
    plan_id: str, node_id: str, body: WorkflowApprovalFeedback, request: Request
) -> dict[str, Any]:
    """Approve/reject a paused ``approval=True`` node — the same
    idempotent/fail-closed contract ``/api/decisions/{plan_id}/feedback``
    uses for business decisions, generalized by ``voly.plan.approval``."""
    from voly.plan.approval import ApprovalConflictError, ApprovalError, decide
    from voly.plan.store import PlanStore
    from voly.plan.types import PlanValidationError

    config = _config(request)
    store = PlanStore(_store_dir(config))
    try:
        result = decide(store, plan_id, node_id, body.decision, comment=body.comment)
    except (FileNotFoundError, PlanValidationError) as exc:
        raise HTTPException(status_code=404, detail=str(exc) or "workflow not found") from exc
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"decision": result.decision, "changed": result.changed, "plan": result.plan.to_dict()}
