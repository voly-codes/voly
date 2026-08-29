"""
AgentMemoryClient — HTTP adapter for Cloudflare Agent Memory API.

Maps VOLY MemoryClient-shaped calls onto Agent Memory remember/recall:

  add()    → POST .../remember
  search() → POST .../recall  (candidates → VOLY result rows)
  get()    → GET  .../memories/:id
  list()   → GET  .../memories
  health() → GET  .../namespaces/:name

Also exposes the managed lifecycle API directly:

  ingest()         → POST   .../ingest
  get_summary()    → POST   .../summary
  delete()         → DELETE .../memories/:id
  delete_session() → DELETE .../sessions/:id
  delete_profile() → DELETE .../profiles/:profile

Docs: https://developers.cloudflare.com/agent-memory/api/http-api/
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from voly.memory.client import USER_AGENT, MemoryClientError, resolve_memory_token

_log = logging.getLogger("voly.memory.agent_memory")

_API_ROOT = "https://api.cloudflare.com/client/v4"


class AgentMemoryClient:
    """Cloudflare Agent Memory HTTP client with MemoryClient-compatible surface."""

    def __init__(
        self,
        account_id: str,
        namespace: str,
        profile: str,
        *,
        token: str = "",
        api_root: str = _API_ROOT,
        timeout: float = 30.0,
    ):
        if not account_id or not namespace or not profile:
            raise ValueError("account_id, namespace, and profile are required")
        self.account_id = account_id.strip()
        self.namespace = namespace.strip()
        self.profile = profile.strip()
        self.token = token or resolve_memory_token()
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout

    @property
    def profile_base(self) -> str:
        ns = urllib.parse.quote(self.namespace, safe="")
        pf = urllib.parse.quote(self.profile, safe="")
        return (
            f"{self.api_root}/accounts/{self.account_id}/agent-memory"
            f"/namespaces/{ns}/profiles/{pf}"
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        from voly.correlation import correlation_headers
        return correlation_headers(headers)

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MemoryClientError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MemoryClientError(str(exc.reason)) from exc

        if isinstance(payload, dict) and payload.get("success") is False:
            errors = payload.get("errors") or []
            raise MemoryClientError(f"Agent Memory API error: {errors}")
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    def health(self) -> dict[str, Any]:
        ns = urllib.parse.quote(self.namespace, safe="")
        url = (
            f"{self.api_root}/accounts/{self.account_id}/agent-memory"
            f"/namespaces/{ns}"
        )
        result = self._request("GET", url)
        return {
            "status": "ok",
            "service": "cloudflare-agent-memory",
            "namespace": self.namespace,
            "profile": self.profile,
            "namespace_id": (result or {}).get("id") if isinstance(result, dict) else None,
        }

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
        del importance  # Agent Memory has no importance field
        meta = metadata or {}
        session_id = str(meta.get("session_id") or meta.get("sessionId") or entry_id or "")
        # Preserve VOLY category/title in free-text content (Agent Memory is untyped free text).
        tag_suffix = f" tags={','.join(tags)}" if tags else ""
        text = f"[{category}] {title}: {content}{tag_suffix}".strip()
        body: dict[str, Any] = {"content": text}
        if session_id:
            body["sessionId"] = session_id
        result = self._request("POST", f"{self.profile_base}/remember", body=body)
        if isinstance(result, dict) and result.get("id"):
            return str(result["id"])
        return entry_id or ""

    def ingest(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str = "",
    ) -> None:
        """Extract durable memories from a bounded conversation batch."""
        if not messages:
            raise ValueError("messages must not be empty")
        normalized: list[dict[str, str]] = []
        for item in messages:
            if not isinstance(item, dict):
                raise ValueError("each message must be an object")
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if not role or not content:
                raise ValueError("each message requires role and content")
            message = {"role": role, "content": content}
            timestamp = str(item.get("timestamp") or "").strip()
            if timestamp:
                message["timestamp"] = timestamp
            normalized.append(message)
        body: dict[str, Any] = {"messages": normalized}
        if session_id.strip():
            body["sessionId"] = session_id.strip()
        self._request("POST", f"{self.profile_base}/ingest", body=body)

    def get_summary(self, *, session_id: str = "") -> str:
        """Return Cloudflare's Markdown summary for the configured profile."""
        body: dict[str, str] = {}
        if session_id.strip():
            body["sessionId"] = session_id.strip()
        result = self._request("POST", f"{self.profile_base}/summary", body=body)
        return str(result.get("summary") or "") if isinstance(result, dict) else ""

    def delete(self, entry_id: str) -> dict[str, Any]:
        """Delete one remote memory and return the deleted memory payload."""
        if not entry_id.strip():
            raise ValueError("entry_id is required")
        mid = urllib.parse.quote(entry_id.strip(), safe="")
        result = self._request("DELETE", f"{self.profile_base}/memories/{mid}")
        return result if isinstance(result, dict) else {}

    def delete_session(self, session_id: str) -> None:
        """Delete all remote messages and memories in one session."""
        if not session_id.strip():
            raise ValueError("session_id is required")
        sid = urllib.parse.quote(session_id.strip(), safe="")
        self._request("DELETE", f"{self.profile_base}/sessions/{sid}")

    def delete_profile(self) -> None:
        """Delete the configured remote profile and all of its contents."""
        self._request("DELETE", self.profile_base)

    def search(self, query: str, limit: int = 5, category: str = "") -> list[dict[str, Any]]:
        del category  # Agent Memory recall has no category filter
        body = {
            "query": query,
            "thinkingLevel": "low",
            "responseLength": "short",
        }
        result = self._request("POST", f"{self.profile_base}/recall", body=body)
        if not isinstance(result, dict):
            return []

        answer = str(result.get("answer") or "").strip()
        candidates = list(result.get("candidates") or [])
        rows: list[dict[str, Any]] = []
        for cand in candidates[:limit]:
            if not isinstance(cand, dict):
                continue
            summary = str(cand.get("summary") or "")
            rows.append({
                "id": str(cand.get("id") or ""),
                "title": summary[:120] or "memory",
                "content": answer or summary,
                "category": "context",
                "tags": [],
                "score": cand.get("score"),
                "source": "agent-memory",
            })
        # If recall returned an answer but no candidates, still surface the answer.
        if not rows and answer:
            rows.append({
                "id": "",
                "title": "recall",
                "content": answer,
                "category": "context",
                "tags": [],
                "score": None,
                "source": "agent-memory",
            })
        return rows

    def get(self, entry_id: str) -> dict[str, Any]:
        mid = urllib.parse.quote(entry_id, safe="")
        result = self._request("GET", f"{self.profile_base}/memories/{mid}")
        if not isinstance(result, dict):
            return {}
        return {
            "id": str(result.get("id") or entry_id),
            "title": str(result.get("summary") or "")[:120],
            "content": str(result.get("content") or result.get("summary") or ""),
            "category": "context",
            "tags": [],
            "type": result.get("type"),
            "sessionId": result.get("sessionId"),
        }

    def list_entries(self, category: str = "", limit: int = 20) -> list[dict[str, Any]]:
        del category
        url = f"{self.profile_base}/memories?per_page={int(limit)}"
        result = self._request("GET", url)
        items = result if isinstance(result, list) else []
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "")
            rows.append({
                "id": str(item.get("id") or ""),
                "title": summary[:120],
                "content": summary,  # list omits full content
                "category": "context",
                "tags": [],
                "type": item.get("type"),
            })
        return rows


def resolve_agent_memory_account_id(config_value: str = "") -> str:
    val = (config_value or "").strip()
    if val and "${" not in val:
        return val
    return os.environ.get("CF_ACCOUNT_ID", "").strip()


def resolve_agent_memory_namespace(config_value: str = "") -> str:
    val = (config_value or "").strip()
    if val and "${" not in val:
        return val
    return os.environ.get("CF_AGENT_MEMORY_NAMESPACE", "").strip() or "voly"


def resolve_agent_memory_profile(config_value: str = "") -> str:
    val = (config_value or "").strip()
    if val and "${" not in val:
        return val
    return os.environ.get("CF_AGENT_MEMORY_PROFILE", "").strip() or "default"


def create_agent_memory_client(
    *,
    account_id: str = "",
    namespace: str = "",
    profile: str = "",
    token: str = "",
    api_root: str = "",
) -> AgentMemoryClient | None:
    aid = resolve_agent_memory_account_id(account_id)
    if not aid:
        _log.debug("agent_memory: CF_ACCOUNT_ID not set — remote client disabled")
        return None
    ns = resolve_agent_memory_namespace(namespace)
    pf = resolve_agent_memory_profile(profile)
    try:
        return AgentMemoryClient(
            aid,
            ns,
            pf,
            token=token or resolve_memory_token(),
            api_root=api_root or _API_ROOT,
        )
    except ValueError:
        return None
