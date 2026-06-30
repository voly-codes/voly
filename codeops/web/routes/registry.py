"""Routes: /api/registry/* — local agents, models, skills."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()

_EXECUTOR_MODELS: dict[str, list[str]] = {
    # Cursor — local agent IDE
    "cursor":   ["composer-2.5"],

    # OpenCode Go — subscription-based coding models (opencode.ai/zen/go/v1)
    "opencode": [
        "deepseek-v4-flash", "deepseek-v4-pro",
        "glm-5.2",
        "kimi-k2.6", "kimi-k2.7-code",
        "mimo-v2.5", "mimo-v2.5-pro",
        "minimax-m3",
        "qwen3.7-plus", "qwen3.7-max",
    ],

    # OpenCode Zen — curated pay-per-use models (opencode.ai/zen/v1)
    "zen": [
        "big-pickle",
        "claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-4-6",
        "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-free",
        "gemini-3.5-flash",
        "glm-5.2",
        "gpt-5.4", "gpt-5.4-mini", "gpt-5.5", "gpt-5.5-pro",
        "grok-build-0.1",
        "kimi-k2.6",
        "mimo-v2.5-free",
        "minimax-m2.7",
        "qwen3.7-max", "qwen3.7-plus",
    ],

    # Other direct providers
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
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
