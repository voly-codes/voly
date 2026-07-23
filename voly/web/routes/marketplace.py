"""Routes: /api/marketplace/* — CF Skill Marketplace."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter()

_MARKETPLACE_UNAVAILABLE_HINT = "Remote marketplace unavailable; showing local registry fallback"


def _url(request: Request) -> str:
    return request.app.state.app.marketplace_url()


def _ev_dir(request: Request):
    return request.app.state.app.ev_dir


def _skills_dir(request: Request):
    return _ev_dir(request).parent / "skills"


def _local_skill_rows(source: str = "", status: str = "active", query: str = "") -> list[dict[str, Any]]:
    from voly.registry.skills import SkillRegistry

    reg = SkillRegistry()
    skills = reg.search(source=source or None, status=status or None, query=query or "")
    return [s.to_dict() for s in skills]


@router.get("/api/marketplace/skills/installed")
def marketplace_installed(request: Request) -> list[str]:
    """Return IDs of locally installed skills from .voly/skills/."""
    skills_dir = _skills_dir(request)
    if not skills_dir.exists():
        return []
    ids: list[str] = []
    seen: set[str] = set()

    # YAML/YML — canonical format written by install_from_marketplace
    try:
        from voly.registry.loader import load_skills_from_directory
        for skill in load_skills_from_directory(skills_dir):
            if skill.id not in seen:
                ids.append(skill.id)
                seen.add(skill.id)
    except Exception:
        pass

    # JSON — legacy format from old install handler
    for f in skills_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            sid = data.get("id")
            if sid and sid not in seen:
                ids.append(sid)
                seen.add(sid)
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
    status: str = "active",
) -> dict[str, Any]:
    url = _url(request)
    if not url:
        skills = _local_skill_rows(source=source, status=status)
        return {
            "skills": skills[(page - 1) * limit : (page - 1) * limit + limit],
            "total": len(skills),
            "configured": False,
            "hint": "Set CF_WORKER_MARKETPLACE_URL to enable remote marketplace",
        }
    try:
        from voly.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).list_skills(
            page=page, limit=limit, agent=agent or None, source=source or None,
        )
        result["configured"] = True
        return result
    except Exception as exc:
        skills = _local_skill_rows(source=source, status=status)
        return {
            "skills": skills[(page - 1) * limit : (page - 1) * limit + limit],
            "total": len(skills),
            "configured": False,
            "error": str(exc),
            "hint": _MARKETPLACE_UNAVAILABLE_HINT,
        }


@router.get("/api/marketplace/skills/search")
def marketplace_search(
    request: Request, q: str = "", limit: int = 20
) -> dict[str, Any]:
    url = _url(request)
    if not url or not q:
        if not q:
            return {"skills": [], "total": 0, "configured": bool(url)}
        skills = _local_skill_rows(query=q)
        return {
            "skills": skills[:limit],
            "total": len(skills),
            "configured": False,
            "hint": _MARKETPLACE_UNAVAILABLE_HINT,
        }
    try:
        from voly.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).search(q, limit=limit)
        result["configured"] = True
        return result
    except Exception as exc:
        skills = _local_skill_rows(query=q)
        return {
            "skills": skills[:limit],
            "total": len(skills),
            "configured": False,
            "error": str(exc),
            "hint": _MARKETPLACE_UNAVAILABLE_HINT,
        }


@router.post(
    "/api/marketplace/skills/{skill_id}/install",
    responses={
        503: {"description": "Marketplace not configured"},
        500: {"description": "Skill install failed"},
    },
)
def marketplace_install(skill_id: str, request: Request) -> dict[str, Any]:
    url = _url(request)
    if not url:
        raise HTTPException(status_code=503, detail="Marketplace not configured")
    try:
        from voly.registry.skills import create_skill_registry
        skills_dir = _skills_dir(request)
        registry = create_skill_registry(
            skills_path=str(skills_dir),
            marketplace_url=url,
        )
        skill = registry.install_from_marketplace(skill_id)
        return {
            "installed": True,
            "skill_id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "source": skill.source.value,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/marketplace/skills/suggest")
def marketplace_suggest(request: Request, task: str = "", limit: int = 5) -> dict[str, Any]:
    """Return marketplace skills relevant to a task that are not installed locally.

    Used by the UI pre-run skill gate and the post-run skill_suggest banner.
    """
    if not task:
        return {"suggestions": [], "configured": False}
    url = _url(request)
    if not url:
        return {"suggestions": [], "configured": False, "hint": "Set CF_WORKER_MARKETPLACE_URL to enable suggestions"}
    skills_dir = _skills_dir(request)
    try:
        from voly.registry.skills import SkillRegistry
        from voly.registry.scout import SkillScout
        reg = SkillRegistry(skills_path=skills_dir if skills_dir.exists() else None)
        scout = SkillScout(reg, url)
        suggestions = scout.find_missing(task, limit=limit)
        return {"suggestions": suggestions, "configured": True}
    except Exception as exc:
        return {"suggestions": [], "configured": True, "error": str(exc)}


@router.get("/api/marketplace/plugins")
def marketplace_plugins(request: Request, status: str = "active", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    url = _url(request)
    if not url:
        from voly.registry.external_catalog import catalog_path_for, load_external_catalog
        catalog = load_external_catalog(catalog_path_for(_ev_dir(request).parent))
        plugins = catalog.get("plugins", []) if catalog else []
        return {
            "plugins": plugins[offset : offset + limit],
            "count": len(plugins),
            "configured": False,
            "hint": "Set CF_WORKER_MARKETPLACE_URL to enable remote plugin marketplace",
        }
    try:
        from voly.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).list_plugins(status=status, limit=limit, offset=offset)
        result["configured"] = True
        return result
    except Exception as exc:
        from voly.registry.external_catalog import catalog_path_for, load_external_catalog
        catalog = load_external_catalog(catalog_path_for(_ev_dir(request).parent))
        plugins = catalog.get("plugins", []) if catalog else []
        return {
            "plugins": plugins[offset : offset + limit],
            "count": len(plugins),
            "configured": False,
            "error": str(exc),
            "hint": "Remote marketplace unavailable; showing local plugin catalog fallback",
        }


@router.post(
    "/api/marketplace/plugins/sync",
    responses={
        503: {"description": "Marketplace not configured (set CF_WORKER_MARKETPLACE_URL)"},
        502: {"description": "Bad gateway from remote marketplace"},
    },
)
def marketplace_plugins_sync(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Bulk-upsert plugins into the remote marketplace (proxy to the CF worker).

    The UI posts ``{"plugins": [...]}``; this proxies to the worker's
    ``POST /plugins/sync``. Requires ``CF_WORKER_MARKETPLACE_URL``.
    """
    url = _url(request)
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Marketplace not configured (set CF_WORKER_MARKETPLACE_URL)",
        )
    plugins = payload.get("plugins") or payload.get("items") or []
    try:
        from voly.registry.marketplace import MarketplaceClient
        result = MarketplaceClient(url).sync_plugins({"plugins": plugins})
        result["configured"] = True
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
