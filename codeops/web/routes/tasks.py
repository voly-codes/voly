"""Routes: /api/status, /api/tasks/*"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


def _state(request: Request):
    return request.app.state.app


def _load_events(ev_dir: pathlib.Path) -> list[dict[str, Any]]:
    if not ev_dir.exists():
        return []
    out = []
    for f in ev_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            d["_mtime"] = f.stat().st_mtime
            out.append(d)
        except Exception:
            pass
    return sorted(out, key=lambda x: x.get("_mtime", 0), reverse=True)


@router.get("/api/status")
def get_status(request: Request) -> dict[str, Any]:
    s = _state(request)
    events = list(s.ev_dir.glob("*.json")) if s.ev_dir.exists() else []
    cfg_info: dict[str, Any] = {}
    if s.config:
        cfg_info["marketplace_url"] = bool(
            getattr(getattr(s.config, "registry", None), "marketplace_url", "")
        )
        cfg_info["spend_url"] = bool(
            getattr(getattr(s.config, "spend", None), "remote_url", "")
        )
    return {
        "version": "0.1.0",
        "tasks_count": len(events),
        "events_dir": str(s.ev_dir),
        "cf": cfg_info,
    }


@router.get("/api/tasks")
def list_tasks(
    request: Request, limit: int = 100, agent: str = "", status: str = ""
) -> list[dict[str, Any]]:
    tasks = _load_events(_state(request).ev_dir)
    if agent:
        tasks = [t for t in tasks if t.get("agent") == agent]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return tasks[:limit]


@router.get("/api/tasks/stats/summary")
def get_summary(request: Request) -> dict[str, Any]:
    tasks = _load_events(_state(request).ev_dir)
    if not tasks:
        return {
            "total_tasks": 0, "total_cost_usd": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_saved_tokens": 0, "avg_duration_ms": 0,
            "by_agent": {}, "by_status": {}, "by_model": {},
        }

    total_cost = 0.0
    total_in = total_out = total_saved = 0
    durations: list[float] = []
    by_agent: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_model: dict[str, int] = {}

    for t in tasks:
        total_cost += t.get("cost_usd") or 0
        tok = t.get("tokens") or {}
        total_in += tok.get("input") or 0
        total_out += tok.get("output") or 0
        total_saved += (tok.get("saved_rtk") or 0) + (tok.get("saved_headroom") or 0)
        if d := t.get("duration_ms"):
            durations.append(d)
        key_agent = t.get("agent") or "unknown"
        key_status = t.get("status") or "unknown"
        key_model = t.get("model") or "unknown"
        by_agent[key_agent] = by_agent.get(key_agent, 0) + 1
        by_status[key_status] = by_status.get(key_status, 0) + 1
        by_model[key_model] = by_model.get(key_model, 0) + 1

    return {
        "total_tasks": len(tasks),
        "total_cost_usd": round(total_cost, 6),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_saved_tokens": total_saved,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "by_agent": by_agent,
        "by_status": by_status,
        "by_model": by_model,
    }


@router.get("/api/tasks/stream")
async def stream_tasks(request: Request) -> StreamingResponse:
    """SSE endpoint: pushes task list diffs to connected clients."""
    ev_dir = _state(request).ev_dir
    seen: dict[str, float] = {}

    async def generator():
        nonlocal seen
        try:
            while True:
                if await request.is_disconnected():
                    break

                current: dict[str, float] = {}
                new_tasks: list[dict[str, Any]] = []
                if ev_dir.exists():
                    for f in ev_dir.glob("*.json"):
                        current[f.stem] = f.stat().st_mtime
                        if f.stem not in seen:
                            try:
                                d = json.loads(f.read_text())
                                d["_mtime"] = f.stat().st_mtime
                                new_tasks.append(d)
                            except Exception:
                                pass

                if new_tasks:
                    yield f"data: {json.dumps({'type': 'new', 'tasks': new_tasks})}\n\n"
                    seen = current
                else:
                    # Heartbeat every 5s to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    path = _state(request).ev_dir / f"{task_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(path.read_text())
