"""Routes: /api/auth/* — login and token issue."""

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


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request) -> dict[str, Any]:
    """Exchange username/password for a JWT access token."""
    state = getattr(request.app.state, "app", None)
    config = getattr(state, "config", None) if state is not None else None
    auth = getattr(config, "auth", None) if config is not None else None

    if auth is None or not auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled (localhost-only mode)",
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
    }


@router.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    """Public probe: whether JWT auth is enforced."""
    state = getattr(request.app.state, "app", None)
    config = getattr(state, "config", None) if state is not None else None
    auth = getattr(config, "auth", None) if config is not None else None
    enabled = bool(auth and auth.enabled and auth.jwt_secret)
    return {
        "enabled": enabled,
        "mode": "jwt" if enabled else "open-localhost",
    }
