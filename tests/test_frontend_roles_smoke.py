"""Smoke tests for frontend A2A roles and signal-driven decomposition."""

from __future__ import annotations


def test_frontend_roles_in_registry():
    from voly.a2a.roles import ROLE_REGISTRY

    for role_id in ["ui_architect", "visual_reviewer", "browser_tester", "ux_reviewer"]:
        assert role_id in ROLE_REGISTRY, f"{role_id} missing from ROLE_REGISTRY"


def test_decomposer_signals_populated():
    from voly.a2a.roles import ROLE_REGISTRY

    visual = ROLE_REGISTRY["visual_reviewer"]
    assert "screenshot" in visual.decomposer_signals
    browser = ROLE_REGISTRY["browser_tester"]
    assert "playwright" in browser.decomposer_signals


def test_signal_driven_roles_screenshot():
    from voly.a2a.decomposer import TaskDecomposer

    td = TaskDecomposer()
    roles = td._signal_driven_roles("review the screenshot for accessibility")
    assert "visual_reviewer" in roles


def test_signal_driven_roles_no_match():
    from voly.a2a.decomposer import TaskDecomposer

    td = TaskDecomposer()
    roles = td._signal_driven_roles("fix the database migration")
    assert "visual_reviewer" not in roles
    assert "browser_tester" not in roles


def test_seed_model_providers_exist():
    import os

    seeds_dir = os.path.join(os.path.dirname(__file__), "..", "voly", "capability", "seeds")
    for name in ["kimi-cli-vision.yaml", "claude-vision.yaml"]:
        assert os.path.exists(os.path.join(seeds_dir, name))
