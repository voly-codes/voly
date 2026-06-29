"""
MarketplaceClient — HTTP client for CodeOps Skill Marketplace (Cloudflare Worker).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class MarketplaceError(Exception):
    pass


class MarketplaceClient:
    USER_AGENT = "CodeOps/0.1 (+https://github.com/codeops)"

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

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
            raise MarketplaceError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MarketplaceError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_skills(
        self,
        *,
        page: int = 1,
        limit: int = 20,
        source: str | None = None,
        agent: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        query: dict[str, str] = {
            "page": str(page),
            "limit": str(limit),
            "status": status,
        }
        if source:
            query["source"] = source
        if agent:
            query["agent"] = agent
        return self._request("GET", "/skills", query=query)

    def search(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        return self._request(
            "GET",
            "/skills/search",
            query={"q": query, "limit": str(limit)},
        )

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        return self._request("GET", f"/skills/{urllib.parse.quote(skill_id, safe='')}")

    def download_skill(self, skill_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/skills/{urllib.parse.quote(skill_id, safe='')}/download"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MarketplaceError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MarketplaceError(str(exc.reason)) from exc

    def fetch_builtins(self, limit: int = 200) -> list[dict[str, Any]]:
        """Fetch active builtin skills from CF Marketplace."""
        data = self.list_skills(source="builtin", status="active", limit=limit)
        return data.get("skills", [])

    def publish_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/skills", body=payload)

    def archive_skill(self, skill_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/skills/{urllib.parse.quote(skill_id, safe='')}")
