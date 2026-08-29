"""Offline contract tests for examples/workflows/ (PR6 of
docs/proposals/agent-workflow-sdk.md).

Each example is loaded by file path (examples/ is not a package under
voly/, so it is never imported by production code) and run via its own
main(offline=True), which patches AIGateway.chat/AgentRunner.run with
canned responses — no credentials, no network, no file writes outside
example 3's own offline-patched AgentRunner.run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from voly.plan.types import VERIFIED

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "workflows"


def _load(name: str):
    path = _EXAMPLES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_01_sequential_research_review() -> None:
    example = _load("01_sequential_research_review")
    seen_prompts: list[str] = []

    def capturing_chat(self, **kwargs):
        seen_prompts.append(kwargs["messages"][0]["content"])
        return example._offline_chat(self, **kwargs)

    from unittest.mock import patch

    workflow = example.build_workflow()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", capturing_chat):
        result = workflow.run("Compare two markets and summarize the growth trend.")

    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["n0", "n1"]
    assert all(n.status == VERIFIED for n in result.node_results)
    # The reviewer's *prompt* must include the researcher's output — the
    # dependency-output handoff this example exists to demonstrate.
    assert "Market A" in seen_prompts[1]


def test_02_parallel_market_analysis() -> None:
    result = _load("02_parallel_market_analysis").main(offline=True)
    assert result.success is True
    ids = {n.node_id for n in result.node_results}
    assert ids == {"supervise", "worker0", "worker1", "worker2", "synthesize"}
    synthesis = result.node("synthesize")
    assert "APAC" in synthesis.output


def test_03_repo_change_tester_reviewer() -> None:
    result = _load("03_repo_change_tester_reviewer").main(offline=True)
    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["develop", "test", "review"]
    assert result.node("develop").files_touched == ["app.py"]


def test_04_human_approved_action() -> None:
    module = _load("04_human_approved_action")
    paused, resumed = module.main(offline=True)
    assert paused.success is False
    assert paused.status == "running"
    assert resumed.success is True
    assert resumed.node("notify").status == VERIFIED


def test_05_incident_triage_parallel_investigators() -> None:
    result = _load("05_incident_triage_parallel_investigators").main(offline=True)
    assert result.success is True
    triage = result.node("triage")
    assert "SEV" in triage.output


def test_06_planner_generator_evaluator() -> None:
    result = _load("06_planner_generator_evaluator").main(offline=True)
    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["plan", "generate", "evaluate"]


def test_07_resumable_long_running_workflow() -> None:
    module = _load("07_resumable_long_running_workflow")
    timed_out, resumed = module.main(offline=True)
    assert timed_out.success is False
    assert timed_out.status == "running"
    assert resumed.success is True
    assert resumed.node("a").status == VERIFIED
    assert resumed.node("c").status == VERIFIED


@pytest.mark.parametrize(
    "name",
    [
        "01_sequential_research_review",
        "02_parallel_market_analysis",
        "03_repo_change_tester_reviewer",
        "04_human_approved_action",
        "05_incident_triage_parallel_investigators",
        "06_planner_generator_evaluator",
        "07_resumable_long_running_workflow",
    ],
)
def test_every_example_has_a_module_docstring_with_required_sections(name: str) -> None:
    """Phase 6 requirement: "Each example must include expected output,
    required credentials, cost/safety notes.\""""
    module = _load(name)
    doc = module.__doc__ or ""
    for section in ("Expected output", "Credentials", "Cost/safety notes"):
        assert section in doc, f"{name} is missing a {section!r} docstring section"
