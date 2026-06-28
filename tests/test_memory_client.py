"""Tests for semantic memory client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from codeops.memory.client import (
    MemoryClient,
    create_memory_client,
    resolve_memory_url,
)


def test_resolve_memory_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_MEMORY_URL", raising=False)
    assert resolve_memory_url("") == ""

    monkeypatch.setenv("CF_WORKER_MEMORY_URL", "https://mem.example.com")
    assert resolve_memory_url("") == "https://mem.example.com"


def test_memory_client_search() -> None:
    client = MemoryClient("https://mem.example.com")

    def fake_urlopen(req, timeout=30):
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"results": [{"id": "1", "title": "Auth", "content": "OAuth2", "category": "decision"}]}
        ).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        results = client.search("auth", limit=3)

    assert len(results) == 1
    assert results[0]["title"] == "Auth"


def test_create_memory_client_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_MEMORY_URL", raising=False)
    assert create_memory_client() is None
