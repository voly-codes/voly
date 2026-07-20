"""Routes: /api/registry/* — local agents, models, skills."""

from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter

router = APIRouter()

_ENV_TOKEN_RE = re.compile(r"[^A-Z0-9]+")
_MODEL_ENV_BY_SUFFIX = {
    "PIPELINE": "VOLY_MODELS_PIPELINE",
    "CLAUDE_CODE": "VOLY_MODELS_CLAUDE_CODE",
    "CURSOR": "VOLY_MODELS_CURSOR",
    "OPENCODE": "VOLY_MODELS_OPENCODE",
    "ZEN": "VOLY_MODELS_ZEN",
    "DEEPSEEK": "VOLY_MODELS_DEEPSEEK",
    "MIMO": "VOLY_MODELS_MIMO",
    "WRANGLER": "VOLY_MODELS_WRANGLER",
    "WORKERS_AI": "VOLY_MODELS_WORKERS_AI",
    "CLOUDFLARE_DYNAMIC": "VOLY_MODELS_CLOUDFLARE_DYNAMIC",
}


def _csv_env(name: str) -> list[str] | None:
    """Return a de-duplicated CSV env list, or None when it is not configured."""
    if name not in os.environ:
        return None
    items = (item.strip() for item in os.environ[name].split(","))
    return list(dict.fromkeys(item for item in items if item))


def _models_env_name(executor: str) -> str:
    suffix = _ENV_TOKEN_RE.sub("_", executor.strip().upper()).strip("_")
    if not suffix:
        return "VOLY_MODELS"
    return _MODEL_ENV_BY_SUFFIX.get(suffix, f"VOLY_MODELS_{suffix}")


@router.get("/api/registry/agents")
def registry_agents() -> list[str]:
    configured = _csv_env("VOLY_ROLES")
    if configured is not None:
        return configured
    try:
        from voly.registry.agents import AgentRegistry
        return AgentRegistry().list_names()
    except Exception:
        return []


@router.get("/api/registry/models")
def registry_models(executor: str = "pipeline") -> list[str]:
    configured = _csv_env(_models_env_name(executor))
    if configured is None:
        configured = _csv_env("VOLY_MODELS")
    if configured is not None:
        return configured
    try:
        from voly.telemetry import _COST_RATES
        return list(_COST_RATES.keys())
    except Exception:
        return []


@router.get("/api/registry/skills")
def registry_skills(source: str = "", status: str = "active") -> list[dict[str, Any]]:
    try:
        from voly.registry.skills import SkillRegistry
        skills = SkillRegistry().search(source=source or None, status=status or None)
        return [s.to_dict() for s in skills]
    except Exception as exc:
        return [{"error": str(exc)}]
