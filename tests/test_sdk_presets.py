"""Phase 4 (docs/proposals/agent-workflow-sdk.md): topology presets.

Every preset is a graph factory over Workflow — these tests check the
compiled graph shape (snapshot), declared bounds, failure propagation and
cost aggregation, per the proposal's Phase 4 "Tests" requirement. No preset
may import a provider client or reimplement PlanRunner scheduling; that's
covered generically by test_sdk_contracts.py's import scan (voly/sdk/**).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from voly.config import VOLYConfig
from voly.plan.types import PENDING, VERIFIED, AcceptanceCheck
from voly.sdk.agent import Agent
from voly.sdk.presets import (
    MAX_COUNCIL_MEMBERS,
    MAX_REVIEWER_ITERATIONS,
    MAX_WORKERS,
    concurrent,
    council,
    planner_generator_evaluator,
    reviewer_loop,
    sequential,
    supervisor_workers,
)
from voly.sdk.workflow import WorkflowError


def _config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


def _chat_ok(self, **kwargs):
    return {"content": f"ok:{kwargs.get('agent', '')}", "model": "x", "usage": {"input_tokens": 1, "output_tokens": 1}}


def _chat_fails_for(agent_name: str):
    def _chat(self, **kwargs):
        if kwargs.get("agent") == agent_name:
            return {"error": "boom", "content": ""}
        return _chat_ok(self, **kwargs)

    return _chat


# ── sequential ────────────────────────────────────────────────────────────


def test_sequential_graph_shape(tmp_path) -> None:
    agents = [Agent("a"), Agent("b"), Agent("c")]
    workflow = sequential(agents, config=_config(tmp_path))
    plan = workflow.compile("task")
    assert [(s.id, s.depends_on) for s in plan.steps] == [
        ("n0", []), ("n1", ["n0"]), ("n2", ["n1"]),
    ]


def test_sequential_requires_at_least_two_agents() -> None:
    with pytest.raises(WorkflowError, match="at least 2"):
        sequential([Agent("a")])


def test_sequential_runs_and_hands_off_output(tmp_path) -> None:
    workflow = sequential([Agent("a"), Agent("b")], config=_config(tmp_path))
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        result = workflow.run("task")
    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["n0", "n1"]


def test_sequential_failure_blocks_downstream(tmp_path) -> None:
    workflow = sequential([Agent("a"), Agent("b")], config=_config(tmp_path))
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_fails_for("a")):
        result = workflow.run("task")
    assert result.success is False
    assert result.node("n1").status == PENDING


# ── concurrent ────────────────────────────────────────────────────────────


def test_concurrent_graph_shape_has_no_dependencies(tmp_path) -> None:
    agents = [Agent("a"), Agent("b"), Agent("c")]
    plan = concurrent(agents, config=_config(tmp_path)).compile("task")
    assert all(s.depends_on == [] for s in plan.steps)
    assert {s.id for s in plan.steps} == {"n0", "n1", "n2"}


def test_concurrent_aggregates_cost_across_all_nodes(tmp_path) -> None:
    def chat(self, **kwargs):
        return {"content": "ok", "model": "claude-3-5-sonnet", "usage": {"input_tokens": 10, "output_tokens": 5}}

    workflow = concurrent([Agent("a"), Agent("b"), Agent("c")], config=_config(tmp_path))
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run("task")
    assert result.success is True
    assert result.cost_usd == pytest.approx(sum(n.cost_usd for n in result.node_results))
    assert result.cost_usd > 0


# ── supervisor_workers ────────────────────────────────────────────────────


def test_supervisor_workers_graph_shape(tmp_path) -> None:
    supervisor = Agent("boss")
    workers = [Agent("w1"), Agent("w2")]
    plan = supervisor_workers(supervisor, workers, config=_config(tmp_path)).compile("task")
    ids = {s.id: s.depends_on for s in plan.steps}
    assert ids["supervise"] == []
    assert ids["worker0"] == ["supervise"]
    assert ids["worker1"] == ["supervise"]
    assert set(ids["synthesize"]) == {"worker0", "worker1"}


def test_supervisor_workers_requires_at_least_one_worker() -> None:
    with pytest.raises(WorkflowError, match="at least 1 worker"):
        supervisor_workers(Agent("boss"), [])


def test_supervisor_workers_bound_enforced() -> None:
    with pytest.raises(WorkflowError, match=str(MAX_WORKERS)):
        supervisor_workers(Agent("boss"), [Agent(f"w{i}") for i in range(MAX_WORKERS + 1)])


def test_supervisor_workers_synthesis_sees_worker_output(tmp_path) -> None:
    seen = []

    def chat(self, **kwargs):
        seen.append((kwargs.get("agent"), kwargs["messages"][0]["content"]))
        return {"content": f"out:{kwargs.get('agent')}", "model": "x", "usage": {}}

    workflow = supervisor_workers(Agent("boss"), [Agent("w1"), Agent("w2")], config=_config(tmp_path))
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run("task")

    assert result.success is True
    # The synthesis call is the *second* "boss" call; its prompt must include worker output.
    boss_prompts = [content for agent, content in seen if agent == "boss"]
    assert len(boss_prompts) == 2
    assert "out:w1" in boss_prompts[1] and "out:w2" in boss_prompts[1]


# ── reviewer_loop ─────────────────────────────────────────────────────────


def test_reviewer_loop_unrolls_bounded_chain(tmp_path) -> None:
    plan = reviewer_loop(Agent("gen"), Agent("rev"), max_iterations=3, config=_config(tmp_path)).compile("task")
    ids = [s.id for s in plan.steps]
    assert ids == [
        "generate_0", "review_0", "generate_1", "review_1", "generate_2", "review_2",
    ]
    steps = plan.step_map()
    assert steps["generate_1"].depends_on == ["review_0"]
    assert steps["review_2"].depends_on == ["generate_2"]


def test_reviewer_loop_bound_enforced() -> None:
    with pytest.raises(WorkflowError, match=str(MAX_REVIEWER_ITERATIONS)):
        reviewer_loop(Agent("gen"), Agent("rev"), max_iterations=MAX_REVIEWER_ITERATIONS + 1)
    with pytest.raises(WorkflowError, match="max_iterations"):
        reviewer_loop(Agent("gen"), Agent("rev"), max_iterations=0)


def test_reviewer_loop_only_gates_the_final_round(tmp_path) -> None:
    """Earlier rounds carry no acceptance (auto-verify) so the chain always
    completes all max_iterations rounds; only the last round's review is
    gated by exit_acceptance — see presets.py docstring for why a true
    early-exit loop isn't implementable over a Plan DAG."""
    exit_check = [AcceptanceCheck(type="output_nonempty")]
    workflow = reviewer_loop(
        Agent("gen"), Agent("rev"), max_iterations=2, exit_acceptance=exit_check,
        config=_config(tmp_path),
    )
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        result = workflow.run("task")

    assert result.success is True
    assert result.node("review_0").status == VERIFIED
    assert result.node("review_1").status == VERIFIED
    assert all(n.status == VERIFIED for n in result.node_results)


def test_reviewer_loop_final_round_failing_exit_criteria_fails_the_workflow(tmp_path) -> None:
    exit_check = [AcceptanceCheck(type="output_regex", pattern="NEVER_MATCHES")]
    workflow = reviewer_loop(
        Agent("gen"), Agent("rev"), max_iterations=2, exit_acceptance=exit_check,
        config=_config(tmp_path),
    )
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        result = workflow.run("task")

    assert result.success is False
    assert result.node("review_0").status == VERIFIED  # unrelated to the failing final gate
    assert result.node("review_1").status != VERIFIED


# ── council ───────────────────────────────────────────────────────────────


def test_council_graph_shape(tmp_path) -> None:
    members = [Agent("m1"), Agent("m2"), Agent("m3")]
    plan = council(members, Agent("judge"), config=_config(tmp_path)).compile("task")
    ids = {s.id: s.depends_on for s in plan.steps}
    assert set(ids["judge"]) == {"member0", "member1", "member2"}
    assert all(ids[f"member{i}"] == [] for i in range(3))


def test_council_requires_at_least_two_members() -> None:
    with pytest.raises(WorkflowError, match="at least 2"):
        council([Agent("m1")], Agent("judge"))


def test_council_bound_enforced() -> None:
    with pytest.raises(WorkflowError, match=str(MAX_COUNCIL_MEMBERS)):
        council([Agent(f"m{i}") for i in range(MAX_COUNCIL_MEMBERS + 1)], Agent("judge"))


def test_council_judge_sees_every_member_output(tmp_path) -> None:
    def chat(self, **kwargs):
        agent = kwargs.get("agent")
        if agent == "judge":
            return {"content": "decision", "model": "x", "usage": {}, "_prompt": kwargs["messages"][0]["content"]}
        return {"content": f"vote:{agent}", "model": "x", "usage": {}}

    captured = {}

    def chat_capture(self, **kwargs):
        result = chat(self, **kwargs)
        if kwargs.get("agent") == "judge":
            captured["prompt"] = kwargs["messages"][0]["content"]
        return result

    workflow = council([Agent("m1"), Agent("m2")], Agent("judge"), config=_config(tmp_path))
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat_capture):
        result = workflow.run("task")

    assert result.success is True
    assert "vote:m1" in captured["prompt"] and "vote:m2" in captured["prompt"]


# ── planner_generator_evaluator ───────────────────────────────────────────


def test_planner_generator_evaluator_graph_shape(tmp_path) -> None:
    plan = planner_generator_evaluator(
        Agent("planner"), Agent("generator"), Agent("evaluator"), config=_config(tmp_path)
    ).compile("task")
    ids = {s.id: s.depends_on for s in plan.steps}
    assert ids == {"plan": [], "generate": ["plan"], "evaluate": ["generate"]}


def test_planner_generator_evaluator_runs_end_to_end(tmp_path) -> None:
    workflow = planner_generator_evaluator(
        Agent("planner"), Agent("generator"), Agent("evaluator"), config=_config(tmp_path)
    )
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        result = workflow.run("task")
    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["plan", "generate", "evaluate"]
