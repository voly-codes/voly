"""Clerk JWT verification via JWKS (RS256).

Uses PyJWT's PyJWKClient — no extra dependency beyond PyJWT (voly[ui]).
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import jwt
from jwt import PyJWKClient

from voly.web.auth.jwt import ExpiredTokenError, InvalidTokenError, TokenPayload

if TYPE_CHECKING:
    from voly.config import AuthConfig

_log = logging.getLogger("voly.web.auth.clerk")
_clients: dict[str, PyJWKClient] = {}
_lock = threading.Lock()


def _jwks_url(auth: AuthConfig) -> str:
    if auth.clerk_jwks_url:
        return auth.clerk_jwks_url.strip()
    if auth.clerk_issuer:
        return auth.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
    raise InvalidTokenError("Clerk JWKS URL not configured")


def _client(jwks_url: str) -> PyJWKClient:
    with _lock:
        c = _clients.get(jwks_url)
        if c is None:
            c = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
            _clients[jwks_url] = c
        return c


def decode_clerk_token(token: str, auth: AuthConfig) -> TokenPayload:
    """Validate a Clerk session JWT and return a TokenPayload (sub = user id)."""
    if not token:
        raise InvalidTokenError("empty token")
    try:
        jwks_url = _jwks_url(auth)
    except InvalidTokenError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InvalidTokenError(f"clerk config: {exc}") from exc

    try:
        client = _client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        options: dict[str, Any] = {
            "require": ["exp", "iat", "sub"],
            "verify_aud": bool(auth.clerk_audience),
        }
        kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": options,
        }
        if auth.clerk_issuer:
            kwargs["issuer"] = auth.clerk_issuer.rstrip("/")
        if auth.clerk_audience:
            kwargs["audience"] = auth.clerk_audience

        data = jwt.decode(token, signing_key.key, **kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("invalid clerk token") from exc
    except Exception as exc:  # noqa: BLE001
        _log.warning("clerk token verify failed: %s", exc)
        raise InvalidTokenError("invalid clerk token") from exc

    return TokenPayload(
        sub=str(data["sub"]),
        exp=int(data["exp"]),
        iat=int(data.get("iat") or 0),
        token_type=str(data.get("type") or "clerk"),
    )


def clear_jwks_cache() -> None:
    """Test helper — drop cached JWKS clients."""
    with _lock:
        _clients.clear()
