"""FastAPI dependencies for pluggable authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from voly.web.auth.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    TokenPayload,
)
from voly.web.auth.providers import get_provider

if TYPE_CHECKING:
    from voly.config import AuthConfig

_bearer = HTTPBearer(auto_error=False)


def _auth_config(request: Request) -> AuthConfig | None:
    state = request.app.state.app
    config = getattr(state, "config", None)
    if config is None:
        return None
    return getattr(config, "auth", None)


def _extract_bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    token = credentials.credentials.strip()
    return token or None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload | None:
    """Return the authenticated user when auth is enforced; None when off."""
    auth = _auth_config(request)
    provider = get_provider(auth) if auth is not None else None
    if auth is None or provider is None or not provider.is_enforced(auth):
        return None

    token = _extract_bearer_token(credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return provider.verify_token(token, auth)
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def require_auth(user: TokenPayload | None = Depends(get_current_user)) -> TokenPayload:
    """Require a valid token when auth is enabled."""
    if user is None:
        return TokenPayload(sub="anonymous", exp=0, iat=0)
    return user
