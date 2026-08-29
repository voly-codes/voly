"""Phase 3 (docs/proposals/agent-workflow-sdk.md): bounded parallel chat
waves, durable resume, stale-running recovery, cancellation and
workflow-level timeout in PlanRunner.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult
from voly.plan import (
    MODE_CHAT,
    MODE_EXECUTOR,
    PLAN_ABORTED,
    PLAN_COMPLETED,
    PLAN_RUNNING,
    RUNNING,
    VERIFIED,
    PlanRunner,
    PlanStep,
    PlanStore,
    create_plan,
)
from voly.runner.agent_runner import RunnerResult


def _config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


def _slow_chat(delay: float = 0.2):
    def _chat(self, **kwargs):  # noqa: ANN001
        time.sleep(delay)
        return {"content": "ok", "model": "claude-3-5-sonnet", "usage": {"input_tokens": 10, "output_tokens": 5}}

    return _chat


def test_wave_runs_independent_chat_nodes_concurrently(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 3
    plan = create_plan(
        "wave-timing",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)

    t0 = time.monotonic()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.3)):
        result = runner.run(plan, mode="active")
    elapsed = time.monotonic() - t0

    assert result.success is True
    assert elapsed < 0.6, f"expected concurrent execution (~0.3s), took {elapsed:.2f}s"


def test_wave_is_bounded_by_max_parallel_nodes(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 2
    plan = create_plan(
        "wave-bounded",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(4)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)

    t0 = time.monotonic()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.2)):
        result = runner.run(plan, mode="active")
    elapsed = time.monotonic() - t0

    assert result.success is True
    # 4 nodes / 2 at a time = 2 waves of ~0.2s each: ~0.4s, not ~0.2s (all
    # at once) or ~0.8s (fully sequential).
    assert 0.35 < elapsed < 0.7, f"expected ~0.4s bounded to 2 concurrent, took {elapsed:.2f}s"


def test_max_parallel_nodes_one_forces_sequential(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 1
    plan = create_plan(
        "wave-disabled",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)

    t0 = time.monotonic()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.2)):
        result = runner.run(plan, mode="active")
    elapsed = time.monotonic() - t0

    assert result.success is True
    assert elapsed > 0.55, f"expected sequential ~0.6s, took {elapsed:.2f}s"


def test_workflow_sdk_disabled_forces_sequential_even_with_high_max_parallel(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.enabled = False
    config.workflow_sdk.max_parallel_nodes = 5
    plan = create_plan(
        "wave-config-disabled",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)

    t0 = time.monotonic()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.2)):
        result = runner.run(plan, mode="active")
    elapsed = time.monotonic() - t0

    assert result.success is True
    assert elapsed > 0.55, f"workflow_sdk.enabled=False must force sequential, took {elapsed:.2f}s"


def test_wave_result_ordering_is_declaration_order_not_completion_order(tmp_path) -> None:
    """A node that finishes first must not reorder node_results."""
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 3
    plan = create_plan(
        "wave-order",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )

    def chat(self, **kwargs):
        # n0 finishes last, n2 finishes first — completion order is reversed.
        content = kwargs["messages"][0]["content"]
        delay = {"t0": 0.3, "t1": 0.15, "t2": 0.05}.get(content, 0.05)
        time.sleep(delay)
        return {"content": content, "model": "x", "usage": {}}

    runner = PlanRunner(config, emit_event=False)
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = runner.run(plan, mode="active")

    assert result.success is True
    assert [s.id for s in result.plan.steps] == ["n0", "n1", "n2"]


def test_no_concurrent_executor_writers_share_cwd(tmp_path) -> None:
    """Executor-mode nodes must never overlap, even with a high
    max_parallel_nodes — they share the Plan's one cwd."""
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 5
    plan = create_plan(
        "exec-serial",
        [PlanStep(id=f"n{i}", mode=MODE_EXECUTOR, executor="claude-code", task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )

    concurrency = {"active": 0, "max": 0}
    lock = threading.Lock()

    def slow_run(self, task, agent, **kwargs):
        with lock:
            concurrency["active"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["active"])
        time.sleep(0.1)
        with lock:
            concurrency["active"] -= 1
        return RunnerResult(
            success=True, executor="claude-code", agent=agent, task_id="t",
            result=ExecutorResult(success=True, output="done"),
        )

    runner = PlanRunner(config, emit_event=False)
    with patch("voly.runner.agent_runner.AgentRunner.run", slow_run):
        result = runner.run(plan, mode="active")

    assert result.success is True
    assert concurrency["max"] == 1


def test_aggregate_cost_counts_every_wave_node_exactly_once(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 3
    plan = create_plan(
        "wave-cost",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )

    def chat(self, **kwargs):
        return {"content": "ok", "model": "claude-3-5-sonnet", "usage": {"input_tokens": 100, "output_tokens": 50}}

    runner = PlanRunner(config, emit_event=False)
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = runner.run(plan, mode="active")

    per_step_cost = result.plan.get_step("n0").cost_usd
    assert per_step_cost > 0
    total = sum(s.cost_usd for s in result.plan.steps)
    assert total == per_step_cost * 3


def test_stale_running_step_is_recovered_and_retried_on_resume(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.stale_running_seconds = 1
    plan = create_plan(
        "stale-test",
        [PlanStep(id="a", mode=MODE_CHAT, status=RUNNING, started_at=time.time() - 999, task="x")],
        cwd=str(tmp_path),
        validate=False,
    )
    store = PlanStore(config.plan.store_dir)
    store.save(plan)
    runner = PlanRunner(config, emit_event=False)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.0)):
        result = runner.resume("stale-test")

    assert result.success is True
    assert result.plan.get_step("a").status == VERIFIED


def test_running_step_not_yet_stale_is_left_alone(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.stale_running_seconds = 999
    plan = create_plan(
        "not-stale-test",
        [
            PlanStep(id="a", mode=MODE_CHAT, status=RUNNING, started_at=time.time(), task="x"),
            PlanStep(id="b", mode=MODE_CHAT, depends_on=["a"], task="y"),
        ],
        cwd=str(tmp_path),
        validate=False,
    )
    store = PlanStore(config.plan.store_dir)
    store.save(plan)
    runner = PlanRunner(config, emit_event=False)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.0)):
        result = runner.resume("not-stale-test")

    # not stale enough to recover, and can_start() never re-picks a
    # `running` step — it stays exactly as it was, paused not failed.
    assert result.plan.get_step("a").status == RUNNING
    assert result.plan.status == PLAN_RUNNING


def test_restart_after_partial_completion_does_not_rerun_verified_nodes(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 1
    plan = create_plan(
        "resume-no-rerun",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(3)],
        cwd=str(tmp_path),
    )

    calls: list[str] = []

    def chat(self, **kwargs):
        calls.append(kwargs["messages"][0]["content"])
        return {"content": "ok", "model": "x", "usage": {}}

    runner = PlanRunner(config, emit_event=False)
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = runner.run(plan, mode="active", timeout_seconds=0.001)

    completed_before = sum(1 for s in result.plan.steps if s.status == VERIFIED)
    assert completed_before < 3
    assert result.plan.status == PLAN_RUNNING

    calls.clear()
    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        resumed = runner.resume("resume-no-rerun")

    assert resumed.success is True
    # Only the not-yet-completed nodes were called again — never the ones
    # already verified before the timeout.
    assert len(calls) == 3 - completed_before


def test_cancel_stops_a_run_in_flight_from_another_thread(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 1
    plan = create_plan(
        "cancel-test",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(5)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)
    holder: dict[str, object] = {}

    def do_run():
        with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.2)):
            holder["result"] = runner.run(plan, mode="active")

    thread = threading.Thread(target=do_run)
    thread.start()
    time.sleep(0.35)
    PlanRunner(config, emit_event=False).cancel("cancel-test", error="user requested stop")
    thread.join(timeout=10)

    result = holder["result"]
    assert result.plan.status == PLAN_ABORTED
    assert result.success is False
    assert result.error == "user requested stop"
    completed = sum(1 for s in result.plan.steps if s.status == VERIFIED)
    assert 0 < completed < 5, f"cancellation should stop the run early, completed={completed}"


def test_cancel_unknown_plan_raises() -> None:
    import pytest

    config = VOLYConfig()
    with pytest.raises(FileNotFoundError):
        PlanRunner(config, emit_event=False).cancel("does-not-exist")


def test_workflow_level_timeout_leaves_a_resumable_state(tmp_path) -> None:
    config = _config(tmp_path)
    config.workflow_sdk.max_parallel_nodes = 1
    plan = create_plan(
        "timeout-test",
        [PlanStep(id=f"n{i}", mode=MODE_CHAT, task=f"t{i}") for i in range(5)],
        cwd=str(tmp_path),
    )
    runner = PlanRunner(config, emit_event=False)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.15)):
        result = runner.run(plan, mode="active", timeout_seconds=0.3)

    assert result.success is False
    assert result.plan.status == PLAN_RUNNING  # resumable, not failed/aborted
    assert "timeout" in result.error
    completed = sum(1 for s in result.plan.steps if s.status == VERIFIED)
    assert 0 < completed < 5

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_chat(0.0)):
        resumed = runner.resume("timeout-test")
    assert resumed.success is True
    assert resumed.plan.status == PLAN_COMPLETED
