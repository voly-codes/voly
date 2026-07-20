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
# Anthropic last among paid peers: credit/billing outages are common and must not
# burn the first attempt of every role before fallback (mark_unhealthy still applies).
_STRONG = ["cloudflare-dynamic", "deepseek", "opencode", "mimo", "anthropic"]
_STANDARD = ["cloudflare-dynamic", "deepseek", "workers-ai", "anthropic"]
_WEAK = ["workers-ai", "deepseek", "mimo", "opencode-zen", "omniroute"]

_TIER_PROVIDERS: dict[str, list[str]] = {
    "premium": _STRONG,
    "strong": _STRONG,
    "standard": _STANDARD,
    "cheap": _WEAK,
    "weak": _WEAK,
    "free": _WEAK,
}

from voly.a2a.roles import ROLE_REGISTRY

# Role → default tier (fallback when the lead orchestrator is unavailable) + persona.
_ROLE_TIER: dict[str, str] = {r.id: r.tier for r in ROLE_REGISTRY.values()}

_VALID_TIERS = ("premium", "standard", "cheap")

# Spread roles across healthy providers in the same tier (modulo pool length).
_ROLE_PROVIDER_OFFSET: dict[str, int] = {r.id: r.provider_offset for r in ROLE_REGISTRY.values()}

# Roles that must succeed for a code-gen multi-agent run to count as completed.
_IMPLEMENT_ROLES = frozenset({"developer", "bugfixer"})

_RECOVERABLE_PROVIDER_ERRORS = frozenset({
    "unauthorized",
    "quota_exhausted",
    "account_deactivated",
    "oauth_invalid_token",
    "forbidden",
})


def exclude_provider_on_gateway_error(provider: str, error: str) -> None:
    """Mark provider unhealthy after auth/billing failures so tier resolution skips it."""
    if not provider or not error:
        return
    from voly.ai_gateway.error_classifier import classify_provider_error

    kind = classify_provider_error(None, error, provider=provider)
    if kind is None:
        low = error.lower()
        if "401" in low or "unauthorized" in low or "invalid x-api-key" in low:
            kind = "unauthorized"
        elif "quota" in low or "billing" in low or "credit" in low:
            kind = "quota_exhausted"
    if kind in _RECOVERABLE_PROVIDER_ERRORS:
        get_checker().mark_unhealthy(provider, reason=kind or "gateway error")


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

    # Code-gen guard first: a run cannot be "completed" without a successful
    # implement role, even if every non-skipped chat role succeeded (e.g. the
    # developer was hard-skipped/blocked and thus excluded from `active`).
    if requires_code_gen:
        impl = [
            a for a in assignments
            if a.mode == "executor" or a.role in _IMPLEMENT_ROLES
        ]

        def _impl_ok(a: Assignment) -> bool:
            if a.ok:
                return True
            # Soft: wrote project files despite role ok=False (e.g. legacy safety hard-fail).
            return any(
                f and not str(f).startswith(".voly/") for f in (a.files_touched or [])
            )

        if impl and not any(_impl_ok(a) for a in impl):
            return False, "partial"

    if all(a.ok for a in active):
        return True, "completed"

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
    duration_ms: float = 0.0      # wall-clock of the role's chat/executor call
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
            "duration_ms": round(self.duration_ms, 1),
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


def apply_env_provider_exclusions() -> list[str]:
    """Mark ``VOLY_A2A_EXCLUDE_PROVIDERS`` unhealthy before the first chat call.

    Tier resolution already skips the env list; this also demotes an assigned
    provider (e.g. Anthropic with empty credits) so fallback does not burn a
    doomed first attempt per role.
    """
    marked: list[str] = []
    for provider in sorted(_excluded_providers()):
        get_checker().mark_unhealthy(provider, reason="VOLY_A2A_EXCLUDE_PROVIDERS")
        marked.append(provider)
    return marked


def _healthy_providers_for_tier(tier: str, checker: Any) -> list[str]:
    """Ordered healthy provider names for a tier (excludes VOLY_A2A_EXCLUDE_PROVIDERS)."""
    excluded = _excluded_providers()

    def _ok(provider: str) -> bool:
        return (
            provider not in excluded
            and provider in _PROVIDER_MODELS
            and checker.check(provider).healthy
        )

    pool = _TIER_PROVIDERS.get(tier, _WEAK)
    return [p for p in pool if _ok(p)]


def resolve_tier_model(tier: str, checker: Any = None) -> tuple[str, str]:
    """Resolve a (model, provider) for the given tier from the healthy real pool."""
    checker = checker or get_checker()
    excluded = _excluded_providers()

    def _ok(provider: str) -> bool:
        return provider not in excluded and checker.check(provider).healthy

    healthy = _healthy_providers_for_tier(tier, checker)
    if healthy:
        return _PROVIDER_MODELS[healthy[0]]

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


def resolve_role_model(
    role: str,
    tier: str | None = None,
    checker: Any = None,
) -> tuple[str, str]:
    """Resolve (model, provider) with per-role offset inside the tier pool."""
    checker = checker or get_checker()
    role_key = (role or "").strip().lower()
    tier_key = tier or _ROLE_TIER.get(role_key, "standard")
    healthy = _healthy_providers_for_tier(tier_key, checker)
    if not healthy:
        return resolve_tier_model(tier_key, checker)
    offset = _ROLE_PROVIDER_OFFSET.get(role_key, 0)
    provider = healthy[offset % len(healthy)]
    return _PROVIDER_MODELS[provider]


def chat_fallback_providers(
    tier: str,
    role: str,
    checker: Any = None,
) -> list[str]:
    """Provider names to try for chat roles after the primary assignment fails."""
    checker = checker or get_checker()
    healthy = _healthy_providers_for_tier(tier, checker)
    if not healthy:
        return []
    offset = _ROLE_PROVIDER_OFFSET.get((role or "").strip().lower(), 0)
    start = offset % len(healthy)
    return healthy[start:] + healthy[:start]
