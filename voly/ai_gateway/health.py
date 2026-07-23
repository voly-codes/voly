"""Provider health checker — checks API key presence and optionally liveness."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

_log = logging.getLogger("voly.ai_gateway.health")

_TTL = 60.0  # seconds between re-checks

_RUNTIME_EXCLUDED = "runtime excluded"


def _runtime_exclude_ttl() -> float:
    """How long a mark_unhealthy() exclusion holds before the provider is re-tried.

    Without a TTL a transient 401/403/5xx would exclude the provider until the
    process restarts — fatal for long-running `voly serve`. Override with
    VOLY_PROVIDER_EXCLUDE_TTL (seconds); 0 disables expiry (exclude forever).
    """
    raw = os.environ.get("VOLY_PROVIDER_EXCLUDE_TTL", "").strip()
    try:
        return float(raw) if raw else 900.0
    except ValueError:
        return 900.0


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


def _byok_env_default() -> bool:
    return os.environ.get("VOLY_BYOK", "").strip().lower() in ("1", "true", "yes", "on")


class ProviderHealthChecker:
    def __init__(self) -> None:
        self._cache: dict[str, ProviderStatus] = {}
        # provider → monotonic timestamp of exclusion (expires after the TTL)
        self._runtime_excluded: dict[str, float] = {}
        # None → follow the VOLY_BYOK env default; set via configure_byok()
        # when a gateway is built from config (pipeline/core.py).
        self._byok_enabled: bool | None = None
        self._byok_providers: list[str] = []

    def mark_unhealthy(self, provider: str, reason: str = "") -> None:
        """Exclude a provider for the rest of this process (e.g. after 401/billing)."""
        provider = (provider or "").strip()
        if not provider:
            return
        self._runtime_excluded[provider] = time.monotonic()
        self._cache[provider] = ProviderStatus(
            name=provider,
            healthy=False,
            reason=reason or _RUNTIME_EXCLUDED,
        )
        _log.warning("provider %s marked unhealthy: %s", provider, reason or _RUNTIME_EXCLUDED)

    def configure_byok(self, enabled: bool, providers: list[str] | None = None) -> None:
        """Sync BYOK state from config; resets cached statuses."""
        self._byok_enabled = enabled
        self._byok_providers = list(providers or [])
        self._cache.clear()

    def _byok_healthy(self, provider: str) -> bool:
        """True when the provider's key lives in the CF gateway (no env key needed)."""
        enabled = self._byok_enabled if self._byok_enabled is not None else _byok_env_default()
        if not enabled:
            return False
        from voly.ai_gateway.credentials import byok_provider_slug

        if not byok_provider_slug(provider, self._byok_providers or None):
            return False
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        token = (
            os.environ.get("CF_AIG_TOKEN", "").strip()
            or os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        )
        return bool(account and token)

    def check(self, provider: str) -> ProviderStatus:
        excluded_at = self._runtime_excluded.get(provider)
        if excluded_at is not None:
            ttl = _runtime_exclude_ttl()
            if ttl > 0 and (time.monotonic() - excluded_at) > ttl:
                # Exclusion expired — give the provider another chance.
                self._runtime_excluded.pop(provider, None)
                self._cache.pop(provider, None)
                _log.info("provider %s exclusion expired — re-checking", provider)
            else:
                cached = self._cache.get(provider)
                reason = cached.reason if cached else _RUNTIME_EXCLUDED
                return ProviderStatus(name=provider, healthy=False, reason=reason)

        cached = self._cache.get(provider)
        if cached and not cached.expired():
            return cached

        if self._byok_healthy(provider):
            st = ProviderStatus(name=provider, healthy=True, reason="byok: key stored in CF gateway")
            self._cache[provider] = st
            return st

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
