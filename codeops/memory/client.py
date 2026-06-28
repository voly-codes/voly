"""
MemoryClient — HTTP client for semantic memory Worker (Vectorize + D1).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "CodeOps/0.1 (+https://github.com/codeops)"


class MemoryClientError(Exception):
    pass


class MemoryClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MemoryClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MemoryClientError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def add(
        self,
        title: str,
        content: str,
        *,
        category: str = "context",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        entry_id: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "title": title,
            "content": content,
            "category": category,
            "tags": tags or [],
            "metadata": metadata or {},
            "importance": importance,
        }
        if entry_id:
            body["id"] = entry_id
        data = self._request("POST", "/memory/add", body=body)
        return str(data["id"])

    def search(self, query: str, limit: int = 5, category: str = "") -> list[dict[str, Any]]:
        body: dict[str, Any] = {"query": query, "limit": limit}
        if category:
            body["category"] = category
        data = self._request("POST", "/memory/search", body=body)
        return list(data.get("results", []))

    def get(self, entry_id: str) -> dict[str, Any]:
        return self._request("GET", f"/memory/{urllib.parse.quote(entry_id, safe='')}")

    def list_entries(self, category: str = "", limit: int = 20) -> list[dict[str, Any]]:
        path = f"/memory?limit={limit}"
        if category:
            path += f"&category={urllib.parse.quote(category, safe='')}"
        data = self._request("GET", path)
        return list(data.get("memories", []))


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_memory_url(config_url: str = "") -> str:
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    for key in ("CF_WORKER_MEMORY_URL", "MEMORY_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def resolve_memory_token() -> str:
    for key in ("CF_WORKER_MEMORY_TOKEN", "CLOUDFLARE_API_TOKEN"):
        token = os.environ.get(key, "").strip()
        if token:
            return token
    return ""


def create_memory_client(base_url: str = "", token: str = "") -> MemoryClient | None:
    url = resolve_memory_url(base_url)
    if not url:
        return None
    return MemoryClient(url, token=token or resolve_memory_token())
