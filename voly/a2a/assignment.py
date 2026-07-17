"""Assignment dataclass and model-tier resolution for local multi-agent execution.

Tier tables map an abstract tier (premium/standard/cheap) to an ordered list of
real configured providers (``router._PROVIDER_MODELS``) filtered by
``ProviderHealthChecker`` — strong = anthropic/claude, weak = the free/cheap
providers (workers-ai, deepseek, opencode-zen, mimo, omniroute).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from voly.ai_gateway.health import get_checker
from voly.router import _PROVIDER_MODELS

_log = logging.getLogger("voly.a2a.multiagent")

# ── Model tiers → ordered real-provider preference (filtered by health) ──────────
_STRONG = ["anthropic", "cloudflare-dynamic", "deepseek", "opencode", "mimo"]
_STANDARD = ["cloudflare-dynamic", "deepseek", "anthropic", "workers-ai"]
_WEAK = ["workers-ai", "deepseek", "opencode-zen", "mimo", "omniroute"]

_TIER_PROVIDERS: dict[str, list[str]] = {
    "premium": _STRONG,
    "strong": _STRONG,
    "standard": _STANDARD,
    "cheap": _WEAK,
    "weak": _WEAK,
    "free": _WEAK,
}

# Role → default tier (fallback when the lead orchestrator is unavailable) + persona.
_ROLE_TIER: dict[str, str] = {
    "architect": "premium",
    "developer": "standard",
    "tester": "cheap",
    "reviewer": "premium",
    "devops": "cheap",
    "security": "premium",
}

_VALID_TIERS = ("premium", "standard", "cheap")

# Roles that must succeed for a code-gen multi-agent run to count as completed.
_IMPLEMENT_ROLES = frozenset({"developer", "bugfixer"})


def _assignment_active(a: Assignment) -> bool:
    if a.plan_status in ("skipped", "blocked"):
        return False
    if (a.error or "").startswith("skipped:"):
        return False
    return True


def evaluate_multiagent_outcome(
    assignments: list[Assignment],
    *,
    requires_code_gen: bool = True,
) -> tuple[bool, str]:
    """Return ``(pipeline_success, telemetry_status)``.

    ``telemetry_status`` is one of ``completed``, ``partial``, or ``failed``.
    ``pipeline_success`` is True only when status is ``completed``.
    """
    if not assignments:
        return False, "failed"

    active = [a for a in assignments if _assignment_active(a)]
    if not active:
        return False, "failed"

    if not any(a.ok for a in active):
        return False, "failed"

    if all(a.ok for a in active):
        return True, "completed"

    if requires_code_gen:
        impl = [
            a for a in assignments
            if a.mode == "executor" or a.role in _IMPLEMENT_ROLES
        ]
        if impl and not any(a.ok for a in impl):
            return False, "partial"

    return False, "partial"


@dataclass
class Assignment:
    """A sub-agent with its lead-assigned model tier and skills."""
    idx: int
    role: str
    description: str
    depends_on: list[int]
    tier: str
    model: str
    provider: str
    skills: list[str] = field(default_factory=list)
    # Lead may set "chat" | "executor" (hybrid policy); empty → role map.
    execution: str = ""
    # filled after execution
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = False
    error: str = ""
    cache_hit: bool = False       # gateway response cache hit → 0 new tokens billed
    mem_hits: int = 0             # semantic-memory entries injected into this sub-agent
    saved_tokens: int = 0        # tokens saved by Headroom compression on this sub-agent
    # Hybrid multi-agent (PR1+)
    mode: str = "chat"            # "chat" | "executor"
    mode_reason: str = ""
    executor: str = ""            # e.g. claude-code when mode=executor
    files_touched: list[str] = field(default_factory=list)
    # Plan gates (Rung B PR4) — status of the mirrored Plan step
    plan_status: str = ""         # pending|running|verified|failed|…
    plan_verify_ok: bool | None = None  # None = no checks; False = failed verify

    def to_event_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tier": self.tier,
            "model": self.model,
            "provider": self.provider,
            "skills": self.skills,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "ok": self.ok,
            "cache_hit": self.cache_hit,
            "mem_hits": self.mem_hits,
            "saved_tokens": self.saved_tokens,
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "executor": self.executor or None,
            "files_touched": list(self.files_touched),
            "plan_status": self.plan_status or None,
            "plan_verify_ok": self.plan_verify_ok,
        }


def _excluded_providers() -> set[str]:
    """Providers to skip when resolving a tier (e.g. out of credits).

    Set via VOLY_A2A_EXCLUDE_PROVIDERS="anthropic,openai" (comma-separated).
    """
    import os
    raw = os.environ.get("VOLY_A2A_EXCLUDE_PROVIDERS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def resolve_tier_model(tier: str, checker: Any = None) -> tuple[str, str]:
    """Resolve a (model, provider) for the given tier from the healthy real pool."""
    checker = checker or get_checker()
    excluded = _excluded_providers()

    def _ok(provider: str) -> bool:
        return provider not in excluded and checker.check(provider).healthy

    for provider in _TIER_PROVIDERS.get(tier, _WEAK):
        if provider in _PROVIDER_MODELS and _ok(provider):
            return _PROVIDER_MODELS[provider]
    # No healthy provider in the requested tier → any healthy, non-excluded provider.
    for provider, pair in _PROVIDER_MODELS.items():
        if _ok(provider):
            _log.warning("tier %r: no healthy provider in tier, using %s", tier, pair[1])
            return pair
    # Last resort — anthropic (call will surface a clear auth error if unconfigured).
    return _PROVIDER_MODELS["anthropic"]
