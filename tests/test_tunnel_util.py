"""Tests for tunnel utilities."""

import pytest

from voly.tunnel_util import parse_tunnel_url, ensure_pipeline_token


def test_parse_tunnel_url() -> None:
    output = "INF Some log\n https://abc-def-123.trycloudflare.com  \n"
    assert parse_tunnel_url(output) == "https://abc-def-123.trycloudflare.com"


def test_ensure_pipeline_token_generates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_RUNNER_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("# empty\n")
    token = ensure_pipeline_token(env_path)
    assert len(token) > 20
    assert "PIPELINE_RUNNER_TOKEN=" in env_path.read_text()
