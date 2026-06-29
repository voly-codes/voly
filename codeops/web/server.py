"""CodeOps FastAPI server — serves REST API + built Svelte UI."""

from __future__ import annotations

import json
import pathlib
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

_STATIC = pathlib.Path(__file__).parent / "static"


def create_app(events_dir: pathlib.Path | None = None) -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("Install UI dependencies: pip install 'codeops[ui]'")

    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="CodeOps UI", version="0.1.0", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ev_dir = events_dir or _resolve_events_dir()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _load_events() -> list[dict[str, Any]]:
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

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        events = list(ev_dir.glob("*.json")) if ev_dir.exists() else []
        return {
            "version": "0.1.0",
            "tasks_count": len(events),
            "events_dir": str(ev_dir),
        }

    @app.get("/api/tasks")
    def list_tasks(
        limit: int = 100,
        agent: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        tasks = _load_events()
        if agent:
            tasks = [t for t in tasks if t.get("agent") == agent]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks[:limit]

    @app.get("/api/tasks/stats/summary")
    def get_summary() -> dict[str, Any]:
        tasks = _load_events()
        if not tasks:
            return {
                "total_tasks": 0,
                "total_cost_usd": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_saved_tokens": 0,
                "avg_duration_ms": 0,
                "by_agent": {},
                "by_status": {},
                "by_model": {},
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
            a = t.get("agent") or "unknown"
            by_agent[a] = by_agent.get(a, 0) + 1
            s = t.get("status") or "unknown"
            by_status[s] = by_status.get(s, 0) + 1
            m = t.get("model") or "unknown"
            by_model[m] = by_model.get(m, 0) + 1

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

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        path = ev_dir / f"{task_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Task not found")
        return json.loads(path.read_text())

    # Serve built Svelte app (only if static dir exists)
    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")

    return app


def _resolve_events_dir() -> pathlib.Path:
    candidates = [
        pathlib.Path.cwd() / ".codeops" / "events",
        pathlib.Path.home() / ".codeops" / "events",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]
