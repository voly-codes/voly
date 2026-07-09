"""JWT token creation and verification."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from voly.config import AuthConfig

TOKEN_TYPE_ACCESS = "access"
_SUPPORTED_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    exp: int
    iat: int
    token_type: str = TOKEN_TYPE_ACCESS


class JWTAuthError(Exception):
    """Base JWT auth error."""


class InvalidCredentialsError(JWTAuthError):
    """Username or password rejected."""


class InvalidTokenError(JWTAuthError):
    """Token missing, malformed, or invalid."""


class ExpiredTokenError(JWTAuthError):
    """Token has expired."""


class JWTAuth:
    """Encode and decode access tokens."""

    def __init__(
        self,
        secret: str,
        *,
        algorithm: str = "HS256",
        expire_minutes: int = 60,
    ) -> None:
        if not secret:
            raise ValueError("JWT secret must not be empty")
        if algorithm not in _SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported JWT algorithm: {algorithm}")
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def create_access_token(
        self,
        subject: str,
        *,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._expire_minutes)).timestamp()),
            "type": TOKEN_TYPE_ACCESS,
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_token(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError("token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError("invalid token") from exc

        token_type = data.get("type", TOKEN_TYPE_ACCESS)
        if token_type != TOKEN_TYPE_ACCESS:
            raise InvalidTokenError("invalid token type")

        return TokenPayload(
            sub=str(data["sub"]),
            exp=int(data["exp"]),
            iat=int(data["iat"]),
            token_type=token_type,
        )


def authenticate_user(username: str, password: str, users: dict[str, str]) -> str:
    """Validate credentials and return the username on success."""
    stored = users.get(username)
    if stored is None:
        # Constant-time dummy compare when user is unknown.
        secrets.compare_digest(password, password)
        raise InvalidCredentialsError("invalid credentials")
    if not hmac.compare_digest(stored, password):
        raise InvalidCredentialsError("invalid credentials")
    return username


def jwt_auth_from_config(auth: AuthConfig) -> JWTAuth:
    """Build a JWTAuth instance from AuthConfig."""
    return JWTAuth(
        auth.jwt_secret,
        algorithm=auth.jwt_algorithm,
        expire_minutes=auth.access_token_expire_minutes,
    )
