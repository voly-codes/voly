from __future__ import annotations


def test_inference_import_without_dspy_extra() -> None:
    import voly.inference

    assert voly.inference is not None


def test_default_config_keeps_dspy_disabled() -> None:
    from voly.config import VOLYConfig

    cfg = VOLYConfig()

    assert cfg.dspy.enabled is False
    assert cfg.dspy.mode == "shadow"


def test_inference_manager_falls_back_to_classic_when_dspy_missing() -> None:
    from voly.config import VOLYConfig
    from voly.inference import InferenceManager
    from voly.router import RouteDecision

    class FakeGateway:
        def chat(self, **kwargs):  # type: ignore[no-untyped-def]
            return {
                "content": "classic response",
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "model": kwargs["model"],
            }

    cfg = VOLYConfig()
    route = RouteDecision(agent="documenter", model="gpt-4o-mini", provider="openai")
    manager = InferenceManager(cfg, FakeGateway(), dspy_runner=None)

    outcome = manager.run(
        task="write docs",
        messages=[{"role": "user", "content": "write docs"}],
        route=route,
        model="gpt-4o-mini",
    )

    assert outcome.runtime == "classic"
    assert outcome.used_dspy is False
    assert outcome.response["content"] == "classic response"


def test_repo_intelligence_stage_skipped_without_url() -> None:
    from voly.pipeline.types import PipelineStage

    assert PipelineStage.REPO_INTELLIGENCE is not None
    assert PipelineStage.REPO_INTELLIGENCE.value == "repo_intelligence"


def test_lead_orchestrator_capability_aware() -> None:
    from voly.a2a.lead import LeadOrchestrator

    class _Gw:
        def chat(self, **kwargs):  # type: ignore[no-untyped-def]
            return {"content": ""}

    lo = LeadOrchestrator(gateway=_Gw(), lead_mode="deterministic")
    assert lo is not None
    assert lo.matcher is None
