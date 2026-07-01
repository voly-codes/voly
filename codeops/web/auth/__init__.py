"""JWT authentication for the CodeOps FastAPI web UI."""

from codeops.web.auth.dependencies import get_current_user, require_auth
from codeops.web.auth.jwt import JWTAuth, TokenPayload, authenticate_user
from codeops.web.auth.middleware import JWTAuthMiddleware

__all__ = [
    "JWTAuth",
    "JWTAuthMiddleware",
    "TokenPayload",
    "authenticate_user",
    "get_current_user",
    "require_auth",
]
