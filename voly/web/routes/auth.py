"""Routes: /api/auth/* — login, status, provider probe."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from voly.web.auth.jwt import (
    InvalidCredentialsError,
    authenticate_user,
    jwt_auth_from_config,
)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _auth_from_request(request: Request):
    state = getattr(request.app.state, "app", None)
    config = getattr(state, "config", None) if state is not None else None
    return getattr(config, "auth", None) if config is not None else None


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request) -> dict[str, Any]:
    """Exchange username/password for a JWT (local provider only)."""
    auth = _auth_from_request(request)

    if auth is None or not auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled (localhost-only mode)",
        )
    provider = (auth.provider or "local").strip().lower()
    if provider == "clerk":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clerk auth is enabled — sign in via the Clerk UI, not /api/auth/login",
        )
    if not auth.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth enabled but jwt_secret is not configured",
        )
    if not auth.users:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth enabled but no users configured",
        )

    try:
        username = authenticate_user(body.username, body.password, auth.users)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token = jwt_auth_from_config(auth).create_access_token(username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": auth.access_token_expire_minutes * 60,
        "provider": "local",
    }


@router.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    """Public probe: whether auth is enforced and which provider."""
    auth = _auth_from_request(request)
    if auth is None or not auth.enabled:
        return {
            "enabled": False,
            "mode": "open-localhost",
            "provider": "none",
        }

    provider = (auth.provider or "local").strip().lower()
    if provider == "clerk" and auth.is_enforced():
        return {
            "enabled": True,
            "mode": "clerk",
            "provider": "clerk",
            "clerk": {
                "publishable_key": auth.clerk_publishable_key or "",
            },
        }

    # local JWT
    enforced = auth.is_enforced()
    return {
        "enabled": enforced,
        "mode": "jwt" if enforced else "open-localhost",
        "provider": "local" if enforced else "none",
    }
