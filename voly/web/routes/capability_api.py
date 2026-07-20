"""Capability match proxy and repository analysis endpoints."""

from __future__ import annotations

import os
from dataclasses import asdict

import httpx
from fastapi import APIRouter

router = APIRouter()

def _capability_worker_url() -> str:
    try:
        from voly.config import load_config
        return load_config().capability.worker_url
    except Exception:
        return os.getenv("VOLY_CAPABILITY_WORKER_URL", "")


_PROFILES_DIR = os.path.join(".voly", "capability", "profiles")
_SEEDS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "capability", "seeds"
)


def _registry():
    from voly.capability.registry import CapabilityRegistry

    return CapabilityRegistry(_PROFILES_DIR, seeds_dir=_SEEDS_DIR)


@router.post("/api/capability/match")
async def capability_match(body: dict) -> dict:
    """Proxy POST to CF Worker /match; fall back to local Python matcher."""
    worker_url = _capability_worker_url()
    if worker_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{worker_url}/match", json=body)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            pass

    from voly.capability.matcher import ExecutorMatcher, MatchRequest

    matcher = ExecutorMatcher(_registry())
    req = MatchRequest(
        dimension=body.get("dimension", "backend"),
        kind=str(body.get("kind") or "executor"),
        available_executors=body.get("available_executors"),
        project_features=body.get("project_stack") or body.get("project_features"),
        requires_file_tools=bool(
            body.get("requires_file_tools", str(body.get("kind") or "executor") == "executor")
        ),
        routing_policy=str(body.get("routing_policy") or "balanced"),
    )
    result = matcher.find_executors(req)
    return {
        "recommended": (
            {
                "executor_id": result.recommended.id,
                "score": result.score,
                "routing_score": result.score,
            }
            if result.recommended
            else None
        ),
        "fallbacks": [
            {"executor_id": p.id, "score": s, "routing_score": s}
            for p, s in result.fallbacks[:4]
        ],
        "excluded": [{"executor_id": eid, "reason": r} for eid, r in result.excluded],
    }


@router.get("/api/capability/profiles")
async def capability_profiles() -> dict:
    """List all executor IDs with profiles in the local registry."""
    return {"executor_ids": _registry().list_ids()}


@router.post("/api/repo/analyze")
async def repo_analyze(body: dict) -> dict:
    """Run voly.intelligence.analyze() and return RepositoryIntelligence as dict."""
    from voly.intelligence import AnalyzeConfig, analyze

    url = body.get("url", "").strip()
    if not url:
        return {"error": "url required"}
    try:
        cfg = AnalyzeConfig(refresh=bool(body.get("refresh", False)))
        intel = analyze(url, cfg)
        return asdict(intel)
    except Exception as exc:
        return {"error": str(exc)}
