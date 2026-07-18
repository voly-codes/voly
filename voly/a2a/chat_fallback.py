"""Provider fallback loop for multi-agent chat roles."""

from __future__ import annotations

import logging
from typing import Any

from voly.a2a.assignment import (
    Assignment,
    chat_fallback_providers,
    exclude_provider_on_gateway_error,
)

_log = logging.getLogger("voly.a2a.multiagent")


def chat_with_provider_fallback(
    gateway: Any,
    *,
    messages: list[dict[str, str]],
    assignment: Assignment,
    system: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """Try gateway.chat on the assigned provider, then other healthy tier providers."""
    from voly.ai_gateway.health import get_checker
    from voly.router import _PROVIDER_MODELS

    providers = chat_fallback_providers(assignment.tier, assignment.role)
    assigned = assignment.provider
    if assigned:
        # Skip assigned provider when already unhealthy (401/billing) instead of
        # burning one failed call per role on a known-dead provider.
        if get_checker().check(assigned).healthy:
            providers = [assigned] + [p for p in providers if p != assigned]
        else:
            providers = [p for p in providers if p != assigned]
    if not providers:
        providers = [assigned] if assigned else []

    last_err = ""
    for provider in providers:
        model = _PROVIDER_MODELS.get(provider, (assignment.model, provider))[0]
        try:
            resp = gateway.chat(
                messages,
                model=model,
                provider_name=provider,
                system=system,
                agent=assignment.role,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            exclude_provider_on_gateway_error(provider, last_err)
            _log.warning(
                "multiagent[%d] %s chat %s failed (%s) — trying next provider",
                assignment.idx, assignment.role, provider, last_err[:120],
            )
            continue

        if resp.get("error"):
            if resp.get("spend_limited"):
                return resp
            last_err = str(resp["error"])
            exclude_provider_on_gateway_error(provider, last_err)
            _log.warning(
                "multiagent[%d] %s chat %s error (%s) — trying next provider",
                assignment.idx, assignment.role, provider, last_err[:120],
            )
            continue

        if provider != assignment.provider:
            assignment.provider = provider
            assignment.model = model
            assignment.mode_reason = (
                f"{assignment.mode_reason}+provider_fallback"
                if assignment.mode_reason
                else "provider_fallback"
            )
        return resp

    return {"error": last_err or "all chat providers failed", "content": ""}
