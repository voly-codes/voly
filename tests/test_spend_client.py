"""Tests for spend client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from voly.spend.client import SpendClient, create_spend_client, resolve_spend_url, resolve_spend_token


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


def _capture_record_body(client: SpendClient, **kwargs) -> dict:
    captured: dict = {}

    def fake_urlopen(req, timeout=10):
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = b'{"ok": true, "duplicate": false}'
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        client.record("developer", 0.05, **kwargs)
    return json.loads(captured["data"].decode())


def test_record_v2_body_fields() -> None:
    client = SpendClient("https://spend.example.com")
    body = _capture_record_body(
        client, task_id="t1", model="m", provider="p",
        product="example-product", model_version="2026-10", tokens_in=10, tokens_out=5,
    )
    assert body["schema_version"] == 2
    assert body["product"] == "example-product"
    assert body["model_version"] == "2026-10"
    assert (body["tokens_in"], body["tokens_out"]) == (10, 5)
    assert body["event_id"]


def test_record_event_id_is_new_per_call_and_reusable_on_retry() -> None:
    client = SpendClient("https://spend.example.com")
    first = _capture_record_body(client)
    second = _capture_record_body(client)
    assert first["event_id"] != second["event_id"]

    retried = _capture_record_body(client, event_id=first["event_id"])
    assert retried["event_id"] == first["event_id"]


def test_record_rejects_too_long_product() -> None:
    client = SpendClient("https://spend.example.com")
    with pytest.raises(ValueError):
        client.record("developer", 0.05, product="x" * 65)


def test_record_rejects_negative_tokens() -> None:
    client = SpendClient("https://spend.example.com")
    with pytest.raises(ValueError):
        client.record("developer", 0.05, tokens_in=-1)


def test_resolve_spend_token_uses_worker_secret_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_SPEND_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "account-token-not-for-worker")
    assert resolve_spend_token() == ""

    monkeypatch.setenv("CF_WORKER_SPEND_TOKEN", "worker-api-token")
    assert resolve_spend_token() == "worker-api-token"


def test_create_spend_client_attaches_spend_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_WORKER_SPEND_URL", "https://spend.example.com")
    monkeypatch.setenv("CF_WORKER_SPEND_TOKEN", "worker-api-token")
    client = create_spend_client()
    assert client is not None
    assert client.token == "worker-api-token"