"""Local HS256 JWT auth provider (open-core default)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from voly.web.auth.jwt import InvalidTokenError, TokenPayload, jwt_auth_from_config

if TYPE_CHECKING:
    from voly.config import AuthConfig


class LocalProvider:
    name = "local"

    def is_enforced(self, auth: AuthConfig) -> bool:
        return bool(auth.enabled and auth.jwt_secret)

    def verify_token(self, token: str, auth: AuthConfig) -> TokenPayload:
        if not auth.jwt_secret:
            raise InvalidTokenError("local jwt_secret not configured")
        return jwt_auth_from_config(auth).decode_token(token)

    def status_payload(self, auth: AuthConfig) -> dict[str, Any]:
        enforced = self.is_enforced(auth)
        return {
            "enabled": enforced,
            "mode": "jwt" if enforced else "open-localhost",
            "provider": "local" if enforced else "none",
        }

    def supports_password_login(self) -> bool:
        return True
