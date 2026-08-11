"""Routes: /api/runs — in-flight run records (RunTracker heartbeats).

`TaskEvent` files appear only when a run finishes; while an executor or a
multi-agent chain is working, its progress lives in ``.voly/runs/`` RunRecords
(heartbeat every ~10s). These endpoints let the UI show tasks that are still
running — including ones launched from the CLI — and drill into their state.

The reading and cancelling live in ``voly.web.service`` so the MCP facade
answers from exactly the same records.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from voly.web import service

router = APIRouter()


def _ev_dir(request: Request):
    return request.app.state.app.ev_dir


@router.get("/api/runs")
def list_runs(
    request: Request,
    active: bool = False,
    include_children: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    return service.list_runs(
        _ev_dir(request),
        active=active,
        include_children=include_children,
        limit=limit,
    )


@router.get("/api/runs/{task_id}", responses={404: {"description": "No run record for this task_id"}})
def get_run(request: Request, task_id: str) -> dict[str, Any]:
    rec = service.get_run(_ev_dir(request), task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no run record for {task_id}")
    return rec


@router.post(
    "/api/runs/{task_id}/cancel",
    responses={409: {"description": "Run is missing or no longer active"}},
)
def cancel_run(request: Request, task_id: str) -> dict[str, Any]:
    """Request cooperative stop before the workflow's next blocking turn."""
    if not service.cancel_run(_ev_dir(request), task_id):
        raise HTTPException(status_code=409, detail="run is missing or no longer active")
    return {
        "task_id": task_id,
        "cancel_requested": True,
        "interrupts_active_subprocess": False,
    }
