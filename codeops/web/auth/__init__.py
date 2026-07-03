"""JWT authentication for the VOLY FastAPI web UI."""

from voly.web.auth.dependencies import get_current_user, require_auth
from voly.web.auth.jwt import JWTAuth, TokenPayload, authenticate_user
from voly.web.auth.middleware import JWTAuthMiddleware

__all__ = [
    "JWTAuth",
    "JWTAuthMiddleware",
    "TokenPayload",
    "authenticate_user",
    "get_current_user",
    "require_auth",
]
