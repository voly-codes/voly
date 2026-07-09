"""Web authentication for the VOLY FastAPI UI (pluggable providers)."""

from voly.web.auth.dependencies import get_current_user, require_auth
from voly.web.auth.jwt import JWTAuth, TokenPayload, authenticate_user
from voly.web.auth.middleware import JWTAuthMiddleware
from voly.web.auth.providers import get_provider, list_provider_names, status_for_auth

__all__ = [
    "JWTAuth",
    "JWTAuthMiddleware",
    "TokenPayload",
    "authenticate_user",
    "get_current_user",
    "get_provider",
    "list_provider_names",
    "require_auth",
    "status_for_auth",
]
