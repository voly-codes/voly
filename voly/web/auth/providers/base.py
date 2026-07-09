"""Auth provider protocol — open-core plug for local JWT and Team SSO.

Implementations live in this package (local, optional clerk) or in a future
external package registered via entry point group ``voly.auth_providers``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from voly.config import AuthConfig
    from voly.web.auth.jwt import TokenPayload


@runtime_checkable
class AuthProvider(Protocol):
    """Pluggable authentication backend for ``voly.web``."""

    #: Stable id: ``local``, ``clerk``, or Team package id.
    name: str

    def is_enforced(self, auth: AuthConfig) -> bool:
        """Whether middleware should require a valid token for this config."""
        ...

    def verify_token(self, token: str, auth: AuthConfig) -> TokenPayload:
        """Validate bearer token; raise ExpiredTokenError / InvalidTokenError."""
        ...

    def status_payload(self, auth: AuthConfig) -> dict[str, Any]:
        """Public ``GET /api/auth/status`` body when this provider is selected."""
        ...

    def supports_password_login(self) -> bool:
        """True if ``POST /api/auth/login`` username/password is supported."""
        ...
