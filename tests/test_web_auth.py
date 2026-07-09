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
