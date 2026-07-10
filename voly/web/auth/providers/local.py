"""Local HS256 JWT auth provider (open-core default)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from voly.web.auth.jwt import (
    TOKEN_TYPE_STREAM,
    InvalidTokenError,
    TokenPayload,
    jwt_auth_from_config,
)

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

    def issue_stream_ticket(self, subject: str, auth: AuthConfig) -> str | None:
        if not auth.jwt_secret:
            raise InvalidTokenError("local jwt_secret not configured")
        return jwt_auth_from_config(auth).create_stream_token(subject)

    def verify_stream_ticket(self, token: str, auth: AuthConfig) -> TokenPayload:
        if not auth.jwt_secret:
            raise InvalidTokenError("local jwt_secret not configured")
        jwt_auth = jwt_auth_from_config(auth)
        try:
            return jwt_auth.decode_token(token, expected_type=TOKEN_TYPE_STREAM)
        except InvalidTokenError:
            # Fall back to a regular access token — covers callers that never
            # reached POST /api/tasks/stream-token (e.g. it errored client-side).
            return jwt_auth.decode_token(token)

    def status_payload(self, auth: AuthConfig) -> dict[str, Any]:
        enforced = self.is_enforced(auth)
        return {
            "enabled": enforced,
            "mode": "jwt" if enforced else "open-localhost",
            "provider": "local" if enforced else "none",
        }

    def supports_password_login(self) -> bool:
        return True
