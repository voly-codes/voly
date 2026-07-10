"""Web UI JWT auth — config, tokens, middleware, login route."""

from __future__ import annotations

from pathlib import Path

import pytest

from voly.config import AuthConfig, VOLYConfig, load_config
from voly.web.auth.jwt import (
    ExpiredTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
    JWTAuth,
    authenticate_user,
    jwt_auth_from_config,
)

pytest.importorskip("fastapi")
pytest.importorskip("jwt")


def test_authenticate_user_ok_and_bad() -> None:
    users = {"admin": "s3cret"}
    assert authenticate_user("admin", "s3cret", users) == "admin"
    with pytest.raises(InvalidCredentialsError):
        authenticate_user("admin", "wrong", users)
    with pytest.raises(InvalidCredentialsError):
        authenticate_user("nobody", "s3cret", users)


def test_jwt_roundtrip() -> None:
    auth = JWTAuth("test-secret-key", expire_minutes=30)
    token = auth.create_access_token("alice")
    payload = auth.decode_token(token)
    assert payload.sub == "alice"
    assert payload.token_type == "access"


def test_jwt_rejects_tampered_and_empty_secret() -> None:
    with pytest.raises(ValueError):
        JWTAuth("")
    auth = JWTAuth("secret-a")
    token = auth.create_access_token("bob")
    with pytest.raises(InvalidTokenError):
        JWTAuth("secret-b").decode_token(token)


def test_auth_config_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOLY_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("VOLY_JWT_SECRET", raising=False)
    monkeypatch.delenv("VOLY_AUTH_USERS", raising=False)
    cfg_path = tmp_path / "voly.yaml"
    cfg_path.write_text(
        """
auth:
  enabled: true
  jwt_secret: "yaml-secret"
  users:
    alice: wonderland
  cors_origins:
    - "http://localhost:7788"
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.auth.enabled is True
    assert cfg.auth.jwt_secret == "yaml-secret"
    assert cfg.auth.users == {"alice": "wonderland"}
    assert cfg.auth.cors_origins == ["http://localhost:7788"]


def test_auth_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "voly.yaml"
    cfg_path.write_text("auth:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("VOLY_AUTH_ENABLED", "true")
    monkeypatch.setenv("VOLY_JWT_SECRET", "env-secret")
    monkeypatch.setenv("VOLY_AUTH_USERS", "admin:pw,dev:x")
    cfg = load_config(cfg_path)
    assert cfg.auth.enabled is True
    assert cfg.auth.jwt_secret == "env-secret"
    assert cfg.auth.users == {"admin": "pw", "dev": "x"}


def test_auth_provider_registry_lists_local_and_clerk() -> None:
    from voly.web.auth.providers import get_provider, list_provider_names
    from voly.config import AuthConfig

    names = list_provider_names()
    assert "local" in names
    assert "clerk" in names
    local = get_provider(AuthConfig(enabled=True, provider="local", jwt_secret="x" * 32))
    assert local is not None and local.name == "local"
    assert local.supports_password_login() is True
    clerk = get_provider(
        AuthConfig(
            enabled=True,
            provider="clerk",
            clerk_issuer="https://demo.clerk.accounts.dev",
        )
    )
    assert clerk is not None and clerk.name == "clerk"
    assert clerk.supports_password_login() is False


def test_auth_status_clerk_mode(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from voly.web.server import create_app

    cfg = VOLYConfig(
        auth=AuthConfig(
            enabled=True,
            provider="clerk",
            clerk_publishable_key="pk_test_demo",
            clerk_issuer="https://demo.clerk.accounts.dev",
            clerk_jwks_url="https://demo.clerk.accounts.dev/.well-known/jwks.json",
            cors_origins=["http://localhost:7788"],
        )
    )
    app = create_app(events_dir=tmp_path, config=cfg)
    client = TestClient(app)
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["provider"] == "clerk"
    assert body["mode"] == "clerk"
    assert body["clerk"]["publishable_key"] == "pk_test_demo"
    # Local login rejected when Clerk is on
    bad = client.post("/api/auth/login", json={"username": "a", "password": "b"})
    assert bad.status_code == 400


def test_auth_config_clerk_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "voly.yaml"
    cfg_path.write_text("auth:\n  enabled: true\n  provider: clerk\n", encoding="utf-8")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_env")
    monkeypatch.setenv("CLERK_ISSUER", "https://env.clerk.accounts.dev")
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    cfg = load_config(cfg_path)
    assert cfg.auth.provider == "clerk"
    assert cfg.auth.clerk_publishable_key == "pk_env"
    assert cfg.auth.clerk_issuer == "https://env.clerk.accounts.dev"
    assert cfg.auth.clerk_jwks_url.endswith("/.well-known/jwks.json")
    assert cfg.auth.is_enforced() is True


def test_create_app_open_mode_allows_status(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from voly.web.server import create_app

    app = create_app(events_dir=tmp_path, config=VOLYConfig())
    client = TestClient(app)
    r = client.get("/api/status")
    assert r.status_code == 200
    r2 = client.get("/api/auth/status")
    assert r2.status_code == 200
    assert r2.json()["enabled"] is False


def test_create_app_auth_accepts_query_token_only_on_stream_path(tmp_path: Path) -> None:
    """EventSource cannot set headers, so /api/tasks/stream alone accepts a
    query token — every other GET route must still use the Authorization
    header, and a leaked stream ticket can't be replayed elsewhere."""
    from fastapi.testclient import TestClient
    from voly.web.server import create_app

    cfg = VOLYConfig(
        auth=AuthConfig(
            enabled=True,
            jwt_secret="unit-test-secret-key-32chars!!",
            users={"admin": "pass"},
            cors_origins=["http://localhost:7788"],
        )
    )
    app = create_app(events_dir=tmp_path, config=cfg)
    client = TestClient(app)
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
    token = ok.json()["access_token"]

    denied = client.get("/api/tasks")
    assert denied.status_code == 401
    allowed = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200

    # A regular (or leaked) access token in the query string no longer works
    # on a non-stream route — only the Authorization header does.
    not_allowed = client.get(f"/api/tasks?access_token={token}")
    assert not_allowed.status_code == 401

    # The stream endpoint accepts a dedicated short-lived ticket minted via
    # POST /api/tasks/stream-token (requires a normal bearer header).
    ticket_res = client.post(
        "/api/tasks/stream-token", headers={"Authorization": f"Bearer {token}"}
    )
    assert ticket_res.status_code == 200
    stream_token = ticket_res.json()["stream_token"]
    assert stream_token and stream_token != token

    # /api/tasks/stream is an infinite generator — use client.stream() to
    # check just the response status without waiting for it to finish.
    with client.stream("GET", f"/api/tasks/stream?access_token={stream_token}") as resp:
        assert resp.status_code == 200

    # A stream ticket must not work as a general bearer token elsewhere.
    stream_denied = client.get(
        "/api/tasks", headers={"Authorization": f"Bearer {stream_token}"}
    )
    assert stream_denied.status_code == 401

    # Minting a ticket without auth is rejected like any other protected route.
    no_auth_ticket = client.post("/api/tasks/stream-token")
    assert no_auth_ticket.status_code == 401


def test_create_app_auth_blocks_and_login(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from voly.web.server import create_app

    cfg = VOLYConfig(
        auth=AuthConfig(
            enabled=True,
            jwt_secret="unit-test-secret",
            users={"admin": "pass"},
            cors_origins=["http://localhost:7788"],
        )
    )
    app = create_app(events_dir=tmp_path, config=cfg)
    client = TestClient(app)

    # Protected without token
    denied = client.get("/api/tasks")
    assert denied.status_code == 401
    assert "Missing" in denied.json()["detail"]

    # Public status still open
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/auth/status").json()["enabled"] is True

    # Bad login
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401

    # Good login → bearer works
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    allowed = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200


def test_auth_enabled_star_cors_restricted() -> None:
    from voly.web.server import _resolve_cors_origins

    cfg = VOLYConfig(auth=AuthConfig(enabled=True, jwt_secret="s", cors_origins=["*"]))
    origins = _resolve_cors_origins(cfg)
    assert "*" not in origins
    assert "http://localhost:7788" in origins


def test_jwt_auth_from_config() -> None:
    cfg = AuthConfig(enabled=True, jwt_secret="cfg-secret", access_token_expire_minutes=15)
    jwt_auth = jwt_auth_from_config(cfg)
    token = jwt_auth.create_access_token("u1")
    assert jwt_auth.decode_token(token).sub == "u1"
