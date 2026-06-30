"""GET /api/telemetry/summary — aggregated telemetry metrics."""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


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


def _day_key(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


@router.get("/summary")
def telemetry_summary(request: Request, days: int = 30) -> dict[str, Any]:
    state = request.app.state.app
    events = _load_events(state.ev_dir)

    total_cost = 0.0
    total_tokens = 0
    total_tasks = len(events)
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})

    for ev in events:
        mtime = ev.get("_mtime", 0)
        day = _day_key(mtime)

        cost = ev.get("cost_usd") or 0
        tok = ev.get("tokens") or {}
        tokens_in = tok.get("input") or 0
        tokens_out = tok.get("output") or 0
        tok_total = tokens_in + tokens_out
        agent = ev.get("agent") or "unknown"
        model = ev.get("model") or "unknown"

        total_cost += cost
        total_tokens += tok_total

        by_day[day]["cost"] += cost
        by_day[day]["tokens"] += tok_total
        by_day[day]["tasks"] += 1

        by_agent[agent]["cost"] += cost
        by_agent[agent]["tokens"] += tok_total
        by_agent[agent]["tasks"] += 1

        by_model[model]["cost"] += cost
        by_model[model]["tokens"] += tok_total
        by_model[model]["tasks"] += 1

    # Sort daily data and keep last N days
    sorted_days = sorted(by_day.items())[-days:]
    days_list = [
        {"date": d, "cost": round(v["cost"], 4), "tokens": int(v["tokens"]), "tasks": int(v["tasks"])}
        for d, v in sorted_days
    ]

    def top_entries(data: dict[str, dict[str, float]], limit: int = 10) -> list[dict[str, Any]]:
        sorted_entries = sorted(data.items(), key=lambda x: x[1]["cost"], reverse=True)[:limit]
        return [
            {"name": name, "cost": round(v["cost"], 4), "tokens": int(v["tokens"]), "tasks": int(v["tasks"])}
            for name, v in sorted_entries
        ]

    return {
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "total_tasks": total_tasks,
        "daily": days_list,
        "by_agent": top_entries(by_agent),
        "by_model": top_entries(by_model),
    }
