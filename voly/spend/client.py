"""
SpendClient — HTTP client for persistent spend tracking (Durable Object).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "VOLY/0.1 (+https://github.com/voly)"


class SpendClientError(Exception):
    pass


class SpendClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 10.0):
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
            raise SpendClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SpendClientError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def record(
        self,
        agent: str,
        cost_usd: float,
        *,
        task_id: str = "",
        model: str = "",
        provider: str = "",
    ) -> None:
        self._request(
            "POST",
            "/spend/record",
            body={
                "agent": agent,
                "cost_usd": cost_usd,
                "task_id": task_id,
                "model": model,
                "provider": provider,
            },
        )

    def check(self, agent: str, daily_limit: float) -> dict[str, Any]:
        path = (
            f"/spend/check?agent={urllib.parse.quote(agent, safe='')}"
            f"&limit={daily_limit}"
        )
        return self._request("GET", path)

    def summary(self, days: int = 1) -> dict[str, Any]:
        return self._request("GET", f"/spend/summary?days={days}")

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        data = self._request("GET", f"/spend/recent?limit={limit}")
        return list(data.get("entries", []))


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_spend_url(config_url: str = "") -> str:
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    for key in ("CF_WORKER_SPEND_URL", "SPEND_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def resolve_spend_token() -> str:
    """Bearer for the spend Worker ``API_TOKEN`` secret.

    Do **not** fall back to ``CLOUDFLARE_API_TOKEN``: that is the account API
    token and almost never matches the worker secret, which only produced
    silent HTTP 401s in the CF Spend UI.
    """
    return os.environ.get("CF_WORKER_SPEND_TOKEN", "").strip()


def create_spend_client(base_url: str = "", token: str = "") -> SpendClient | None:
    url = resolve_spend_url(base_url)
    if not url:
        return None
    return SpendClient(url, token=token or resolve_spend_token())
