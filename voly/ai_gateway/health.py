"""Provider health checker — checks API key presence and optionally liveness."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

_log = logging.getLogger("voly.ai_gateway.health")

_TTL = 60.0  # seconds between re-checks


@dataclass
class ProviderStatus:
    name: str
    healthy: bool
    reason: str = ""
    checked_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return (time.monotonic() - self.checked_at) > _TTL


# Priority order when choosing an alternative provider
PROVIDER_PRIORITY: list[str] = [
    "anthropic",
    "workers-ai",       # CF Workers AI — included in CF plan
    "deepseek",
    "opencode-zen",     # free models available
    "mimo",
    "google",
    "opencode",         # opencode-go (subscription)
    "openai",           # last — pay-per-use, can run out of balance
]

# Env var that signals each provider is configured
_PROVIDER_KEYS: dict[str, list[str]] = {
    "anthropic":     ["ANTHROPIC_API_KEY"],
    "openai":        ["OPENAI_API_KEY"],
    "google":        ["GOOGLE_API_KEY"],
    "deepseek":      ["DEEPSEEK_API_KEY"],
    "opencode":      ["OPENCODE_API_KEY"],
    "opencode-zen":  ["OPENCODE_API_KEY"],
    "mimo":          ["MIMO_API_KEY"],
    "mimo-anthropic":["MIMO_API_KEY"],
    # CF Workers AI uses the same token as the AI Gateway
    "workers-ai":    ["CLOUDFLARE_API_TOKEN"],
    "cloudflare-dynamic": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
}


class ProviderHealthChecker:
    def __init__(self) -> None:
        self._cache: dict[str, ProviderStatus] = {}

    def check(self, provider: str) -> ProviderStatus:
        cached = self._cache.get(provider)
        if cached and not cached.expired():
            return cached

        keys = _PROVIDER_KEYS.get(provider)
        if not keys:
            st = ProviderStatus(name=provider, healthy=True, reason="no key required")
            self._cache[provider] = st
            return st

        missing = [k for k in keys if not os.environ.get(k, "").strip()]
        if missing:
            st = ProviderStatus(
                name=provider,
                healthy=False,
                reason=f"missing env: {', '.join(missing)}",
            )
        else:
            st = ProviderStatus(name=provider, healthy=True, reason="key present")

        self._cache[provider] = st
        _log.debug("health check %s → %s (%s)", provider, "ok" if st.healthy else "unhealthy", st.reason)
        return st

    def healthy_providers(self, candidates: list[str] | None = None) -> list[str]:
        """Return providers from candidates (or PROVIDER_PRIORITY) that are healthy, in priority order."""
        pool = candidates if candidates is not None else PROVIDER_PRIORITY
        return [p for p in pool if self.check(p).healthy]

    def best_provider(self, preferred: str, candidates: list[str] | None = None) -> tuple[str, bool]:
        """Return (provider, is_fallback). Tries preferred first, then priority list."""
        if self.check(preferred).healthy:
            return preferred, False
        pool = candidates if candidates is not None else PROVIDER_PRIORITY
        for p in pool:
            if p != preferred and self.check(p).healthy:
                _log.warning("Provider %s unhealthy — falling back to %s", preferred, p)
                return p, True
        # Nothing healthy, return preferred anyway and let it fail naturally
        return preferred, False

    def status_all(self) -> dict[str, dict]:
        return {
            p: {"healthy": self.check(p).healthy, "reason": self.check(p).reason}
            for p in PROVIDER_PRIORITY
        }


# Module-level singleton (re-used across calls in the same process)
_checker = ProviderHealthChecker()


def get_checker() -> ProviderHealthChecker:
    return _checker
