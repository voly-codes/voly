"""GET /api/environment — local readiness (CLIs, keys, cwd, cloud link)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/environment")
def get_environment(request: Request, cwd: str = "") -> dict[str, Any]:
    """Return readiness checks for the local Web UI / doctor view.

    Query ``cwd`` overrides the config default for the working-directory check.
    """
    from voly.environment import collect_environment_report

    s = request.app.state.app
    report = collect_environment_report(s.config, cwd=cwd or None)
    return report.to_dict()
