"""
WorkflowClient — HTTP client for persistent workflow Worker (D1-backed).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "VOLY/0.1 (+https://github.com/voly)"


class WorkflowClientError(Exception):
    pass


class WorkflowClient:
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
            raise WorkflowClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WorkflowClientError(str(exc.reason)) from exc

    def list_workflows(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/workflows")
        return list(data.get("workflows", []))

    def start(self, workflow_name: str, task: str, inputs: dict[str, Any] | None = None) -> str:
        data = self._request(
            "POST",
            "/workflow/start",
            body={"workflow_name": workflow_name, "task": task, "inputs": inputs or {}},
        )
        return str(data["instance_id"])

    def get_status(self, instance_id: str) -> dict[str, Any]:
        return self._request("GET", f"/workflow/status/{urllib.parse.quote(instance_id, safe='')}")

    def save_instance(self, instance_id: str, payload: dict[str, Any]) -> None:
        self._request("PUT", f"/workflow/instance/{urllib.parse.quote(instance_id, safe='')}", body=payload)

    def approve(self, instance_id: str, step: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/approve",
            body={"instance_id": instance_id, "step": step},
        )

    def reject(self, instance_id: str, step: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/reject",
            body={"instance_id": instance_id, "step": step},
        )

    def list_instances(self, limit: int = 20) -> list[dict[str, Any]]:
        data = self._request("GET", f"/workflow/instances?limit={limit}")
        return list(data.get("instances", []))


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_workflow_url(config_url: str = "") -> str:
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    for key in ("CF_WORKER_WORKFLOW_URL", "WORKFLOW_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def resolve_workflow_token() -> str:
    for key in ("CF_WORKER_WORKFLOW_TOKEN", "CLOUDFLARE_API_TOKEN"):
        token = os.environ.get(key, "").strip()
        if token:
            return token
    return ""


def create_workflow_client(base_url: str = "", token: str = "") -> WorkflowClient | None:
    url = resolve_workflow_url(base_url)
    if not url:
        return None
    return WorkflowClient(url, token=token or resolve_workflow_token())
