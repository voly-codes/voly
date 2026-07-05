"""Tests for spend client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from voly.spend.client import SpendClient, create_spend_client, resolve_spend_url


def test_resolve_spend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_WORKER_SPEND_URL", "https://spend.example.com")
    assert resolve_spend_url("") == "https://spend.example.com"


def test_spend_client_record() -> None:
    client = SpendClient("https://spend.example.com")
    captured: dict = {}

    def fake_urlopen(req, timeout=10):
        captured["method"] = req.method
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = b'{"ok": true}'
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        client.record("developer", 0.05, task_id="t1", model="gpt-4o")

    body = json.loads(captured["data"].decode())
    assert body["agent"] == "developer"
    assert captured["method"] == "POST"


def test_create_spend_client_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_SPEND_URL", raising=False)
    assert create_spend_client() is None
