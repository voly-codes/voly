"""PR1: plan state machine — types, store, engine (gates + transitions)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voly.plan import (
    DONE,
    FAILED,
    MODE_CHAT,
    MODE_EXECUTOR,
    PENDING,
    PLAN_ABORTED,
    PLAN_COMPLETED,
    PLAN_FAILED,
    PLAN_PENDING,
    PLAN_RUNNING,
    RUNNING,
    SKIPPED,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    IllegalTransition,
    Plan,
    PlanEngine,
    PlanStep,
    PlanStore,
    PlanValidationError,
    create_plan,
)


def _two_step_plan(**kwargs) -> Plan:
    return create_plan(
        "p1",
        [
            PlanStep(id="design", role="architect", mode=MODE_CHAT),
            PlanStep(
                id="implement",
                role="developer",
                mode=MODE_EXECUTOR,
                depends_on=["design"],
            ),
        ],
        **kwargs,
    )


@pytest.fixture()
def engine() -> PlanEngine:
    return PlanEngine()


# ── Validation / topo ────────────────────────────────────────────────────────


def test_validate_and_topo_order(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    engine.validate(plan)
    assert engine.topo_order(plan) == ["design", "implement"]


def test_topo_with_diamond(engine: PlanEngine) -> None:
    plan = create_plan(
        "diamond",
        [
            PlanStep(id="a"),
            PlanStep(id="b", depends_on=["a"]),
            PlanStep(id="c", depends_on=["a"]),
            PlanStep(id="d", depends_on=["b", "c"]),
        ],
    )
    order = engine.topo_order(plan)
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_cycle_rejected(engine: PlanEngine) -> None:
    plan = Plan(
        plan_id="cyc",
        steps=[
            PlanStep(id="a", depends_on=["b"]),
            PlanStep(id="b", depends_on=["a"]),
        ],
    )
    with pytest.raises(PlanValidationError, match="cycle"):
        engine.validate(plan)


def test_duplicate_step_id(engine: PlanEngine) -> None:
    plan = Plan(
        plan_id="dup",
        steps=[PlanStep(id="a"), PlanStep(id="a")],
    )
    with pytest.raises(PlanValidationError, match="duplicate"):
        engine.validate(plan)


def test_unknown_dependency(engine: PlanEngine) -> None:
    plan = Plan(
        plan_id="x",
        steps=[PlanStep(id="a", depends_on=["missing"])],
    )
    with pytest.raises(PlanValidationError, match="unknown"):
        engine.validate(plan)


def test_empty_plan_rejected(engine: PlanEngine) -> None:
    with pytest.raises(PlanValidationError, match="at least one"):
        create_plan("empty", [])


# ── Gate ─────────────────────────────────────────────────────────────────────


def test_can_start_root_only_until_verified(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    assert engine.can_start(plan, "design") is True
    assert engine.can_start(plan, "implement") is False
    assert engine.unmet_deps(plan, "implement") == ["design"]
    assert engine.runnable_steps(plan) == ["design"]


def test_gate_blocks_running_until_dep_verified(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    with pytest.raises(IllegalTransition, match="unmet dependencies"):
        engine.transition(plan, "implement", RUNNING)


def test_after_design_verified_implement_can_start(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    engine.transition(plan, "design", RUNNING)
    engine.transition(plan, "design", DONE)
    engine.transition(plan, "design", VERIFIED)  # no acceptance
    assert plan.get_step("design").status == VERIFIED
    assert engine.can_start(plan, "implement") is True
    engine.transition(plan, "implement", RUNNING)
    assert plan.get_step("implement").status == RUNNING


def test_done_not_enough_for_gate(engine: PlanEngine) -> None:
    """Process-complete (done) is not acceptance-complete (verified)."""
    plan = _two_step_plan()
    engine.transition(plan, "design", RUNNING)
    engine.transition(plan, "design", DONE)
    assert engine.can_start(plan, "implement") is False
    with pytest.raises(IllegalTransition, match="unmet"):
        engine.transition(plan, "implement", RUNNING)


# ── Legal / illegal transitions ──────────────────────────────────────────────


def test_happy_path_empty_acceptance(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    engine.transition(plan, "design", RUNNING)
    engine.mark_execution_finished(plan, "design", success=True, output="ok")
    engine.advance_after_done(plan, "design")
    assert plan.get_step("design").status == VERIFIED

    engine.transition(plan, "implement", RUNNING)
    engine.mark_execution_finished(plan, "implement", success=True)
    engine.advance_after_done(plan, "implement")
    assert plan.get_step("implement").status == VERIFIED
    assert plan.status == PLAN_COMPLETED


def test_happy_path_with_acceptance_goes_verifying(engine: PlanEngine) -> None:
    plan = create_plan(
        "acc",
        [
            PlanStep(
                id="impl",
                mode=MODE_EXECUTOR,
                acceptance=[AcceptanceCheck(type="files_exist", paths=["a.py"])],
            ),
        ],
    )
    engine.transition(plan, "impl", RUNNING)
    engine.transition(plan, "impl", DONE)
    with pytest.raises(IllegalTransition, match="acceptance"):
        engine.transition(plan, "impl", VERIFIED)
    engine.transition(plan, "impl", VERIFYING)
    engine.transition(plan, "impl", VERIFIED)
    assert plan.status == PLAN_COMPLETED


def test_empty_acceptance_cannot_enter_verifying(engine: PlanEngine) -> None:
    plan = create_plan("e", [PlanStep(id="s")])
    engine.transition(plan, "s", RUNNING)
    engine.transition(plan, "s", DONE)
    with pytest.raises(IllegalTransition, match="no acceptance"):
        engine.transition(plan, "s", VERIFYING)
    engine.transition(plan, "s", VERIFIED)


def test_illegal_pending_to_verified(engine: PlanEngine) -> None:
    plan = create_plan("x", [PlanStep(id="s")])
    with pytest.raises(IllegalTransition):
        engine.transition(plan, "s", VERIFIED)


def test_execution_failure(engine: PlanEngine) -> None:
    plan = create_plan("x", [PlanStep(id="s")])
    engine.transition(plan, "s", RUNNING)
    engine.mark_execution_finished(plan, "s", success=False, error="boom")
    step = plan.get_step("s")
    assert step.status == FAILED
    assert "boom" in step.error


def test_retry_from_failed(engine: PlanEngine) -> None:
    plan = create_plan("x", [PlanStep(id="s")])
    engine.transition(plan, "s", RUNNING)
    engine.transition(plan, "s", FAILED, error="e1")
    engine.transition(plan, "s", RUNNING)  # retry
    assert plan.get_step("s").status == RUNNING
    assert plan.get_step("s").error == ""


def test_skip_requires_allow_skip(engine: PlanEngine) -> None:
    plan = create_plan("x", [PlanStep(id="s")])
    with pytest.raises(IllegalTransition, match="skip not allowed"):
        engine.transition(plan, "s", SKIPPED)
    engine.transition(plan, "s", SKIPPED, allow_skip=True)
    assert plan.get_step("s").status == SKIPPED


def test_verify_fail_then_retry(engine: PlanEngine) -> None:
    plan = create_plan(
        "v",
        [
            PlanStep(
                id="s",
                acceptance=[AcceptanceCheck(type="command", run="true")],
            ),
        ],
    )
    engine.transition(plan, "s", RUNNING)
    engine.transition(plan, "s", DONE)
    engine.transition(plan, "s", VERIFYING)
    engine.transition(plan, "s", FAILED, error="check failed")
    engine.transition(plan, "s", RUNNING)
    engine.transition(plan, "s", DONE)
    engine.transition(plan, "s", VERIFYING)
    engine.transition(plan, "s", VERIFIED)
    assert plan.status == PLAN_COMPLETED


# ── Plan-level status ────────────────────────────────────────────────────────


def test_plan_status_pending_to_running(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    assert plan.status == PLAN_PENDING
    engine.transition(plan, "design", RUNNING)
    assert plan.status == PLAN_RUNNING


def test_abort_sticky(engine: PlanEngine) -> None:
    plan = _two_step_plan()
    engine.abort(plan, "user cancel")
    assert plan.status == PLAN_ABORTED
    engine.transition(plan, "design", RUNNING)
    # recompute must not un-abort
    assert plan.status == PLAN_ABORTED


def test_all_skipped_is_failed(engine: PlanEngine) -> None:
    plan = create_plan("x", [PlanStep(id="a"), PlanStep(id="b")])
    engine.transition(plan, "a", SKIPPED, allow_skip=True)
    engine.transition(plan, "b", SKIPPED, allow_skip=True)
    assert plan.status == PLAN_FAILED


# ── Serialization / store ────────────────────────────────────────────────────


def test_roundtrip_dict() -> None:
    plan = create_plan(
        "rt",
        [
            PlanStep(
                id="s",
                acceptance=[AcceptanceCheck(type="files_exist", paths=["f.py"])],
                depends_on=[],
            ),
        ],
        cwd="/tmp/proj",
        task="do thing",
        task_id="t1",
    )
    restored = Plan.from_dict(plan.to_dict())
    assert restored.plan_id == "rt"
    assert restored.cwd == "/tmp/proj"
    assert restored.steps[0].acceptance[0].type == "files_exist"
    assert restored.steps[0].acceptance[0].paths == ["f.py"]


def test_store_save_load_list(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path / "plans"))
    plan = _two_step_plan(cwd="/proj")
    store.save(plan)
    assert store.exists("p1")
    loaded = store.load("p1")
    assert loaded is not None
    assert loaded.plan_id == "p1"
    assert loaded.cwd == "/proj"
    assert [s.id for s in loaded.steps] == ["design", "implement"]
    assert "p1" in store.list_ids()
    assert store.list()[0].plan_id == "p1"

    # atomic file is valid JSON
    raw = json.loads((tmp_path / "plans" / "p1.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


def test_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path / "plans"))
    with pytest.raises(PlanValidationError):
        store.path("../evil")


def test_store_delete(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path / "plans"))
    store.save(_two_step_plan())
    assert store.delete("p1") is True
    assert store.load("p1") is None
    assert store.delete("p1") is False


def test_persist_after_transitions(tmp_path: Path, engine: PlanEngine) -> None:
    store = PlanStore(str(tmp_path / "plans"))
    plan = _two_step_plan()
    engine.transition(plan, "design", RUNNING)
    store.save(plan)
    again = store.load("p1")
    assert again is not None
    assert again.get_step("design").status == RUNNING
    assert again.status == PLAN_RUNNING
