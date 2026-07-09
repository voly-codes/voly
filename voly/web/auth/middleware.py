"""ASGI middleware that enforces pluggable auth on protected API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from voly.web.auth.jwt import ExpiredTokenError, InvalidTokenError
from voly.web.auth.providers import get_provider

if TYPE_CHECKING:
    from voly.config import AuthConfig

PUBLIC_API_PREFIXES = (
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
    "/api/auth/",
    "/api/status",
)


def _is_public_api_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


class JWTAuthMiddleware:
    """Reject unauthenticated requests to /api/* when a provider is enforced."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        auth = _resolve_auth_config(request)
        provider = get_provider(auth) if auth is not None else None
        if auth is None or provider is None or not provider.is_enforced(auth):
            await self.app(scope, receive, send)
            return

        path = request.url.path
        if not path.startswith("/api/") or _is_public_api_path(path):
            await self.app(scope, receive, send)
            return

        token = _extract_bearer(request.headers.get("authorization", ""))
        # EventSource cannot set Authorization headers — allow access_token query
        # for GET streams only (e.g. /api/tasks/stream).
        if token is None and request.method == "GET":
            token = (request.query_params.get("access_token") or "").strip() or None
        if token is None:
            await _unauthorized(scope, receive, send, "Missing bearer token")
            return

        try:
            payload = provider.verify_token(token, auth)
            subject = payload.sub
        except ExpiredTokenError:
            await _unauthorized(scope, receive, send, "Token expired")
            return
        except InvalidTokenError:
            await _unauthorized(scope, receive, send, "Invalid token")
            return

        new_scope = dict(scope)
        state = dict(new_scope.get("state") or {})
        state["auth_user"] = subject
        new_scope["state"] = state
        await self.app(new_scope, receive, send)


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


async def _unauthorized(scope: Scope, receive: Receive, send: Send, detail: str) -> None:
    response = JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
    await response(scope, receive, send)
