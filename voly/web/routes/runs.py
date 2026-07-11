"""Routes: /api/runs — in-flight run records (RunTracker heartbeats).

`TaskEvent` files appear only when a run finishes; while an executor or a
multi-agent chain is working, its progress lives in ``.voly/runs/`` RunRecords
(heartbeat every ~10s). These endpoints let the UI show tasks that are still
running — including ones launched from the CLI — and drill into their state.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _runs_dir(request: Request) -> str:
    # Sibling of the events dir: <project>/.voly/events → <project>/.voly/runs.
    ev_dir = request.app.state.app.ev_dir
    return str(ev_dir.parent / "runs")


def _to_dict(rec: Any) -> dict[str, Any]:
    d = asdict(rec)
    d["age_seconds"] = round(rec.age_seconds, 1)
    d["elapsed_seconds"] = round(rec.elapsed_seconds, 1)
    return d


@router.get("/api/runs")
def list_runs(request: Request, active: bool = False, limit: int = 50) -> dict[str, Any]:
    from voly.runtime.runs import RUNNING, RunTracker

    records = RunTracker(_runs_dir(request)).list()
    if active:
        records = [r for r in records if r.status == RUNNING]
    return {
        "runs": [_to_dict(r) for r in records[: max(1, min(limit, 200))]],
        "active": sum(1 for r in records if r.status == RUNNING),
    }


@router.get("/api/runs/{task_id}")
def get_run(request: Request, task_id: str) -> dict[str, Any]:
    from voly.runtime.runs import RunTracker

    rec = RunTracker(_runs_dir(request)).load(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no run record for {task_id}")
    return _to_dict(rec)
