"""Tests for Cloudflare Agent Memory HTTP adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from voly.memory.agent_memory_client import (
    AgentMemoryClient,
    create_agent_memory_client,
)
from voly.memory.client import create_remote_memory_client
from voly.memory.store import MemoryStore


def _fake_urlopen(payload: dict):
    def fake(req, timeout=30):
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        return resp

    return fake


def test_create_agent_memory_client_requires_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    assert create_agent_memory_client() is None


def test_create_remote_memory_client_agent_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc-1")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    client = create_remote_memory_client(backend="agent_memory")
    assert isinstance(client, AgentMemoryClient)
    assert client.account_id == "acc-1"
    assert "agent-memory" in client.profile_base


def test_create_remote_memory_client_local() -> None:
    assert create_remote_memory_client(backend="local") is None


def test_agent_memory_remember_and_recall() -> None:
    client = AgentMemoryClient("acc", "voly", "default", token="tok")
    captured: list = []

    remember_payload = {
        "success": True,
        "result": {"id": "mem-1", "summary": "Prefer concise", "content": "Prefer concise"},
    }

    def fake_remember(req, timeout=30):
        captured.append(req)
        resp = MagicMock()
        resp.read.return_value = json.dumps(remember_payload).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_remember):
        mid = client.add("Pref", "Prefer concise answers", category="decision", entry_id="local-1")
    assert mid == "mem-1"
    req = captured[0]
    assert req.full_url.endswith("/remember")
    body = json.loads(req.data.decode())
    assert "[decision] Pref:" in body["content"]
    assert body["sessionId"] == "local-1"

    recall_payload = {
        "success": True,
        "result": {
            "answer": "Prefer concise answers.",
            "candidates": [{"id": "mem-1", "summary": "Prefer concise", "score": 0.9}],
        },
    }
    with patch("urllib.request.urlopen", _fake_urlopen(recall_payload)):
        rows = client.search("how to answer?")
    assert len(rows) == 1
    assert rows[0]["id"] == "mem-1"
    assert rows[0]["content"] == "Prefer concise answers."
    assert rows[0]["source"] == "agent-memory"


def test_memory_store_uses_agent_memory_backend(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    store = MemoryStore(
        db_path=tmp_path / "m.db",
        backend="agent_memory",
        agent_memory_account_id="acc",
        agent_memory_namespace="voly",
        agent_memory_profile="default",
    )

    class _Fake:
        def add(self, *a, **k):
            return "remote-id"

        def search(self, query, limit=5, category=""):
            return [{"id": "r1", "title": "T", "content": "C", "category": "context", "tags": []}]

    store._remote_client = _Fake()
    eid = store.add("Title", "Body", category="context")
    assert eid  # local id
    hits = store.search("Body")
    assert hits[0].content == "C"


def test_memory_store_local_backend_skips_remote(tmp_path) -> None:
    store = MemoryStore(db_path=tmp_path / "m.db", backend="local", remote_url="http://example")
    assert store._get_remote_client() is None
    eid = store.add("T", "hello world", category="context")
    hits = store.search("hello")
    assert any(h.id == eid for h in hits)
