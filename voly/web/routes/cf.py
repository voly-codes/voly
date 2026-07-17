"""Routes: /api/cf/* — Cloudflare Spend + Workers status."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/cf/spend/summary")
def cf_spend_summary(request: Request, days: int = 7) -> dict[str, Any]:
    url = request.app.state.app.spend_url()
    if not url:
        return {"configured": False, "hint": "Set CF_WORKER_SPEND_URL to enable",
                "total": 0, "agents": []}
    try:
        from voly.spend.client import create_spend_client, resolve_spend_token

        client = create_spend_client(url)
        if client is None:
            return {
                "configured": False,
                "hint": "Set CF_WORKER_SPEND_URL to enable",
                "total": 0,
                "agents": [],
            }
        if not resolve_spend_token() and not client.token:
            return {
                "configured": True,
                "error": "Spend Worker requires CF_WORKER_SPEND_TOKEN "
                "(must match the worker wrangler secret API_TOKEN)",
                "hint": "Set CF_WORKER_SPEND_TOKEN in .env, then restart voly ui",
                "total": 0,
                "agents": [],
            }
        data = client.summary(days=days)
        data["configured"] = True
    except Exception as exc:
        err = str(exc)
        hint = ""
        if "401" in err or "Unauthorized" in err:
            hint = (
                "CF_WORKER_SPEND_TOKEN must match the spend worker "
                "API_TOKEN secret (not CLOUDFLARE_API_TOKEN)"
            )
        out = {"configured": True, "error": err, "total": 0, "agents": []}
        if hint:
            out["hint"] = hint
        return out

    # The spend worker returns total/agents but no per-day series — attach a daily
    # breakdown from local telemetry so the "По дням" chart is populated.
    if not data.get("daily"):
        from voly.web.routes.telemetry import _load_events, aggregate
        agg = aggregate(_load_events(request.app.state.app.ev_dir), days)
        data["daily"] = [{"date": d["date"], "total": d["cost"]} for d in agg["daily"]]
    return data


@router.get("/api/cf/workers/status")
def cf_workers_status(request: Request) -> dict[str, Any]:
    s = request.app.state.app
    workers: dict[str, tuple[str, str]] = {
        "spend":       ("CF_WORKER_SPEND_URL",       s.spend_url()),
        "marketplace": ("CF_WORKER_MARKETPLACE_URL", s.marketplace_url()),
        "agui":        ("CF_WORKER_AGUI_URL",        os.environ.get("CF_WORKER_AGUI_URL", "")),
        "memory":      ("CF_WORKER_MEMORY_URL",      os.environ.get("CF_WORKER_MEMORY_URL", "")),
        "a2a":         ("CF_WORKER_A2A_URL",         os.environ.get("CF_WORKER_A2A_URL", "")),
        "catalog":     ("CF_WORKER_CATALOG_URL",     os.environ.get("CF_WORKER_CATALOG_URL", "")),
        "telemetry":   ("CF_WORKER_TELEMETRY_URL",  os.environ.get("CF_WORKER_TELEMETRY_URL", "")),
    }
    return {
        name: {"env_key": env_key, "url": url, "configured": bool(url)}
        for name, (env_key, url) in workers.items()
    }


@router.get("/api/providers/health")
def providers_health() -> dict[str, Any]:
    """Return health status for each LLM provider (key-presence check, ~1s TTL cache)."""
    from voly.ai_gateway.health import PROVIDER_PRIORITY, get_checker
    checker = get_checker()
    return {
        "providers": {
            p: {"healthy": checker.check(p).healthy, "reason": checker.check(p).reason}
            for p in PROVIDER_PRIORITY
        },
        "healthy": checker.healthy_providers(),
    }
