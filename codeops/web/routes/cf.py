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
        from codeops.spend.client import SpendClient
        data = SpendClient(url).summary(days=days)
        data["configured"] = True
        return data
    except Exception as exc:
        return {"configured": True, "error": str(exc), "total": 0, "agents": []}


@router.get("/api/cf/workers/status")
def cf_workers_status(request: Request) -> dict[str, Any]:
    s = request.app.state.app
    workers: dict[str, tuple[str, str]] = {
        "spend":       ("CF_WORKER_SPEND_URL",       s.spend_url()),
        "marketplace": ("CF_WORKER_MARKETPLACE_URL", s.marketplace_url()),
        "agui":        ("CF_WORKER_AGUI_URL",        os.environ.get("CF_WORKER_AGUI_URL", "")),
        "memory":      ("CF_WORKER_MEMORY_URL",      os.environ.get("CF_WORKER_MEMORY_URL", "")),
        "a2a":         ("CF_WORKER_A2A_URL",         os.environ.get("CF_WORKER_A2A_URL", "")),
        "workflow":    ("CF_WORKER_WORKFLOW_URL",    os.environ.get("CF_WORKER_WORKFLOW_URL", "")),
        "catalog":     ("CF_WORKER_CATALOG_URL",     os.environ.get("CF_WORKER_CATALOG_URL", "")),
        "telemetry":   ("CF_WORKER_TELEMETRY_URL",  os.environ.get("CF_WORKER_TELEMETRY_URL", "")),
    }
    return {
        name: {"env_key": env_key, "url": url, "configured": bool(url)}
        for name, (env_key, url) in workers.items()
    }
