"""HTTP client for VOLY Catalog CF Worker (optional)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "VOLY/0.1 (+https://github.com/codeops)"


class CatalogClientError(Exception):
    pass


class CatalogClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> CatalogClient | None:
        url = os.getenv("CF_WORKER_CATALOG_URL", "").strip()
        if not url:
            return None
        token = os.getenv("CF_CATALOG_API_TOKEN", os.getenv("CF_API_TOKEN", ""))
        return cls(url, token=token)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(json_body=body is not None),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CatalogClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CatalogClientError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_models(self) -> dict[str, Any]:
        return self._request("GET", "/models")

    def sync_models(self, models: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", "/models/sync", body={"models": models})

    def match(self, task: str, *, budget_usd: float = 1.0) -> dict[str, Any]:
        return self._request(
            "POST",
            "/match",
            body={"task": task, "budget_usd": budget_usd},
        )
