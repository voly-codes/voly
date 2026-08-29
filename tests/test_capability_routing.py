"""voly.capability.routing.capability_route — the shared evidence-based
resolution helper voly.sdk.agent.Agent and the default (non-injected)
voly.plan.runner.PlanRunner chat/executor paths both consult when a caller
left model/tier/executor unset. Generalizes the pattern
voly.decisions._build_business_executor and voly.a2a.lead.LeadOrchestrator
each implement separately, without a third copy of the ExecutorMatcher
wiring.
"""

from __future__ import annotations

from voly.capability.routing import capability_route
from voly.config import VOLYConfig


def _config_with_capability(tmp_path, *, enabled: bool = True) -> VOLYConfig:
    config = VOLYConfig()
    config.capability.enabled = enabled
    config.capability.profiles_dir = str(tmp_path / "profiles")
    return config


def test_disabled_by_default_returns_none(tmp_path) -> None:
    config = _config_with_capability(tmp_path, enabled=False)
    assert capability_route("developer", mode="chat", config=config) is None
    assert capability_route("developer", mode="executor", config=config) is None


def test_empty_role_returns_none(tmp_path) -> None:
    config = _config_with_capability(tmp_path)
    assert capability_route("", mode="chat", config=config) is None


def test_missing_capability_config_returns_none() -> None:
    """A bare object with no `.capability` attribute at all (e.g. a stub in
    a unit test) must not raise — capability routing is always best-effort."""

    class NoCapabilityConfig:
        pass

    assert capability_route("developer", mode="chat", config=NoCapabilityConfig()) is None


def test_executor_mode_recommends_a_real_seed_profile(tmp_path) -> None:
    """CapabilityRegistry(profiles_dir) with no seeds_dir override already
    defaults to the bundled voly/capability/seeds/ profiles — no fixture
    profiles need to be written for this test."""
    config = _config_with_capability(tmp_path)
    hint = capability_route(
        "developer", mode="executor", config=config,
        available_executors=["claude-code", "cursor", "wrangler"],
    )
    assert hint is not None
    executor_id, model, provider = hint
    assert executor_id in ("claude-code", "cursor", "wrangler")
    assert model == "" and provider == ""


def test_chat_mode_recommends_a_model_and_provider(tmp_path) -> None:
    config = _config_with_capability(tmp_path)
    hint = capability_route("developer", mode="chat", config=config)
    assert hint is not None
    executor_id, model, provider = hint
    assert executor_id == ""
    assert model and provider


def test_matcher_exception_falls_back_to_none(tmp_path, monkeypatch) -> None:
    def boom(self, req):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr("voly.capability.matcher.ExecutorMatcher.find_executors", boom)
    config = _config_with_capability(tmp_path)
    assert capability_route("developer", mode="chat", config=config) is None
