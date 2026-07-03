"""DSPy программа для агентного роутинга."""

from __future__ import annotations

from typing import Any

from voly.dspy.programs.base import BaseProgram
from voly.dspy.programs.registry import register_program


class RouterProgram(BaseProgram):
    program_id = "task-routing"
    agents = ("router",)
    strategy = "predict"
    description = "Выбор оптимального агента и инструментов"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        from voly.dspy.signatures import build_route_task_signature

        signature = build_route_task_signature()
        return dspy.Predict(signature)

    def get_metric(self) -> Any:
        from voly.dspy.metrics import routing_metric

        return routing_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "project_context": self._extract_project_context(route),
        }


register_program(RouterProgram())
