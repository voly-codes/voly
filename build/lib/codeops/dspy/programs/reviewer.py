"""DSPy программа для кода-ревью."""

from __future__ import annotations

from typing import Any

from codeops.dspy.programs.base import BaseProgram
from codeops.dspy.programs.registry import register_program


class ReviewProgram(BaseProgram):
    program_id = "code-review"
    agents = ("reviewer",)
    strategy = "chain_of_thought"
    description = "Структурированное ревью diff'ов с анализом рисков"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        from codeops.dspy.signatures import build_review_code_signature

        signature = build_review_code_signature()
        return dspy.ChainOfThought(signature)

    def get_metric(self) -> Any:
        from codeops.dspy.metrics import review_metric

        return review_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "diff": self._extract_diff(messages),
            "project_context": self._extract_project_context(route),
        }


register_program(ReviewProgram())
