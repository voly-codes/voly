"""Priority: pipeline stage helpers + A2A dispatch decision (no live LLM)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from voly.config import A2AConfig, VOLYConfig
from voly.pipeline.stages import _PipelineStageMixin


class _FakePipeline(_PipelineStageMixin):
    def __init__(self, config: VOLYConfig | None = None) -> None:
        self.config = config or VOLYConfig(a2a=A2AConfig(enabled=True, auto_dispatch=True, min_flags_for_dispatch=2))
        self._fired: list = []

    def _fire(self, stage, **kwargs):  # noqa: ANN001
        self._fired.append((stage, kwargs))


def test_should_dispatch_a2a_by_flags() -> None:
    p = _FakePipeline()
    analysis = SimpleNamespace(
        requires_code_gen=True,
        requires_review=True,
        requires_testing=False,
        requires_deployment=False,
        complexity="medium",
    )
    assert p._should_dispatch_a2a(analysis) is True


def test_should_not_dispatch_single_flag() -> None:
    p = _FakePipeline()
    analysis = SimpleNamespace(
        requires_code_gen=True,
        requires_review=False,
        requires_testing=False,
        requires_deployment=False,
        complexity="low",
    )
    assert p._should_dispatch_a2a(analysis) is False


def test_should_dispatch_high_complexity() -> None:
    p = _FakePipeline()
    analysis = SimpleNamespace(
        requires_code_gen=False,
        requires_review=False,
        requires_testing=False,
        requires_deployment=False,
        complexity="high",
    )
    assert p._should_dispatch_a2a(analysis) is True


def test_should_not_dispatch_when_disabled() -> None:
    p = _FakePipeline(VOLYConfig(a2a=A2AConfig(enabled=False, auto_dispatch=True)))
    analysis = SimpleNamespace(
        requires_code_gen=True,
        requires_review=True,
        requires_testing=True,
        requires_deployment=True,
        complexity="high",
    )
    assert p._should_dispatch_a2a(analysis) is False


def test_should_not_dispatch_nested() -> None:
    p = _FakePipeline()
    analysis = SimpleNamespace(
        requires_code_gen=True,
        requires_review=True,
        requires_testing=True,
        requires_deployment=True,
        complexity="high",
    )
    assert p._should_dispatch_a2a(analysis, nested=True) is False


def test_stage_a2a_auto_nested_returns_none() -> None:
    p = _FakePipeline()
    out = p._stage_a2a_auto(
        "task",
        SimpleNamespace(requires_code_gen=True, requires_review=True, requires_testing=True, requires_deployment=True, complexity="high"),
        None,
        0.0,
        "tid",
        nested=True,
    )
    assert out is None


def test_budget_helpers_still_importable() -> None:
    # sanity: stages mixin coexists with pipeline types
    from voly.pipeline.types import PipelineStage

    assert PipelineStage.DONE
    assert hasattr(_FakePipeline(), "_should_dispatch_a2a")
