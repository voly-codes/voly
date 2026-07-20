"""Pipeline + registry smoke tests (Phase 9)."""

from __future__ import annotations

import os

import pytest


def test_pipeline_stage_order():
    from voly.pipeline.types import PipelineStage

    stages = [s.value for s in PipelineStage]
    init_idx = stages.index("init")
    repo_intel_idx = stages.index("repo_intelligence")
    a2a_idx = stages.index("a2a_discover")
    assert init_idx < repo_intel_idx < a2a_idx


def test_role_registry_completeness():
    from voly.a2a.roles import ROLE_REGISTRY

    expected = {
        "architect",
        "developer",
        "tester",
        "reviewer",
        "devops",
        "security",
        "bugfixer",
        "ui_architect",
        "visual_reviewer",
        "browser_tester",
        "ux_reviewer",
    }
    assert expected.issubset(set(ROLE_REGISTRY.keys()))


def test_capability_registry_all_seeds_loadable(tmp_path):
    from voly.capability.registry import CapabilityRegistry

    seeds = os.path.join(os.path.dirname(__file__), "..", "voly", "capability", "seeds")
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds)
    ids = reg.list_ids()
    assert len(ids) >= 7
    for eid in ids:
        profile = reg.load(eid)
        assert profile.id == eid


def test_decomposer_signals_no_hardcode():
    from voly.a2a.roles import ROLE_REGISTRY

    roles_with_signals = [
        r for r in ROLE_REGISTRY.values() if r.decomposer_signals
    ]
    assert len(roles_with_signals) >= 4


def test_scoring_weights_sum_to_one():
    from voly.capability.scorer import ROUTING_SCORE_WEIGHTS

    total = sum(ROUTING_SCORE_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.001)
