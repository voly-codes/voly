"""Tests for env-configurable Web UI registry lists."""

from __future__ import annotations

from voly.web.routes.registry import registry_agents, registry_models


def test_registry_agents_prefers_env_roles(monkeypatch) -> None:
    monkeypatch.setenv("VOLY_ROLES", "architect, developer,architect, tester ")

    assert registry_agents() == ["architect", "developer", "tester"]


def test_registry_agents_allows_explicit_empty_list(monkeypatch) -> None:
    monkeypatch.setenv("VOLY_ROLES", "")

    assert registry_agents() == []


def test_registry_models_prefers_executor_specific_env(monkeypatch) -> None:
    monkeypatch.setenv("VOLY_MODELS", "generic-model")
    monkeypatch.setenv("VOLY_MODELS_CLOUDFLARE_DYNAMIC", "dynamic/first, dynamic/second")

    assert registry_models("cloudflare-dynamic") == ["dynamic/first", "dynamic/second"]


def test_registry_models_uses_generic_env_fallback(monkeypatch) -> None:
    monkeypatch.setenv("VOLY_MODELS", "model-a,model-b,model-a")

    assert registry_models("custom-executor") == ["model-a", "model-b"]


def test_registry_models_uses_dynamic_catalog_without_env(monkeypatch) -> None:
    monkeypatch.delenv("VOLY_MODELS", raising=False)
    monkeypatch.delenv("VOLY_MODELS_PIPELINE", raising=False)

    models = registry_models("pipeline")

    assert "claude-sonnet-4-6" in models
