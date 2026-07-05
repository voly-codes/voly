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


def aggregate(events: list[dict[str, Any]], days: int = 30) -> dict[str, Any]:
    """Aggregate telemetry events. Shared by /telemetry, /gateway and /cf routes.

    Counts LLM calls (a2a sub-agents count individually) for provider/model/cache
    breakdowns so the Gateway tab reflects real usage instead of a fresh 0-metrics
    gateway instance.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    total_cost = 0.0
    total_tokens = 0
    total_tasks = len(events)
    requests = 0
    cache_hits = 0
    spent_today = 0.0
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "tasks": 0})
    by_provider_calls: dict[str, int] = defaultdict(int)
    by_model_calls: dict[str, int] = defaultdict(int)

    for ev in events:
        day = _day_key(ev.get("_mtime", 0))
        cost = ev.get("cost_usd") or 0
        tok = ev.get("tokens") or {}
        tok_total = (tok.get("input") or 0) + (tok.get("output") or 0)
        agent = ev.get("agent") or "unknown"
        model = ev.get("model") or "unknown"

        total_cost += cost
        total_tokens += tok_total
        if day == today:
            spent_today += cost

        for bucket, key in ((by_day, day), (by_agent, agent), (by_model, model)):
            bucket[key]["cost"] += cost
            bucket[key]["tokens"] += tok_total
            bucket[key]["tasks"] += 1

        # Per-call provider/model/cache breakdown: a2a tasks made N sub-calls.
        assigns = ev.get("a2a_assignments") or []
        if assigns:
            for a in assigns:
                requests += 1
                by_provider_calls[a.get("provider") or "unknown"] += 1
                by_model_calls[a.get("model") or "unknown"] += 1
                if a.get("cache_hit"):
                    cache_hits += 1
        else:
            requests += 1
            by_provider_calls[ev.get("provider") or "unknown"] += 1
            by_model_calls[model] += 1
            if (ev.get("gateway") or {}).get("cache_hit"):
                cache_hits += 1

    sorted_days = sorted(by_day.items())[-days:]
    days_list = [
        {"date": d, "cost": round(v["cost"], 4), "tokens": int(v["tokens"]), "tasks": int(v["tasks"])}
        for d, v in sorted_days
    ]

    def top_entries(data: dict[str, dict[str, float]], limit: int = 10) -> list[dict[str, Any]]:
        top = sorted(data.items(), key=lambda x: x[1]["cost"], reverse=True)[:limit]
        return [
            {"name": name, "cost": round(v["cost"], 4), "tokens": int(v["tokens"]), "tasks": int(v["tasks"])}
            for name, v in top
        ]

    return {
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "total_tasks": total_tasks,
        "requests": requests,
        "cache_hits": cache_hits,
        "cache_misses": max(requests - cache_hits, 0),
        "spent_today": round(spent_today, 4),
        "daily": days_list,
        "by_agent": top_entries(by_agent),
        "by_model": top_entries(by_model),
        "by_provider_calls": dict(sorted(by_provider_calls.items(), key=lambda x: -x[1])),
        "by_model_calls": dict(sorted(by_model_calls.items(), key=lambda x: -x[1])[:12]),
    }


@router.get("/summary")
def telemetry_summary(request: Request, days: int = 30) -> dict[str, Any]:
    state = request.app.state.app
    agg = aggregate(_load_events(state.ev_dir), days)
    return {
        "total_cost": agg["total_cost"],
        "total_tokens": agg["total_tokens"],
        "total_tasks": agg["total_tasks"],
        "daily": agg["daily"],
        "by_agent": agg["by_agent"],
        "by_model": agg["by_model"],
    }
