from __future__ import annotations


def test_inference_import_without_dspy_extra() -> None:
    import codeops.inference

    assert codeops.inference is not None


def test_default_config_keeps_dspy_disabled() -> None:
    from codeops.config import CodeOpsConfig

    cfg = CodeOpsConfig()

    assert cfg.dspy.enabled is False
    assert cfg.dspy.mode == "shadow"


def test_inference_manager_falls_back_to_classic_when_dspy_missing() -> None:
    from codeops.config import CodeOpsConfig
    from codeops.inference import InferenceManager
    from codeops.router import RouteDecision

    class FakeGateway:
        def chat(self, **kwargs):  # type: ignore[no-untyped-def]
            return {
                "content": "classic response",
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "model": kwargs["model"],
            }

    cfg = CodeOpsConfig()
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
