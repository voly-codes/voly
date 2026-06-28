"""DSPy программа для архитектурного анализа."""

from __future__ import annotations

from typing import Any

from codeops.dspy.programs.base import BaseProgram
from codeops.dspy.programs.registry import register_program


class ArchitectProgram(BaseProgram):
    program_id = "architecture-analysis"
    agents = ("architect",)
    strategy = "chain_of_thought"
    description = "Архитектурные рекомендации и миграционный план"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        from codeops.dspy.signatures import build_architecture_analysis_signature

        signature = build_architecture_analysis_signature()
        return dspy.ChainOfThought(signature)

    def get_metric(self) -> Any:
        from codeops.dspy.metrics import architecture_metric

        return architecture_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "files_summary": self._extract_code_context(messages),
            "current_architecture": self._extract_project_context(route),
        }


register_program(ArchitectProgram())
