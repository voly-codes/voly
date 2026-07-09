"""Auth provider registry.

Built-ins: ``local`` (open-core), ``clerk`` (optional SSO, extract candidate).

External packages may register via setuptools entry point group::

    [project.entry-points.\"voly.auth_providers\"]
    clerk = \"voly_team.auth:ClerkProvider\"

External providers **override** built-ins with the same name (Phase 3 extract).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from voly.web.auth.jwt import InvalidTokenError
from voly.web.auth.providers.base import AuthProvider
from voly.web.auth.providers.local import LocalProvider

if TYPE_CHECKING:
    from voly.config import AuthConfig

_log = logging.getLogger("voly.web.auth.providers")

# Built-in factories (lazy for clerk so core import path stays free of JWKS code
# until provider=clerk is selected).
_BUILTIN: dict[str, Callable[[], AuthProvider]] = {
    "local": LocalProvider,
}


def _clerk_factory() -> AuthProvider:
    from voly.web.auth.providers.clerk import ClerkProvider

    return ClerkProvider()


_BUILTIN["clerk"] = _clerk_factory


def _entry_point_providers() -> dict[str, Callable[[], AuthProvider]]:
    out: dict[str, Callable[[], AuthProvider]] = {}
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return out
    try:
        eps = entry_points()
        # Python 3.10+ SelectableGroups; 3.12 has .select
        if hasattr(eps, "select"):
            group = eps.select(group="voly.auth_providers")
        else:  # pragma: no cover
            group = eps.get("voly.auth_providers", [])  # type: ignore[arg-type]
        for ep in group:
            name = (ep.name or "").strip().lower()
            if not name:
                continue

            def _factory(load=ep.load) -> AuthProvider:
                obj = load()
                # Support class or instance
                return obj() if isinstance(obj, type) else obj

            out[name] = _factory
    except Exception as exc:  # noqa: BLE001
        _log.debug("auth entry points not loaded: %s", exc)
    return out


def list_provider_names() -> list[str]:
    names = set(_BUILTIN)
    names.update(_entry_point_providers())
    return sorted(names)


def get_provider(auth: AuthConfig | None) -> AuthProvider | None:
    """Resolve provider for config; None if auth off / not selected."""
    if auth is None or not auth.enabled:
        return None
    name = (auth.provider or "local").strip().lower() or "local"
    factories = dict(_BUILTIN)
    factories.update(_entry_point_providers())
    factory = factories.get(name)
    if factory is None:
        _log.error(
            "Unknown auth.provider=%r (known: %s). Install Team package or use local.",
            name,
            ", ".join(sorted(factories)),
        )
        return None
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001
        _log.error("Failed to load auth provider %r: %s", name, exc)
        return None


def verify_bearer(token: str, auth: AuthConfig) -> str:
    """Verify token via resolved provider; return subject string."""
    provider = get_provider(auth)
    if provider is None:
        raise InvalidTokenError("auth provider not available")
    if not provider.is_enforced(auth):
        raise InvalidTokenError("auth not enforced")
    payload = provider.verify_token(token, auth)
    return payload.sub


def status_for_auth(auth: AuthConfig | None) -> dict[str, Any]:
    """Build public /api/auth/status body."""
    if auth is None or not auth.enabled:
        return {
            "enabled": False,
            "mode": "open-localhost",
            "provider": "none",
        }
    provider = get_provider(auth)
    if provider is None:
        return {
            "enabled": False,
            "mode": "open-localhost",
            "provider": "none",
            "error": f"unknown or unloadable provider: {auth.provider}",
        }
    if not provider.is_enforced(auth):
        return {
            "enabled": False,
            "mode": "open-localhost",
            "provider": "none",
            "configured_provider": provider.name,
        }
    return provider.status_payload(auth)


__all__ = [
    "AuthProvider",
    "LocalProvider",
    "get_provider",
    "list_provider_names",
    "status_for_auth",
    "verify_bearer",
]
