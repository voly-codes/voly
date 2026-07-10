"""`voly setup` hosted catalog opt-in (PR5, docs/proposals/byok-cf-secrets.md)."""

from __future__ import annotations

from voly.cli.commands.lifecycle import (
    OFFICIAL_CATALOG_URL,
    OFFICIAL_MARKETPLACE_URL,
    _offer_official_catalog,
)


def test_offer_writes_urls_on_confirm(tmp_path, monkeypatch) -> None:
    import voly.cli.commands.lifecycle as mod

    monkeypatch.delenv("CF_WORKER_CATALOG_URL", raising=False)
    monkeypatch.delenv("CF_WORKER_MARKETPLACE_URL", raising=False)
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(mod.click, "confirm", lambda *a, **k: True)

    env = tmp_path / ".env"
    env.write_text("EXISTING=1", encoding="utf-8")
    assert _offer_official_catalog(env) is True
    text = env.read_text(encoding="utf-8")
    assert f"CF_WORKER_CATALOG_URL={OFFICIAL_CATALOG_URL}" in text
    assert f"CF_WORKER_MARKETPLACE_URL={OFFICIAL_MARKETPLACE_URL}" in text
    assert text.startswith("EXISTING=1\n")  # existing content preserved


def test_offer_skips_without_tty(tmp_path, monkeypatch) -> None:
    import voly.cli.commands.lifecycle as mod

    monkeypatch.delenv("CF_WORKER_CATALOG_URL", raising=False)
    monkeypatch.delenv("CF_WORKER_MARKETPLACE_URL", raising=False)
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)

    env = tmp_path / ".env"
    assert _offer_official_catalog(env) is False
    assert not env.exists()


def test_offer_skips_when_already_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CF_WORKER_CATALOG_URL", "https://own.example")
    monkeypatch.setenv("CF_WORKER_MARKETPLACE_URL", "https://own.example")
    env = tmp_path / ".env"
    assert _offer_official_catalog(env) is False
    assert not env.exists()


def test_offer_declined_writes_nothing(tmp_path, monkeypatch) -> None:
    import voly.cli.commands.lifecycle as mod

    monkeypatch.delenv("CF_WORKER_CATALOG_URL", raising=False)
    monkeypatch.delenv("CF_WORKER_MARKETPLACE_URL", raising=False)
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(mod.click, "confirm", lambda *a, **k: False)

    env = tmp_path / ".env"
    assert _offer_official_catalog(env) is False
    assert not env.exists()


def test_env_example_carries_official_urls() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath(".env.example").read_text(encoding="utf-8")
    assert OFFICIAL_CATALOG_URL in text
    assert OFFICIAL_MARKETPLACE_URL in text
