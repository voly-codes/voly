"""PR4: multi-agent plan gates — bridge + run_local integration."""

from __future__ import annotations

from pathlib import Path

from voly.a2a.decomposer import TaskDecomposer
from voly.a2a.multiagent import LeadOrchestrator, run_local
from voly.config import PlanConfig
from voly.plan.bridge import (
    assignment_step_id,
    assignments_to_plan,
    default_acceptance_for_role,
    plan_gates_enabled,
)
from voly.plan.store import PlanStore
from voly.runtime.runs import RunTracker


class _FakeAnalysis:
    complexity = "high"
    requires_code_gen = True
    requires_review = True
    requires_testing = True
    requires_deployment = True


class _FakeGateway:
    def __init__(self, *, empty_architect: bool = False):
        self.calls: list[str] = []
        self.empty_architect = empty_architect

    def chat(self, messages, model, provider_name="anthropic", system=None, agent=None, **kw):
        self.calls.append(agent or "")
        if agent == "lead":
            return {
                "content": "[]",
                "model": model,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        if self.empty_architect and agent == "architect":
            return {
                "content": "   ",
                "model": model,
                "usage": {"input_tokens": 5, "output_tokens": 0},
            }
        return {
            "content": f"output from {agent}",
            "model": model,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }


def _assignments(task: str = "build service"):
    subs = TaskDecomposer().decompose(task, _FakeAnalysis())
    return LeadOrchestrator(gateway=_FakeGateway(), skill_matcher=None).assign(task, subs)


def test_plan_gates_enabled():
    assert plan_gates_enabled(None) is False
    assert plan_gates_enabled(PlanConfig(enabled=False, mode="active")) is False
    assert plan_gates_enabled(PlanConfig(enabled=True, mode="off")) is False
    assert plan_gates_enabled(PlanConfig(enabled=True, mode="shadow", a2a_attach=False)) is False
    assert plan_gates_enabled(PlanConfig(enabled=True, mode="active")) is True


def test_default_acceptance():
    chat = default_acceptance_for_role(
        "architect", "chat", plan_cfg=PlanConfig(chat_require_output=True)
    )
    assert any(c.type == "output_nonempty" for c in chat)

    exe = default_acceptance_for_role(
        "developer",
        "executor",
        plan_cfg=PlanConfig(
            executor_require_git_diff=True,
            executor_file_line_limit=300,
            architect_approved_file_line_limit=500,
        ),
    )
    assert any(c.type == "git_diff_nonempty" for c in exe)
    line_check = next(c for c in exe if c.type == "file_line_limit")
    assert line_check.max_lines == 300
    assert line_check.approved_max_lines == 500

    tester = default_acceptance_for_role(
        "tester",
        "executor",
        plan_cfg=PlanConfig(tester_command="pytest -q"),
    )
    assert any(c.type == "command" and c.run == "pytest -q" for c in tester)


def test_assignments_to_plan_depends_on():
    assignments = _assignments()
    plan = assignments_to_plan(
        "build",
        assignments,
        plan_id="p1",
        role_modes={a.idx: "chat" for a in assignments},
    )
    assert len(plan.steps) == 5
    by_id = {s.id: s for s in plan.steps}
    # developer depends on architect
    dev = next(s for s in plan.steps if s.role == "developer")
    arch_id = assignment_step_id(0, "architect")
    assert arch_id in dev.depends_on
    assert arch_id in by_id


def test_active_empty_architect_blocks_developer(tmp_path: Path):
    """architect fails output_nonempty → developer must not run (active)."""
    gw = _FakeGateway(empty_architect=True)
    subs = TaskDecomposer().decompose("build", _FakeAnalysis())
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)

    plan_cfg = PlanConfig(
        enabled=True,
        mode="active",
        store_dir=str(tmp_path / "plans"),
        a2a_attach=True,
        chat_require_output=True,
    )
    tracker = RunTracker(str(tmp_path / "runs"))
    run_local(
        "build",
        assignments,
        gw,
        skill_matcher=None,
        hybrid_code_gen=False,  # all chat
        task_id="t-active",
        tracker=tracker,
        plan_config=plan_cfg,
        plan_store=PlanStore(str(tmp_path / "plans")),
    )

    by_role = {a.role: a for a in assignments}
    assert by_role["architect"].ok is False
    assert by_role["architect"].plan_status == "failed"
    # developer must not run (blocked by plan gate or skipped prior failure)
    assert by_role["developer"].ok is False
    err = (by_role["developer"].error or "").lower()
    assert (
        "blocked" in err
        or "prior" in err
        or "skipped" in err
        or by_role["developer"].plan_status in ("blocked", "skipped")
    )
    assert "architect" in gw.calls
    assert "developer" not in gw.calls

    rec = tracker.load("t-active")
    assert rec is not None
    assert rec.plan_id.startswith("a2a-")
    assert rec.step_statuses  # snapshot present
    assert len(rec.graph_nodes) == len(assignments)
    assert rec.graph_edges
    by_graph_role = {node["role"]: node for node in rec.graph_nodes}
    assert by_graph_role["architect"]["status"] == "failed"
    assert by_graph_role["developer"]["status"] in ("blocked", "failed")


def test_shadow_empty_architect_still_runs_developer(tmp_path: Path):
    """shadow: verify fail soft-opens gate → developer still runs."""
    gw = _FakeGateway(empty_architect=True)
    subs = TaskDecomposer().decompose("build", _FakeAnalysis())
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)

    plan_cfg = PlanConfig(
        enabled=True,
        mode="shadow",
        store_dir=str(tmp_path / "plans"),
        a2a_attach=True,
        chat_require_output=True,
    )
    run_local(
        "build",
        assignments,
        gw,
        skill_matcher=None,
        hybrid_code_gen=False,
        task_id="t-shadow",
        plan_config=plan_cfg,
        plan_store=PlanStore(str(tmp_path / "plans")),
    )

    by_role = {a.role: a for a in assignments}
    # architect soft-verified
    assert by_role["architect"].plan_status == "verified"
    assert by_role["architect"].plan_verify_ok is False
    assert "developer" in gw.calls
    assert by_role["developer"].ok is True
    assert by_role["developer"].plan_status == "verified"


def test_gates_off_preserves_legacy_behavior(tmp_path: Path):
    gw = _FakeGateway()
    assignments = _assignments()
    run_local(
        "build",
        assignments,
        gw,
        skill_matcher=None,
        hybrid_code_gen=False,
        plan_config=PlanConfig(enabled=False),
    )
    for a in assignments:
        assert a.ok is True
        assert a.plan_status == ""
