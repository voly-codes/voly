"""Routes: /api/providers/keys — BYOK provider keys in CF Secrets Store.

Security invariants (docs/backend/ai-gateway.md § BYOK):
- key values transit this process once (POST body → CF API) and are never
  logged or written to disk; list/GET return names only (CF cannot read values);
- endpoints are localhost-only: this is a self-host management surface, not a
  public API — the auth module was removed, so the guard is explicit here.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

_log = logging.getLogger("voly.web.providers")

_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _require_local(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="provider keys API is localhost-only")


def _client():
    from voly.ai_gateway.cf_secrets import CFSecretsClient

    client = CFSecretsClient()
    if not client.configured:
        raise HTTPException(
            status_code=400,
            detail="CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set "
                   "(token needs Secrets Store Edit)",
        )
    return client


def _resolve_slug(provider: str) -> str:
    from voly.ai_gateway.credentials import BYOK_PROVIDER_SLUGS

    slug = BYOK_PROVIDER_SLUGS.get(provider) or (
        provider if provider in BYOK_PROVIDER_SLUGS.values() else ""
    )
    if not slug:
        supported = sorted(set(BYOK_PROVIDER_SLUGS.values()))
        raise HTTPException(
            status_code=400,
            detail=f"provider {provider!r} is not BYOK-eligible; supported: {supported}",
        )
    return slug


class ProviderKeyIn(BaseModel):
    provider: str
    key: str = Field(repr=False)  # keep the value out of reprs/validation errors
    alias: str = "default"


@router.get("/api/providers/keys")
def list_keys(request: Request) -> dict[str, Any]:
    _require_local(request)
    from voly.config import load_config

    cfg = load_config()
    byok_enabled = bool(getattr(cfg.ai_gateway, "byok_enabled", False))
    try:
        client = _client()
        keys = client.list_provider_keys()
        return {"configured": True, "byok_enabled": byok_enabled, "keys": keys}
    except HTTPException as exc:
        return {"configured": False, "byok_enabled": byok_enabled, "keys": [],
                "hint": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001 — surface CF errors as data, not 500
        return {"configured": True, "byok_enabled": byok_enabled, "keys": [],
                "error": str(exc)}


@router.post("/api/providers/keys")
def create_key(request: Request, body: ProviderKeyIn) -> dict[str, Any]:
    _require_local(request)
    slug = _resolve_slug(body.provider.strip().lower())
    if not body.key.strip():
        raise HTTPException(status_code=400, detail="key must not be empty")
    client = _client()
    try:
        name = client.create_provider_key(slug, body.key.strip(), alias=body.alias.strip() or "default")
    except Exception as exc:  # noqa: BLE001
        # exc comes from CFSecretsClient and never contains the key value.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _log.info("provider key stored: %s", name)
    return {
        "ok": True,
        "name": name,
        "hint": "enable ai_gateway.byok_enabled in voly.yaml to route via the gateway",
    }


@router.delete("/api/providers/keys/{provider}")
def delete_key(request: Request, provider: str, alias: str = "default") -> dict[str, Any]:
    _require_local(request)
    slug = _resolve_slug(provider.strip().lower())
    client = _client()
    try:
        deleted = client.delete_provider_key(slug, alias=alias)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"no stored key for {slug} (alias={alias})")
    return {"ok": True}
