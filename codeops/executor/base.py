from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WorkReport:
    """Структурированный мини-отчёт о выполненной задаче."""
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "files_changed": self.files_changed,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "actions": self.actions,
        }


@dataclass
class ExecutorResult:
    success: bool
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0
    num_turns: int = 0
    session_id: str = ""
    metadata: dict = field(default_factory=dict)
    report: WorkReport | None = None


class Executor(ABC):
    @abstractmethod
    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
        timeout: int = 300,
    ) -> ExecutorResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
