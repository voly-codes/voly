"""Tests for A2A federation client and backend."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from voly.a2a.backend import FederationBackend, task_from_remote
from voly.a2a.federation import (
    FederationClient,
    FederationClientError,
    create_federation_client,
    resolve_federation_url,
)


REMOTE_TASK = {
    "id": "task-abc",
    "agent_name": "developer",
    "title": "Implement auth",
    "description": "Implement OAuth2 login",
    "state": "working",
    "result": "",
    "error": "",
    "metadata": {},
    "created_at": 1_700_000_000_000,
    "updated_at": 1_700_000_001_000,
}


def test_resolve_federation_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_A2A_URL", raising=False)
    assert resolve_federation_url("") == ""

    monkeypatch.setenv("CF_WORKER_A2A_URL", "https://a2a.example.com")
    assert resolve_federation_url("") == "https://a2a.example.com"


def test_create_federation_client_none_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_A2A_URL", raising=False)
    assert create_federation_client() is None


def test_task_from_remote_payload() -> None:
    task = task_from_remote(REMOTE_TASK)
    assert task.id == "task-abc"
    assert task.metadata["routed_to"] == "developer"
    assert task.state.value == "working"


def test_federation_client_create_task() -> None:
    client = FederationClient("https://a2a.example.com", token="secret")
    captured: dict = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["method"] = req.method
        resp = MagicMock()
        resp.read.return_value = json.dumps({"task_id": "new-task", "state": "submitted"}).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        task_id = client.create_task("Fix bug", "Fix login bug", agent_name="bugfixer")

    assert task_id == "new-task"
    assert captured["method"] == "POST"
    body = json.loads(captured["data"].decode())
    assert body["agent_name"] == "bugfixer"


def test_federation_client_http_error() -> None:
    client = FederationClient("https://a2a.example.com")

    def fake_urlopen(req, timeout=30):
        raise HTTPError(
            req.full_url, 404, "Not Found", hdrs=None, fp=MagicMock(read=lambda: b'{"error":"missing"}')
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        with pytest.raises(FederationClientError, match="HTTP 404"):
            client.get_task("missing")


def test_federation_backend_sync_agents() -> None:
    client = FederationClient("https://a2a.example.com")
    with patch.object(
        client,
        "list_agents",
        return_value=[
            {
                "name": "developer",
                "description": "Dev agent",
                "url": "https://a2a.example.com/agents/developer",
                "version": "1.0.0",
                "skills": [],
                "capabilities": {},
                "provider": "voly",
            }
        ],
    ):
        backend = FederationBackend(client)
        cards = backend.sync_agents()
        assert len(cards) == 1
        assert cards[0].name == "developer"
