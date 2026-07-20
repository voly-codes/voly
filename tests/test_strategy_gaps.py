"""Close strategy gaps: model_provider match, health filter, routing policy, intel auto."""

from __future__ import annotations


def test_model_provider_match_does_not_require_file_tools(tmp_path):
    import os

    from voly.capability.matcher import ExecutorMatcher, MatchRequest
    from voly.capability.registry import CapabilityRegistry

    seeds = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds)
    matcher = ExecutorMatcher(reg)
    result = matcher.find_executors(
        MatchRequest(
            dimension="architecture",
            kind="model_provider",
            available_executors=None,
            project_features=["python"],
            requires_file_tools=False,
        )
    )
    assert result.recommended is not None
    assert result.recommended.kind == "model_provider"
    assert result.recommended.provider
    assert result.recommended.model


def test_routing_policy_budget_prefers_cheaper(tmp_path):
    import os

    from voly.capability.matcher import ExecutorMatcher, MatchRequest
    from voly.capability.registry import CapabilityRegistry
    from voly.capability.scorer import ROUTING_POLICY_WEIGHTS

    assert abs(sum(ROUTING_POLICY_WEIGHTS["budget_first"].values()) - 1.0) < 1e-9
    assert abs(sum(ROUTING_POLICY_WEIGHTS["quality_first"].values()) - 1.0) < 1e-9

    seeds = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds)
    matcher = ExecutorMatcher(reg)
    balanced = matcher.find_executors(
        MatchRequest(
            dimension="architecture",
            kind="model_provider",
            available_executors=["anthropic-sonnet", "opencode-zen"],
            project_features=None,
            requires_file_tools=False,
            routing_policy="balanced",
        )
    )
    budget = matcher.find_executors(
        MatchRequest(
            dimension="architecture",
            kind="model_provider",
            available_executors=["anthropic-sonnet", "opencode-zen"],
            project_features=None,
            requires_file_tools=False,
            routing_policy="budget_first",
        )
    )
    assert budget.recommended is not None
    assert balanced.recommended is not None
    # budget_first must not prefer the expensive anthropic seed over free zen.
    assert budget.recommended.id == "opencode-zen"
    # quality_first should prefer the higher capability anthropic seed.
    quality = matcher.find_executors(
        MatchRequest(
            dimension="architecture",
            kind="model_provider",
            available_executors=["anthropic-sonnet", "opencode-zen"],
            project_features=None,
            requires_file_tools=False,
            routing_policy="quality_first",
        )
    )
    assert quality.recommended is not None
    assert quality.recommended.id == "anthropic-sonnet"

def test_lead_filters_unhealthy_providers(tmp_path, monkeypatch):
    import os

    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator
    from voly.capability.matcher import ExecutorMatcher
    from voly.capability.registry import CapabilityRegistry

    seeds = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds)
    matcher = ExecutorMatcher(reg)

    class _Checker:
        def check(self, provider: str):
            class S:
                healthy = provider != "anthropic"
                reason = "test"

            return S()

    class _Gw:
        def chat(self, *a, **k):
            raise RuntimeError("lead should stay deterministic")

    lead = LeadOrchestrator(
        gateway=_Gw(),
        skill_matcher=None,
        checker=_Checker(),
        lead_mode="deterministic",
        matcher=matcher,
        project_context={"task_features": ["python"], "routing_policy": "balanced"},
    )
    assigns = lead.assign(
        "design architecture",
        [Subtask("Design architecture", "architect")],
    )
    assert len(assigns) == 1
    # anthropic filtered → not anthropic provider for chat role
    assert assigns[0].provider != "anthropic"
    assert assigns[0].model


def test_extract_github_url_and_auto_intel(tmp_path):
    from voly.pipeline.stages_intelligence import extract_github_url

    assert (
        extract_github_url(
            "port UI from https://github.com/owner/repo.git please"
        )
        == "https://github.com/owner/repo"
    )
    assert extract_github_url("no url here") == ""


def test_local_cwd_features_python(tmp_path):
    from voly.pipeline.stages_intelligence import _local_cwd_features

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    feats = _local_cwd_features(str(tmp_path))
    assert "python" in [f.lower() for f in feats]


def test_model_provider_seeds_exist():
    import os

    seeds = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    for name in (
        "anthropic-sonnet.yaml",
        "deepseek-chat.yaml",
        "opencode-zen.yaml",
        "workers-ai-scout.yaml",
    ):
        assert os.path.exists(os.path.join(seeds, name)), name
