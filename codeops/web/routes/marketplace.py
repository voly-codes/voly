"""Routes: /api/marketplace/* — CF Skill Marketplace."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _url(request: Request) -> str:
    return request.app.state.app.marketplace_url()


def _ev_dir(request: Request):
    return request.app.state.app.ev_dir


def _skills_dir(request: Request):
    return _ev_dir(request).parent / "skills"


@router.get("/api/marketplace/skills/installed")
def marketplace_installed(request: Request) -> list[str]:
    """Return IDs of locally installed skills (from .codeops/skills/*.json)."""
    skills_dir = _skills_dir(request)
    if not skills_dir.exists():
        return []
    ids = []
    for f in skills_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if sid := data.get("id"):
                ids.append(sid)
        except Exception:
            pass
    return ids


@router.get("/api/marketplace/skills")
def marketplace_skills(
    request: Request,
    page: int = 1,
    limit: int = 24,
    agent: str = "",
    source: str = "",
) -> dict[str, Any]:
    url = _url(request)
    if not url:
        return {"skills": [], "total": 0, "configured": False,
                "hint": "Set CF_WORKER_MARKETPLACE_URL to enable"}
    try:
        from codeops.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).list_skills(
            page=page, limit=limit, agent=agent or None, source=source or None,
        )
        result["configured"] = True
        return result
    except Exception as exc:
        return {"skills": [], "total": 0, "configured": True, "error": str(exc)}


@router.get("/api/marketplace/skills/search")
def marketplace_search(
    request: Request, q: str = "", limit: int = 20
) -> dict[str, Any]:
    url = _url(request)
    if not url or not q:
        return {"skills": [], "total": 0, "configured": bool(url)}
    try:
        from codeops.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).search(q, limit=limit)
        result["configured"] = True
        return result
    except Exception as exc:
        return {"skills": [], "total": 0, "configured": True, "error": str(exc)}


@router.post("/api/marketplace/skills/{skill_id}/install")
def marketplace_install(skill_id: str, request: Request) -> dict[str, Any]:
    url = _url(request)
    if not url:
        raise HTTPException(status_code=503, detail="Marketplace not configured")
    try:
        from codeops.registry.marketplace import MarketplaceClient
        skill_data = MarketplaceClient(url).download_skill(skill_id)
        skills_dir = _ev_dir(request).parent / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = skill_id.replace("/", "_").replace("..", "")
        (skills_dir / f"{safe}.json").write_text(
            json.dumps(skill_data, ensure_ascii=False, indent=2)
        )
        return {"installed": True, "skill_id": skill_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
