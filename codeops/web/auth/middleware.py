"""ASGI middleware that enforces JWT auth on protected API routes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from voly.web.auth.jwt import ExpiredTokenError, InvalidTokenError, jwt_auth_from_config

if TYPE_CHECKING:
    from voly.config import AuthConfig

PUBLIC_API_PREFIXES = (
    "/api/docs",
    "/api/openapi.json",
    "/api/auth/",
    "/api/status",
)


def _is_public_api_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


class JWTAuthMiddleware:
    """Reject unauthenticated requests to /api/* when auth is enabled."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        auth = _resolve_auth_config(request)
        if auth is None or not auth.enabled or not auth.jwt_secret:
            await self.app(scope, receive, send)
            return

        path = request.url.path
        if not path.startswith("/api/") or _is_public_api_path(path):
            await self.app(scope, receive, send)
            return

        token = _extract_bearer(request.headers.get("authorization", ""))
        if token is None:
            await _unauthorized(send, "Missing bearer token")
            return

        jwt_auth = jwt_auth_from_config(auth)
        try:
            payload = jwt_auth.decode_token(token)
        except ExpiredTokenError:
            await _unauthorized(send, "Token expired")
            return
        except InvalidTokenError:
            await _unauthorized(send, "Invalid token")
            return

        scope = dict(scope)
        scope["state"] = dict(scope.get("state", {}))
        scope["state"]["auth_user"] = payload.sub
        await self.app(scope, receive, send)


def _resolve_auth_config(request: Request) -> AuthConfig | None:
    app_state = getattr(request.app.state, "app", None)
    if app_state is None:
        return None
    config = getattr(app_state, "config", None)
    if config is None:
        return None
    return getattr(config, "auth", None)


def _extract_bearer(header: str) -> str | None:
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


async def _unauthorized(send: Send, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    response = JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
    await response(scope={"type": "http"}, receive=_empty_receive, send=send)


async def _empty_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}
