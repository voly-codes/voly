"""Backward-compatible shim — implementation lives in providers.clerk.

.. deprecated::
    Import from ``voly.web.auth.providers.clerk`` instead.
    This path remains for Phase 2 compatibility; Phase 3 may remove it when
    Clerk moves to the private ``voly-team`` package.
"""
from __future__ import annotations

from voly.web.auth.providers.clerk import (  # noqa: F401
    ClerkProvider,
    clear_jwks_cache,
    decode_clerk_token,
)

__all__ = ["ClerkProvider", "clear_jwks_cache", "decode_clerk_token"]
