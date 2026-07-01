"""
DSPy TaskPlanner program.

Sits at the boundary between AgentRunner and the executor:
  task (input) → DSPy ChainOfThought → refined_task + success_criteria
  executor runs → result (output) → stored as (task, result) example

This creates a feedback loop that DSPy teleprompters can later optimize:
  dspy.BootstrapFewShot / MIPROv2 compiles on collected (task, result) pairs
  to find better prompts/chain-of-thought prefixes for the task_planner program.

Usage:
  auto — AgentRunner calls this when dspy.enabled and executor path
  manual:
    from codeops.dspy.programs.task_planner import TaskPlannerProgram
    program = TaskPlannerProgram()
    module = program.build()
    result = module(task="add JWT auth to FastAPI app", project_context="Python/FastAPI")
"""

from __future__ import annotations

from typing import Any

from codeops.dspy.programs.base import BaseProgram
from codeops.dspy.programs.registry import register_program


def _build_task_planner_signature() -> type:
    import dspy

    class PlanTask(dspy.Signature):
        """Break down a developer task into a clear, actionable execution plan.

        Given a task description and project context, produce a refined version
        of the task that is specific, scoped, and actionable. Include acceptance
        criteria so the executor knows when the task is done.
        """

        task: str = dspy.InputField(
            desc="The original developer task as submitted by the user"
        )
        project_context: str = dspy.InputField(
            desc="Brief summary of the project: language, framework, key files"
        )

        refined_task: str = dspy.OutputField(
            desc=(
                "A rewritten, more specific version of the task. "
                "Include: what to do, which files/modules to touch, "
                "and any constraints (e.g. do not break existing tests)."
            )
        )
        success_criteria: str = dspy.OutputField(
            desc=(
                "Bullet list of acceptance criteria. The executor should be able "
                "to check these to verify the task is complete."
            )
        )
        estimated_complexity: str = dspy.OutputField(
            desc="low | medium | high — how complex this task is for an AI executor"
        )

    return PlanTask


class TaskPlannerProgram(BaseProgram):
    program_id  = "task_planner"
    agents      = ("developer", "architect", "bugfixer", "tester", "devops")
    strategy    = "chain_of_thought"
    description = "Plans and refines tasks before executor runs; collects (task, result) for DSPy optimization"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        return dspy.ChainOfThought(_build_task_planner_signature())

    def get_metric(self) -> Any:
        """Metric: reward refined_task that is longer/more specific than the original."""

        def task_quality_metric(example: Any, prediction: Any, trace: Any = None) -> float:
            original = getattr(example, "task", "") or ""
            refined  = getattr(prediction, "refined_task", "") or ""
            criteria = getattr(prediction, "success_criteria", "") or ""
            if not refined:
                return 0.0
            # Score: specificity (length ratio) + criteria completeness
            specificity = min(len(refined) / max(len(original), 1), 3.0) / 3.0
            criteria_score = min(criteria.count("\n") + criteria.count("•") + criteria.count("-"), 5) / 5.0
            return 0.6 * specificity + 0.4 * criteria_score

        return task_quality_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        project_ctx = self._extract_project_context(route)
        # Look for any context block injected by _gather_local_context
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and "## Relevant local files" in content:
                # Summarise: just file names
                lines = content.splitlines()
                files = [l.replace("### ", "").strip() for l in lines if l.startswith("### ")]
                if files:
                    project_ctx = f"{project_ctx}\nContext files: {', '.join(files[:5])}"
                break
        return {"task": task, "project_context": project_ctx}


register_program(TaskPlannerProgram())
