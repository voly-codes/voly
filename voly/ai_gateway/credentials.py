"""Provider credential routing: CF AI Gateway BYOK vs local env keys.

See ``docs/backend/ai-gateway.md`` § BYOK (Store Keys).

BYOK (Store Keys): provider API keys live in Cloudflare Secrets Store
(named ``{gateway_id}_{provider_slug}_{alias}``) and are resolved by the
gateway per request — the client sends only the gateway token
(``cf-aig-authorization``). Providers not supported by AI Gateway always
use the local env path.
"""
from __future__ import annotations

import os
import re
from typing import Any

# provider_name (VOLY) → provider slug on the CF /compat endpoint.
# Only providers AI Gateway can proxy with stored keys belong here;
# everything else (mimo, opencode, opencode-zen, omniroute, …) stays on env.
BYOK_PROVIDER_SLUGS: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google-ai-studio",
    "google-ai-studio": "google-ai-studio",
    "deepseek": "deepseek",
}


def byok_active(gateway: Any) -> bool:
    """True when BYOK is enabled and the CF gateway is addressable.

    Requires an account id and a gateway token (``CF_AIG_TOKEN`` preferred,
    ``api_token`` / ``CLOUDFLARE_API_TOKEN`` as fallback) — same credentials
    the existing ``/compat`` dynamic-routing path uses.
    """
    if not getattr(gateway, "byok_enabled", False):
        return False
    account = getattr(gateway, "account_id", "") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = (
        os.environ.get("CF_AIG_TOKEN", "")
        or getattr(gateway, "api_token", "")
        or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    )
    return bool(account and token)


# CF gateway catalog spells Anthropic minor versions with a dot
# (claude-sonnet-4.6) while Anthropic API ids use a hyphen (claude-sonnet-4-6).
_ANTHROPIC_MINOR_VERSION = re.compile(r"^(claude-[a-z0-9]+-\d+)-(\d)$")


def gateway_model(provider_slug: str, model: str) -> str:
    """Model id as the CF AI REST API catalog expects it (live-verified 2026-07-11)."""
    if provider_slug == "anthropic":
        m = _ANTHROPIC_MINOR_VERSION.match(model)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
    return model


def byok_provider_slug(
    provider_name: str,
    byok_providers: list[str] | None = None,
) -> str:
    """CF slug for the provider, or "" when it must use the env path.

    ``byok_providers`` restricts BYOK to a subset (empty/None = all supported);
    entries may use either the VOLY provider name or the CF slug.
    """
    slug = BYOK_PROVIDER_SLUGS.get(provider_name, "")
    if not slug:
        return ""
    if byok_providers and provider_name not in byok_providers and slug not in byok_providers:
        return ""
    return slug
