"""
FederationClient — HTTP client for A2A federation Worker (D1 + Queues).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "VOLY/0.1 (+https://github.com/codeops)"


class FederationClientError(Exception):
    pass


class FederationClient:
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
        logger.debug("A2A federation %s %s body=%s", method, url, body)
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                result = json.loads(raw) if raw else {}
                logger.debug("A2A federation %s %s → %s", method, path, result)
                return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.error("A2A federation %s %s → HTTP %s: %s", method, url, exc.code, detail)
            raise FederationClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            logger.error("A2A federation %s %s → URLError: %s", method, url, exc.reason)
            raise FederationClientError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_agents(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/agents")
        return list(data.get("agents", []))

    def get_agent_card(self, name: str) -> dict[str, Any]:
        return self._request("GET", f"/agents/{urllib.parse.quote(name, safe='')}/card")

    def register_agent(self, card: dict[str, Any]) -> None:
        self._request("POST", "/agents/register", body={"card": card})

    def create_task(
        self,
        title: str,
        description: str = "",
        *,
        agent_name: str = "",
        async_dispatch: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        data = self._request(
            "POST",
            "/tasks",
            body={
                "agent_name": agent_name,
                "title": title,
                "description": description or title,
                "async": async_dispatch,
                "metadata": metadata or {},
            },
        )
        return str(data["task_id"])

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{urllib.parse.quote(task_id, safe='')}")

    def update_task(
        self,
        task_id: str,
        *,
        state: str | None = None,
        result: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {}
        if state is not None:
            body["state"] = state
        if result is not None:
            body["result"] = result
        if error is not None:
            body["error"] = error
        if metadata is not None:
            body["metadata"] = metadata
        self._request("PUT", f"/tasks/{urllib.parse.quote(task_id, safe='')}", body=body)

    def complete_task(self, task_id: str, result: str) -> None:
        self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(task_id, safe='')}/complete",
            body={"result": result},
        )

    def fail_task(self, task_id: str, error: str) -> None:
        self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(task_id, safe='')}/fail",
            body={"error": error},
        )

    def list_tasks(self, state: str = "", limit: int = 20) -> list[dict[str, Any]]:
        path = f"/tasks?limit={limit}"
        if state:
            path += f"&state={urllib.parse.quote(state, safe='')}"
        data = self._request("GET", path)
        return list(data.get("tasks", []))


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_federation_url(config_url: str = "") -> str:
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    for key in ("CF_WORKER_A2A_URL", "A2A_FEDERATION_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def resolve_federation_token() -> str:
    for key in ("CODEOPS_A2A_TOKEN", "CF_WORKER_A2A_TOKEN"):
        token = os.environ.get(key, "").strip()
        if token:
            return token
    return ""


def create_federation_client(base_url: str = "", token: str = "") -> FederationClient | None:
    url = resolve_federation_url(base_url)
    if not url:
        return None
    return FederationClient(url, token=token or resolve_federation_token())
