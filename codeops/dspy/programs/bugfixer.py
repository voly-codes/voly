"""DSPy программа для анализа багов."""

from __future__ import annotations

from typing import Any

from codeops.dspy.programs.base import BaseProgram
from codeops.dspy.programs.registry import register_program


class BugfixerProgram(BaseProgram):
    program_id = "bug-analysis"
    agents = ("bugfixer",)
    strategy = "chain_of_thought"
    description = "Поиск первопричины и патча для бага"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        from codeops.dspy.signatures import build_analyze_bug_signature

        signature = build_analyze_bug_signature()
        return dspy.ChainOfThought(signature)

    def get_metric(self) -> Any:
        from codeops.dspy.metrics import bugfix_metric

        return bugfix_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "code_context": self._extract_code_context(messages),
            "stack_trace": self._extract_stack_trace(messages),
        }


register_program(BugfixerProgram())
