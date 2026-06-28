"""DSPy программа для генерации документации."""

from __future__ import annotations

from typing import Any

from codeops.dspy.programs.base import BaseProgram
from codeops.dspy.programs.registry import register_program


class DocumenterProgram(BaseProgram):
    program_id = "generate-docs"
    agents = ("documenter",)
    strategy = "predict"
    description = "Создание технической документации из исходников"

    def build(self) -> Any:
        self.ensure_dspy()
        import dspy
        from codeops.dspy.signatures import build_generate_docs_signature

        signature = build_generate_docs_signature()
        return dspy.Predict(signature)

    def get_metric(self) -> Any:
        from codeops.dspy.metrics import docs_metric

        return docs_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "source_context": self._extract_code_context(messages),
        }


register_program(DocumenterProgram())
