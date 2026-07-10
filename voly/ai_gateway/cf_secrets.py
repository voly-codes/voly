"""CF Secrets Store client for AI Gateway BYOK provider keys.

Flow (docs/proposals/byok-cf-secrets.md, PR4): secrets are created in the
account's Secrets Store with the BYOK naming convention
``{gateway_id}_{provider_slug}_{alias}`` and the ``ai_gateway`` scope;
AI Gateway resolves them at runtime **by name** (the ``secret_id`` is not used
for lookup, per CF docs). Values are write-only: the CF API never returns
them, and this module never logs or persists them.

Requires ``CLOUDFLARE_API_TOKEN`` with **Account → Secrets Store → Edit**.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

_log = logging.getLogger("voly.ai_gateway.cf_secrets")

_API_BASE = "https://api.cloudflare.com/client/v4"


class CFSecretsError(RuntimeError):
    """CF API failure; message is safe to surface (never contains key values)."""


class CFSecretsClient:
    def __init__(self, account_id: str = "", api_token: str = "", gateway_id: str = ""):
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN", "")
        self.gateway_id = gateway_id or os.environ.get("CLOUDFLARE_AI_GATEWAY_ID", "default")
        self._store_id = ""

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.api_token)

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{_API_BASE}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
        )
        # Log method+path only — request bodies may carry secret values.
        _log.info("cf-secrets %s %s", method, path)
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            try:
                errors = json.loads(text).get("errors", [])
                msg = "; ".join(str(err.get("message", "")) for err in errors) or text[:200]
            except Exception:  # noqa: BLE001
                msg = text[:200]
            raise CFSecretsError(f"CF API {e.code} on {method} {path}: {msg}") from e
        if not payload.get("success", False):
            errors = payload.get("errors", [])
            msg = "; ".join(str(err.get("message", "")) for err in errors) or "unknown error"
            raise CFSecretsError(f"CF API error on {method} {path}: {msg}")
        return payload.get("result")

    # ── Store ──────────────────────────────────────────────────────────────────

    def store_id(self) -> str:
        """Account's Secrets Store id (first store; created on first dashboard use)."""
        if self._store_id:
            return self._store_id
        stores = self._request("GET", f"/accounts/{self.account_id}/secrets_store/stores") or []
        if not stores:
            raise CFSecretsError(
                "no Secrets Store found — open CF Dashboard → Secrets Store once "
                "to provision the default store"
            )
        self._store_id = str(stores[0].get("id", ""))
        return self._store_id

    # ── Provider keys (BYOK naming convention) ────────────────────────────────

    def secret_name(self, provider_slug: str, alias: str = "default") -> str:
        return f"{self.gateway_id}_{provider_slug}_{alias}"

    def create_provider_key(
        self,
        provider_slug: str,
        value: str,
        alias: str = "default",
        comment: str = "",
    ) -> str:
        """Store a provider API key; returns the secret name. Value is write-only."""
        name = self.secret_name(provider_slug, alias)
        self._request(
            "POST",
            f"/accounts/{self.account_id}/secrets_store/stores/{self.store_id()}/secrets",
            body=[{
                "name": name,
                "value": value,
                "scopes": ["ai_gateway"],
                "comment": comment or f"VOLY BYOK key for {provider_slug}",
            }],
        )
        return name

    def list_provider_keys(self) -> list[dict[str, str]]:
        """Names of gateway-scoped keys for this gateway (values are not readable)."""
        secrets = self._request(
            "GET",
            f"/accounts/{self.account_id}/secrets_store/stores/{self.store_id()}/secrets?per_page=100",
        ) or []
        prefix = f"{self.gateway_id}_"
        out: list[dict[str, str]] = []
        for s in secrets:
            name = str(s.get("name", ""))
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix):]
            provider, sep, alias = rest.rpartition("_")
            if not sep:
                provider, alias = rest, "default"
            out.append({
                "name": name,
                "provider": provider,
                "alias": alias,
                "secret_id": str(s.get("id", "")),
            })
        return out

    def delete_provider_key(self, provider_slug: str, alias: str = "default") -> bool:
        name = self.secret_name(provider_slug, alias)
        for s in self.list_provider_keys():
            if s["name"] == name:
                self._request(
                    "DELETE",
                    f"/accounts/{self.account_id}/secrets_store/stores/{self.store_id()}"
                    f"/secrets/{s['secret_id']}",
                )
                return True
        return False
