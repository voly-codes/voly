from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codeops.router import TaskAnalysis


@dataclass
class Subtask:
    description: str
    agent: str
    depends_on: list[int] = field(default_factory=list)


class TaskDecomposer:
    def decompose(self, task: str, analysis: Any) -> list[Subtask]:
        code_gen = analysis.requires_code_gen
        review = analysis.requires_review
        testing = analysis.requires_testing
        deployment = analysis.requires_deployment
        high = analysis.complexity == "high"

        flag_count = sum([code_gen, review, testing, deployment])

        if code_gen and review and testing and deployment:
            return self._all_flags(task)

        if high and code_gen and review and testing:
            return self._all_flags(task)

        if high and code_gen and review:
            return [
                Subtask(f"Design architecture for: {task}", "architect"),
                Subtask(f"Implement: {task}", "developer", depends_on=[0]),
                Subtask("Review", "reviewer", depends_on=[0]),
            ]

        if high and code_gen:
            return [
                Subtask("Design architecture", "architect"),
                Subtask(f"Implement: {task}", "developer", depends_on=[0]),
            ]

        if code_gen and review and testing:
            return [
                Subtask(f"Implement: {task}", "developer"),
                Subtask("Write tests", "tester", depends_on=[0]),
                Subtask("Review code and tests", "reviewer", depends_on=[0]),
            ]

        if code_gen and review:
            return [
                Subtask(f"Implement: {task}", "developer"),
                Subtask("Review implementation", "reviewer", depends_on=[0]),
            ]

        if code_gen and testing:
            return [
                Subtask(f"Implement: {task}", "developer"),
                Subtask("Write tests", "tester", depends_on=[0]),
            ]

        if code_gen and deployment:
            return [
                Subtask(f"Implement: {task}", "developer"),
                Subtask("Prepare deployment", "devops", depends_on=[0]),
            ]

        if flag_count <= 1:
            return []

        return []

    def _all_flags(self, task: str) -> list[Subtask]:
        return [
            Subtask(f"Design architecture for: {task}", "architect"),
            Subtask(f"Implement: {task}", "developer", depends_on=[0]),
            Subtask("Write tests", "tester", depends_on=[0]),
            Subtask("Review code and tests", "reviewer", depends_on=[0]),
            Subtask("Prepare deployment", "devops", depends_on=[0, 1]),
        ]
