"""Routes: /api/status, /api/tasks/*"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from voly.web import service

router = APIRouter()

_JSON_GLOB = "*.json"
_ARTIFACT_NOT_FOUND = "Artifact not found"


def _state(request: Request):
    return request.app.state.app


@router.get("/api/status")
def get_status(request: Request) -> dict[str, Any]:
    s = _state(request)
    events = list(s.ev_dir.glob(_JSON_GLOB)) if s.ev_dir.exists() else []
    cfg_info: dict[str, Any] = {}
    if s.config:
        cfg_info["marketplace_url"] = bool(
            getattr(getattr(s.config, "registry", None), "marketplace_url", "")
        )
        cfg_info["spend_url"] = bool(
            getattr(getattr(s.config, "spend", None), "remote_url", "")
        )
    default_cwd = ""
    if s.config:
        default_cwd = (
            getattr(s.config, "default_cwd", "")
            or os.environ.get("VOLY_PROJECT_CWD", "")
        )
    return {
        "version": "0.1.0",
        "tasks_count": len(events),
        "events_dir": str(s.ev_dir),
        "default_cwd": default_cwd,
        "cf": cfg_info,
    }


@router.get("/api/tasks")
def list_tasks(
    request: Request, limit: int = 100, agent: str = "", status: str = ""
) -> list[dict[str, Any]]:
    return service.list_tasks(
        _state(request).ev_dir, limit=limit, agent=agent, status=status
    )


@router.get("/api/tasks/stats/summary")
def get_summary(request: Request) -> dict[str, Any]:
    return service.task_stats(_state(request).ev_dir)


@router.get("/api/tasks/stream")
async def stream_tasks(request: Request) -> StreamingResponse:
    """SSE endpoint: pushes task list diffs to connected clients."""
    ev_dir = _state(request).ev_dir
    seen: dict[str, float] = {}

    async def generator():
        nonlocal seen
        # The first scan is a snapshot of what already exists — emitted as
        # type "init" so the UI does not badge historical tasks as new
        # (also on EventSource auto-reconnects, which restart this generator).
        first = True
        try:
            while True:
                if await request.is_disconnected():
                    break

                current: dict[str, float] = {}
                new_tasks: list[dict[str, Any]] = []
                if ev_dir.exists():
                    for f in ev_dir.glob(_JSON_GLOB):
                        current[f.stem] = f.stat().st_mtime
                        if f.stem not in seen:
                            try:
                                d = json.loads(f.read_text())
                                d["_mtime"] = f.stat().st_mtime
                                new_tasks.append(d)
                            except Exception:
                                pass

                if new_tasks:
                    msg_type = "init" if first else "new"
                    yield f"data: {json.dumps({'type': msg_type, 'tasks': new_tasks})}\n\n"
                    seen = current
                else:
                    # Heartbeat every 5s to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                first = False

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/tasks/{task_id}", responses={404: {"description": "Task not found"}})
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    task = service.get_task(_state(request).ev_dir, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get(
    "/api/tasks/{task_id}/artifacts/{name}",
    responses={404: {"description": "Artifact not found"}},
)
def get_task_artifact(task_id: str, name: str, request: Request) -> FileResponse:
    if "/" in name or "\\" in name or not name.endswith(".png"):
        raise HTTPException(status_code=404, detail=_ARTIFACT_NOT_FOUND)
    base = (_state(request).ev_dir.parent / "pxpipe" / "images" / task_id).resolve()
    path = (base / name).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail=_ARTIFACT_NOT_FOUND) from None
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=_ARTIFACT_NOT_FOUND)
    return FileResponse(path, media_type="image/png")
