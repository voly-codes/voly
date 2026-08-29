"""Phase 2 (docs/proposals/agent-workflow-sdk.md): Workflow builder -> Plan.

Workflow must remain a builder, not a second runtime: compile() produces an
ordinary Plan; run()/arun() execute it through the existing PlanRunner and
persist it through the existing PlanStore.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from voly import Agent, NodeResult, Workflow, WorkflowError, WorkflowResult
from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult
from voly.plan.approval import decide as decide_human_review
from voly.plan.runner import PlanRunner
from voly.plan.store import PlanStore
from voly.plan.types import PENDING, VERIFIED, VERIFYING
from voly.runner.agent_runner import RunnerResult


def _config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


def _fake_chat(content_by_agent: dict[str, str] | None = None):
    content_by_agent = content_by_agent or {}

    def _chat(self, **kwargs):  # noqa: ANN001
        agent = kwargs.get("agent", "")
        content = content_by_agent.get(agent, f"output from {agent}")
        return {"content": content, "model": "claude-x", "usage": {"input_tokens": 1, "output_tokens": 1}}

    return _chat


def test_import_smoke() -> None:
    from voly import Workflow as ImportedWorkflow

    assert ImportedWorkflow is Workflow


def test_compile_is_deterministic_in_topology(tmp_path) -> None:
    a = Agent("developer", mode="executor", executor="claude-code")
    b = Agent("reviewer")
    workflow = Workflow("mixed", config=_config(tmp_path))
    workflow.add("write", agent=a, task="write code")
    workflow.add("review", agent=b, depends_on=["write"])

    def topology(plan):
        return [(s.id, s.role, s.mode, s.depends_on, s.executor, s.task) for s in plan.steps]

    plan1 = workflow.compile("build a thing", cwd="/tmp/proj")
    plan2 = workflow.compile("build a thing", cwd="/tmp/proj")

    assert topology(plan1) == topology(plan2)
    assert plan1.plan_id != plan2.plan_id  # runtime ids may differ


def test_compile_tags_the_plan_as_sdk_workflow(tmp_path) -> None:
    """metadata["kind"] must stay "sdk_workflow" (never "business_decision") so
    voly.decisions.DecisionService correctly refuses these Plans and the
    generic voly.plan.approval.decide() is the only resolver."""
    workflow = Workflow("tagged", config=_config(tmp_path))
    workflow.add("x", agent=Agent("a"))
    plan = workflow.compile("task")
    assert plan.metadata["kind"] == "sdk_workflow"
    assert plan.metadata["workflow_name"] == "tagged"


def test_duplicate_node_id_rejected(tmp_path) -> None:
    workflow = Workflow("dup", config=_config(tmp_path))
    workflow.add("x", agent=Agent("a"))
    with pytest.raises(WorkflowError, match="duplicate"):
        workflow.add("x", agent=Agent("b"))


def test_missing_dependency_rejected(tmp_path) -> None:
    workflow = Workflow("missing-dep", config=_config(tmp_path))
    workflow.add("x", agent=Agent("a"), depends_on=["nope"])
    with pytest.raises(WorkflowError, match="nope"):
        workflow.compile("task")


def test_cycle_rejected(tmp_path) -> None:
    workflow = Workflow("cycle", config=_config(tmp_path))
    workflow.add("x", agent=Agent("a"), depends_on=["y"])
    workflow.add("y", agent=Agent("b"), depends_on=["x"])
    with pytest.raises(WorkflowError, match="cycle"):
        workflow.compile("task")


def test_empty_workflow_rejected(tmp_path) -> None:
    with pytest.raises(WorkflowError, match="no nodes"):
        Workflow("empty", config=_config(tmp_path)).compile("task")


def test_output_handoff_to_dependent_node(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("handoff", config=config)
    workflow.add("research", agent=Agent("researcher", config=config))
    workflow.add("review", agent=Agent("reviewer", config=config), depends_on=["research"])

    seen = []

    def chat(self, **kwargs):
        seen.append(kwargs["messages"][0]["content"])
        if kwargs["agent"] == "researcher":
            return {"content": "Market A grew 5%.", "model": "x", "usage": {}}
        return {"content": "reviewed", "model": "x", "usage": {}}

    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run("Compare two markets")

    assert result.success is True
    assert "Compare two markets" in seen[0]
    assert "Market A grew 5%" in seen[1]
    assert "Compare two markets" in seen[1]


def test_approval_blocks_downstream_execution(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("decision-flow", config=config)
    workflow.add("decide", agent=Agent("manager", config=config), approval=True)
    workflow.add("notify", agent=Agent("notifier", config=config), depends_on=["decide"])

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        result = workflow.run("Should we proceed?")

    assert result.success is False
    assert result.status == "running"
    assert result.node("decide").status == VERIFYING
    assert result.node("notify").status == PENDING

    store = PlanStore(config.plan.store_dir)
    decide_human_review(store, result.plan.plan_id, "decide", "approve")

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        resumed = PlanRunner(config, emit_event=False).resume(result.plan.plan_id)

    assert resumed.success is True
    assert resumed.plan.get_step("notify").status == VERIFIED


def test_mixed_chat_executor_graph_honors_cwd(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("mixed-cwd", config=config)
    workflow.add("write", agent=Agent("developer", mode="executor", executor="claude-code", config=config), task="write code")
    workflow.add("review", agent=Agent("reviewer", config=config), depends_on=["write"])

    er = ExecutorResult(success=True, output="wrote file")
    runner_result = RunnerResult(success=True, executor="claude-code", agent="developer", task_id="tid", result=er)

    with patch("voly.runner.agent_runner.AgentRunner.run", return_value=runner_result) as run_mock, \
         patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        result = workflow.run("build a thing", cwd=str(tmp_path))

    assert result.success is True
    assert result.plan.cwd == str(tmp_path)
    assert run_mock.call_args.kwargs["cwd"] == str(tmp_path)
    assert result.node("write").status == VERIFIED


def test_round_trip_through_plan_store(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("persisted", config=config)
    workflow.add("a", agent=Agent("x", config=config))
    workflow.add("b", agent=Agent("y", config=config), depends_on=["a"])

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        result = workflow.run("do the thing")

    store = PlanStore(config.plan.store_dir)
    loaded = store.load(result.plan.plan_id)
    assert loaded is not None
    assert [s.id for s in loaded.steps] == ["a", "b"]
    assert loaded.status == result.plan.status
    assert loaded.get_step("b").depends_on == ["a"]


def test_run_aggregates_cost_across_nodes(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("cost", config=config)
    workflow.add("a", agent=Agent("x", config=config))
    workflow.add("b", agent=Agent("y", config=config), depends_on=["a"])

    def chat(self, **kwargs):
        return {"content": "ok", "model": "claude-3-5-sonnet", "usage": {"input_tokens": 100, "output_tokens": 50}}

    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run("task")

    assert result.cost_usd > 0
    assert result.cost_usd == pytest.approx(sum(n.cost_usd for n in result.node_results))


def test_run_never_reports_success_when_a_node_fails(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("fails", config=config)
    workflow.add("a", agent=Agent("x", config=config))
    workflow.add("b", agent=Agent("y", config=config), depends_on=["a"])

    def chat(self, **kwargs):
        return {"error": "boom", "content": ""}

    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run("task")

    assert result.success is False
    assert result.node("a").success is False
    assert result.node("b").status == PENDING


def test_run_resume_true_is_not_implemented_yet(tmp_path) -> None:
    workflow = Workflow("r", config=_config(tmp_path))
    workflow.add("x", agent=Agent("a"))
    with pytest.raises(NotImplementedError):
        workflow.run("task", resume=True)


def test_arun_matches_run(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("async", config=config)
    workflow.add("a", agent=Agent("x", config=config))

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        result = asyncio.run(workflow.arun("task"))

    assert isinstance(result, WorkflowResult)
    assert result.success is True


def test_workflow_result_node_lookup(tmp_path) -> None:
    config = _config(tmp_path)
    workflow = Workflow("lookup", config=config)
    workflow.add("a", agent=Agent("x", config=config))

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _fake_chat()):
        result = workflow.run("task")

    assert isinstance(result.node("a"), NodeResult)
    assert result.node("missing") is None


def test_workflow_name_rejects_path_separators() -> None:
    with pytest.raises(WorkflowError):
        Workflow("bad/name")
