"""
Remote AG-UI client — forward events to CF AGUISession Durable Object.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "VOLY/0.1 (+https://github.com/voly)"


class RemoteAGUIClient:
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
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def create_session(self, session_id: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {}
        if session_id:
            body["session_id"] = session_id
        return self._request("POST", "/agui/sessions", body=body)

    def emit_event(self, session_id: str, event: dict[str, Any]) -> None:
        path = f"/agui/sessions/{urllib.parse.quote(session_id, safe='')}/events"
        self._request("POST", path, body=event)

    def list_events(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        path = (
            f"/agui/sessions/{urllib.parse.quote(session_id, safe='')}/events"
            f"?limit={limit}"
        )
        data = self._request("GET", path)
        return list(data.get("events", []))

    def session_state(self, session_id: str) -> dict[str, Any]:
        path = f"/agui/sessions/{urllib.parse.quote(session_id, safe='')}/state"
        return self._request("GET", path)


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_agui_remote_url(config_url: str = "") -> str:
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    # AGUI sessions (/agui/*) are served by the spend worker when a dedicated
    # CF_WORKER_AGUI_URL is not configured.
    for key in ("CF_WORKER_AGUI_URL", "AGUI_URL", "AGUI_REMOTE_URL", "CF_WORKER_SPEND_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def create_remote_agui_client(base_url: str = "", token: str = "") -> RemoteAGUIClient | None:
    url = resolve_agui_remote_url(base_url)
    if not url:
        return None
    if not token:
        for key in ("CF_WORKER_SPEND_TOKEN", "CLOUDFLARE_API_TOKEN"):
            token = os.environ.get(key, "").strip()
            if token:
                break
    return RemoteAGUIClient(url, token=token)
