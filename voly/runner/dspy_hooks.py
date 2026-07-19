"""Optional DSPy TaskPlanner hooks used by AgentRunner."""

from __future__ import annotations

import logging

from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult

_chain_log = logging.getLogger("voly.chain")


def _dspy_plan_task(
    task: str,
    config: VOLYConfig,
) -> tuple[str, dict]:
    """
    Use DSPy TaskPlannerProgram to refine the task before sending to executor.

    Returns (refined_task, plan_dict). On any failure returns original task unchanged.
    The plan_dict contains: refined_task, success_criteria, estimated_complexity.
    """
    from voly.dspy.programs.registry import get_registry
    from voly.dspy.adapter import VOLYDSPyLM
    from voly.ai_gateway import AIGateway

    registry = get_registry()
    program_def = registry.get("task_planner")
    if program_def is None:
        return task, {}

    import dspy

    gateway = AIGateway(config)
    lm = VOLYDSPyLM(
        gateway=gateway,
        model=getattr(config.dspy, "model", "") or "",
        provider="",
        agent="developer",
        max_tokens=1024,
        temperature=0.3,
    )
    dspy.configure(lm=lm)

    module = program_def.factory()
    prediction = module(task=task, project_context="VOLY project")

    refined = getattr(prediction, "refined_task", "") or task
    criteria = getattr(prediction, "success_criteria", "") or ""
    complexity = getattr(prediction, "estimated_complexity", "") or ""

    if refined and refined.strip() and refined.strip() != task.strip():
        plan = {
            "refined_task": refined,
            "success_criteria": criteria,
            "estimated_complexity": complexity,
        }
        _chain_log.info(
            "[CHAIN:DSPY_PLAN] complexity=%s criteria_lines=%d refined=%r",
            complexity, criteria.count("\n") + 1, refined[:80],
        )
        return refined, plan

    return task, {}


def _dspy_store_example(
    original_task: str,
    refined_task: str,
    result: ExecutorResult,
    config: VOLYConfig,
) -> None:
    """Persist a (task, result) example for DSPy teleprompter optimization."""
    import json
    import os
    import time as _time
    import uuid as _uuid

    datasets_dir = os.path.join(
        config.dspy.datasets_dir,
        "task_planner",
    )
    os.makedirs(datasets_dir, exist_ok=True)

    example = {
        "task": original_task,
        "refined_task": refined_task,
        "success": result.success,
        "output_len": len(result.output or ""),
        "cost_usd": result.cost_usd,
    }

    # One file per example. Unix-second timestamp alone collides when two
    # examples are produced within the same second (plausible with the
    # concurrent /api/run thread pool) and mode "w" silently overwrites the
    # earlier one — add a random suffix to guarantee uniqueness while keeping
    # the timestamp prefix for chronological sorting.
    fname = os.path.join(datasets_dir, f"{int(_time.time())}-{_uuid.uuid4().hex[:8]}.jsonl")
    with open(fname, "w") as f:
        f.write(json.dumps(example) + "\n")

    _chain_log.debug("[CHAIN:DSPY_STORE] saved example to %s", fname)
