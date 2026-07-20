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
    roles = td._signal_driven_roles("review the screenshot for accessibility wcag")
    assert "visual_reviewer" in roles
    roles_figma = td._signal_driven_roles("compare the figma mock to the implemented UI")
    assert "visual_reviewer" in roles_figma


def test_signal_driven_roles_no_match():
    from voly.a2a.decomposer import TaskDecomposer

    td = TaskDecomposer()
    roles = td._signal_driven_roles("fix the database migration")
    assert "visual_reviewer" not in roles
    assert "browser_tester" not in roles
    assert "ui_architect" not in roles
    assert "ux_reviewer" not in roles


def test_signal_driven_roles_no_false_positive_on_backend_design():
    """Regression: bare 'design' matched 'architecture design' → visual_reviewer."""
    from voly.a2a.decomposer import TaskDecomposer

    td = TaskDecomposer()
    prompt = (
        "Implement and extend this Python project (architecture design, code generation, "
        "tests, devops packaging, and code review required). FastAPI /health endpoint."
    )
    roles = td._signal_driven_roles(prompt)
    assert "visual_reviewer" not in roles
    assert "ui_architect" not in roles
    assert "browser_tester" not in roles
    assert "ux_reviewer" not in roles

    # Full high-complexity decompose must also stay free of frontend extras.
    from voly.router import TaskAnalysis

    analysis = TaskAnalysis(
        intent="implement",
        complexity="high",
        requires_code_gen=True,
        requires_testing=True,
        requires_review=True,
        requires_deployment=True,
    )
    subs = td.decompose(prompt, analysis)
    agents = {s.agent for s in subs}
    assert "visual_reviewer" not in agents
    assert "ui_architect" not in agents


def test_seed_model_providers_exist():
    import os

    seeds_dir = os.path.join(os.path.dirname(__file__), "..", "voly", "capability", "seeds")
    for name in ["kimi-cli-vision.yaml", "claude-vision.yaml"]:
        assert os.path.exists(os.path.join(seeds_dir, name))
