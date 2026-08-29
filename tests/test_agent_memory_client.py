"""Tests for Cloudflare Agent Memory HTTP adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from voly.cli.commands.infra import memory
from voly.memory.agent_memory_client import (
    AgentMemoryClient,
    create_agent_memory_client,
    resolve_agent_memory_token,
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


def test_agent_memory_token_never_uses_worker_memory_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CF_WORKER_MEMORY_TOKEN", "worker-token")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-token")

    assert resolve_agent_memory_token() == "cloudflare-token"
    assert AgentMemoryClient("acc", "voly", "profile").token == "cloudflare-token"


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


def test_agent_memory_ingest_and_summary() -> None:
    client = AgentMemoryClient("acc", "voly", "project-a", token="tok")
    captured: list = []

    def fake(req, timeout=30):
        captured.append(req)
        result = (
            {"summary": "## Project\n\nUses FastAPI"} if req.full_url.endswith("/summary") else None
        )
        resp = MagicMock()
        resp.read.return_value = json.dumps({"success": True, "result": result}).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake):
        client.ingest(
            [{"role": "user", "content": "Use FastAPI", "timestamp": "2026-08-30T10:00:00Z"}],
            session_id="run-1",
        )
        summary = client.get_summary(session_id="run-1")

    ingest_body = json.loads(captured[0].data.decode())
    assert captured[0].full_url.endswith("/ingest")
    assert ingest_body["sessionId"] == "run-1"
    assert ingest_body["messages"][0]["content"] == "Use FastAPI"
    assert json.loads(captured[1].data.decode()) == {"sessionId": "run-1"}
    assert summary == "## Project\n\nUses FastAPI"


@pytest.mark.parametrize("messages", [[], [{}], [{"role": "user"}], ["bad"]])
def test_agent_memory_ingest_rejects_invalid_messages(messages) -> None:
    client = AgentMemoryClient("acc", "voly", "project-a", token="tok")
    with pytest.raises(ValueError):
        client.ingest(messages)


def test_agent_memory_ingest_enforces_cloudflare_limits() -> None:
    client = AgentMemoryClient("acc", "voly", "project-a", token="tok")
    message = {"role": "user", "content": "ok"}

    with pytest.raises(ValueError, match="at most 500"):
        client.ingest([message] * 501)
    with pytest.raises(ValueError, match="64 bytes"):
        client.ingest([message], session_id="s" * 65)
    with pytest.raises(ValueError, match="32 KiB"):
        client.ingest([{"role": "user", "content": "я" * 16_385}])


def test_agent_memory_delete_lifecycle_quotes_ids() -> None:
    client = AgentMemoryClient("acc", "voly", "project-a", token="tok")
    captured: list = []

    def fake(req, timeout=30):
        captured.append(req)
        result = {"id": "memory/1"} if "/memories/" in req.full_url else None
        resp = MagicMock()
        resp.read.return_value = json.dumps({"success": True, "result": result}).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake):
        deleted = client.delete("memory/1")
        client.delete_session("session/1")
        client.delete_profile()

    assert deleted["id"] == "memory/1"
    assert captured[0].method == "DELETE"
    assert captured[0].full_url.endswith("/memories/memory%2F1")
    assert captured[1].full_url.endswith("/sessions/session%2F1")
    assert captured[2].full_url.endswith("/profiles/project-a")


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


def test_memory_store_uses_distinct_remote_client_per_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clients: dict[str, MagicMock] = {}

    def create_client(**kwargs):
        profile = kwargs["agent_memory_profile"]
        client = clients.setdefault(profile, MagicMock())
        client.search.return_value = []
        return client

    monkeypatch.setattr("voly.memory.client.create_remote_memory_client", create_client)
    store = MemoryStore(db_path=tmp_path / "m.db", backend="agent_memory")

    store.scoped("project-a").search("database")
    store.scoped("project-b").search("database")
    store.scoped("project-a").search("cache")

    assert set(clients) == {"project-a", "project-b"}
    assert clients["project-a"].search.call_count == 2
    assert clients["project-b"].search.call_count == 1


def test_agent_memory_setup_cli_prints_current_wrangler_command() -> None:
    config = MagicMock()
    config.memory.agent_memory_namespace = "voly-prod"
    config.memory.agent_memory_profile = "project-a"
    config.memory.agent_memory_profile_mode = "explicit"

    result = CliRunner().invoke(memory, ["agent-memory-setup"], obj={"config": config})

    assert result.exit_code == 0
    assert "npx wrangler agent-memory namespace create voly-prod" in result.output
    assert "VOLY profile: project-a" in result.output


def test_agent_memory_setup_cli_derives_project_profile(tmp_path: Path) -> None:
    config = MagicMock()
    config.default_cwd = ""
    config.memory.agent_memory_namespace = "voly-prod"
    config.memory.agent_memory_profile = "default"
    config.memory.agent_memory_profile_mode = "project"

    result = CliRunner().invoke(
        memory,
        ["agent-memory-setup", "--cwd", str(tmp_path / "My Project")],
        obj={"config": config},
    )

    assert result.exit_code == 0
    assert "VOLY profile: project-my-project-" in result.output
    assert "unresolved" not in result.output


def test_agent_memory_ingest_and_summary_cli(tmp_path) -> None:
    config = MagicMock()
    config.memory.backend = "agent_memory"
    config.memory.agent_memory_account_id = "acc"
    config.memory.agent_memory_namespace = "voly-prod"
    config.memory.agent_memory_profile = "project-a"
    config.memory.agent_memory_profile_mode = "explicit"
    client = MagicMock()
    client.get_summary.return_value = "## Summary"
    conversation = tmp_path / "conversation.json"
    conversation.write_text(
        json.dumps(
            {
                "sessionId": "run-1",
                "messages": [{"role": "user", "content": "Use FastAPI"}],
            }
        ),
        encoding="utf-8",
    )

    with patch("voly.memory.client.create_remote_memory_client", return_value=client):
        ingested = CliRunner().invoke(memory, ["ingest", str(conversation)], obj={"config": config})
        summarized = CliRunner().invoke(
            memory, ["summary", "--session-id", "run-1"], obj={"config": config}
        )

    assert ingested.exit_code == 0
    client.ingest.assert_called_once_with(
        [{"role": "user", "content": "Use FastAPI"}], session_id="run-1"
    )
    assert summarized.exit_code == 0
    assert "## Summary" in summarized.output
