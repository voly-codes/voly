"""Tests for catalog routing and supervisor."""

from voly.catalog.routing import get_mission_plan, match_task, resolve_model
from voly.catalog.zen_sync import parse_zen_models_payload, _builtin_fallback_catalog


def test_parse_zen_models_payload():
    data = {"data": [{"id": "claude-opus-4-8", "name": "Claude Opus 4.8"}]}
    models = parse_zen_models_payload(data)
    assert len(models) == 1
    assert models[0].id == "claude-opus-4-8"
    assert models[0].tier == "premium"


def test_match_task_review():
    ex, model = match_task("Full parity review checklist P0 gaps")
    assert ex == "zen"
    assert "free" in model or model.startswith("deepseek")


def test_plane_issues_plan_has_eight_steps():
    steps = get_mission_plan("plane-issues")
    assert len(steps) == 8
    assert steps[-1].readonly is True
    assert steps[-1].executor == "zen"


def test_resolve_model_fallback():
    model = resolve_model("zen", "nonexistent-model-xyz", prefer_free=True)
    assert model in ("deepseek-v4-flash-free", "mimo-v2.5-free", "nemotron-3-ultra-free")


def test_builtin_fallback_non_empty():
    assert len(_builtin_fallback_catalog()) >= 10
