"""Routes: /api/registry/* — local agents, models, skills."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()

_EXECUTOR_MODELS: dict[str, list[str]] = {
    "cursor":   ["composer-2.5"],
    "opencode": ["kimi-k2.6", "claude-sonnet-4-6", "gpt-4o"],
    "zen":      ["claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4o-mini"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"],
    "mimo":     ["mimo-v2.5-free"],
}

_FALLBACK_AGENTS = [
    "cursor", "architect", "developer", "reviewer",
    "tester", "security", "devops", "documenter", "product-analyst",
]

_FALLBACK_MODELS = [
    "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5",
    "gpt-4o", "gpt-4o-mini", "deepseek-v4-flash",
]


@router.get("/api/registry/agents")
def registry_agents() -> list[str]:
    try:
        from codeops.registry.agents import AgentRegistry
        return AgentRegistry().list_names()
    except Exception:
        return _FALLBACK_AGENTS


@router.get("/api/registry/models")
def registry_models(executor: str = "pipeline") -> list[str]:
    if executor in _EXECUTOR_MODELS:
        return _EXECUTOR_MODELS[executor]
    try:
        from codeops.telemetry import _COST_RATES
        return list(_COST_RATES.keys())
    except Exception:
        return _FALLBACK_MODELS


@router.get("/api/registry/skills")
def registry_skills(source: str = "", status: str = "active") -> list[dict[str, Any]]:
    try:
        from codeops.registry.skills import SkillRegistry
        skills = SkillRegistry().search(source=source or None, status=status or None)
        return [s.to_dict() for s in skills]
    except Exception as exc:
        return [{"error": str(exc)}]
