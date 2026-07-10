"""CF Secrets Store client + /api/providers/keys routes (PR4, BYOK)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voly.ai_gateway.cf_secrets import CFSecretsClient, CFSecretsError


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(calls: list, responses: dict):
    """responses: {(method, path_prefix): payload}"""

    def fake(req, timeout=0):
        path = req.full_url.replace("https://api.cloudflare.com/client/v4", "")
        calls.append({
            "method": req.get_method(),
            "path": path,
            "body": json.loads(req.data.decode()) if req.data else None,
            "headers": dict(req.header_items()),
        })
        for (method, prefix), payload in responses.items():
            if req.get_method() == method and path.startswith(prefix):
                return _FakeResp(payload)
        raise AssertionError(f"unexpected CF call: {req.get_method()} {path}")

    return fake


def _patch(monkeypatch, calls, responses):
    import voly.ai_gateway.cf_secrets as mod
    monkeypatch.setattr(mod.urllib.request, "urlopen", _fake_urlopen(calls, responses))


def test_create_provider_key_naming_and_scope(monkeypatch) -> None:
    calls: list = []
    _patch(monkeypatch, calls, {
        ("GET", "/accounts/acct/secrets_store/stores"): {
            "success": True, "result": [{"id": "store1"}],
        },
        ("POST", "/accounts/acct/secrets_store/stores/store1/secrets"): {
            "success": True, "result": [{"id": "sec1"}],
        },
    })
    client = CFSecretsClient(account_id="acct", api_token="tok", gateway_id="gw1")
    name = client.create_provider_key("anthropic", "sk-value", alias="default")
    assert name == "gw1_anthropic_default"
    post = [c for c in calls if c["method"] == "POST"][0]
    assert post["body"] == [{
        "name": "gw1_anthropic_default",
        "value": "sk-value",
        "scopes": ["ai_gateway"],
        "comment": "VOLY BYOK key for anthropic",
    }]
    assert post["headers"].get("Authorization") == "Bearer tok"


def test_list_provider_keys_filters_by_gateway(monkeypatch) -> None:
    calls: list = []
    _patch(monkeypatch, calls, {
        ("GET", "/accounts/acct/secrets_store/stores/store1/secrets"): {
            "success": True,
            "result": [
                {"id": "s1", "name": "gw1_anthropic_default"},
                {"id": "s2", "name": "gw1_google-ai-studio_default"},
                {"id": "s3", "name": "other-gw_openai_default"},
                {"id": "s4", "name": "unrelated"},
            ],
        },
        ("GET", "/accounts/acct/secrets_store/stores"): {
            "success": True, "result": [{"id": "store1"}],
        },
    })
    client = CFSecretsClient(account_id="acct", api_token="tok", gateway_id="gw1")
    keys = client.list_provider_keys()
    assert [(k["provider"], k["alias"]) for k in keys] == [
        ("anthropic", "default"),
        ("google-ai-studio", "default"),
    ]


def test_delete_provider_key(monkeypatch) -> None:
    calls: list = []
    _patch(monkeypatch, calls, {
        ("GET", "/accounts/acct/secrets_store/stores/store1/secrets"): {
            "success": True, "result": [{"id": "s1", "name": "gw1_deepseek_default"}],
        },
        ("GET", "/accounts/acct/secrets_store/stores"): {
            "success": True, "result": [{"id": "store1"}],
        },
        ("DELETE", "/accounts/acct/secrets_store/stores/store1/secrets/s1"): {
            "success": True, "result": {},
        },
    })
    client = CFSecretsClient(account_id="acct", api_token="tok", gateway_id="gw1")
    assert client.delete_provider_key("deepseek") is True
    assert client.delete_provider_key("openai") is False


def test_no_store_raises_with_hint(monkeypatch) -> None:
    calls: list = []
    _patch(monkeypatch, calls, {
        ("GET", "/accounts/acct/secrets_store/stores"): {"success": True, "result": []},
    })
    client = CFSecretsClient(account_id="acct", api_token="tok")
    with pytest.raises(CFSecretsError, match="no Secrets Store"):
        client.store_id()


# ── Web routes ────────────────────────────────────────────────────────────────

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from voly.config import VOLYConfig  # noqa: E402
from voly.web.server import create_app  # noqa: E402


@pytest.fixture()
def web_client(tmp_path: Path) -> TestClient:
    d = tmp_path / "events"
    d.mkdir()
    app = create_app(config=VOLYConfig(), events_dir=d)
    return TestClient(app)


def test_post_key_requires_cf_creds(web_client, monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    r = web_client.post("/api/providers/keys", json={"provider": "anthropic", "key": "sk-x"})
    assert r.status_code == 400
    assert "CLOUDFLARE" in r.json()["detail"]


def test_post_key_rejects_non_byok_provider(web_client, monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    r = web_client.post("/api/providers/keys", json={"provider": "mimo", "key": "sk-x"})
    assert r.status_code == 400
    assert "not BYOK-eligible" in r.json()["detail"]


def test_post_and_list_keys_roundtrip(web_client, monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_AI_GATEWAY_ID", "gw1")

    calls: list = []
    _patch(monkeypatch, calls, {
        ("GET", "/accounts/acct/secrets_store/stores/"): {
            "success": True, "result": [{"id": "s1", "name": "gw1_anthropic_default"}],
        },
        ("GET", "/accounts/acct/secrets_store/stores"): {
            "success": True, "result": [{"id": "store1"}],
        },
        ("POST", "/accounts/acct/secrets_store/stores/store1/secrets"): {
            "success": True, "result": [{"id": "s1"}],
        },
    })

    r = web_client.post("/api/providers/keys", json={"provider": "anthropic", "key": "sk-secret"})
    assert r.status_code == 200
    assert r.json()["name"] == "gw1_anthropic_default"
    # the key value never appears in the response
    assert "sk-secret" not in r.text

    r2 = web_client.get("/api/providers/keys")
    assert r2.status_code == 200
    data = r2.json()
    assert data["configured"] is True
    assert data["keys"][0]["provider"] == "anthropic"
    assert "sk-secret" not in r2.text
