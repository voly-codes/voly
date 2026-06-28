"""Базовые классы и протоколы для DSPy программ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


_DSPY_AVAILABLE = False
try:  # pragma: no cover - опциональная зависимость
    import dspy  # noqa: F401

    _DSPY_AVAILABLE = True
except ImportError:  # pragma: no cover - окружения без DSPy
    pass


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:  # pragma: no cover - ошибки создаются выше по стеку
        raise ImportError("DSPy не установлен. Выполните: pip install codeops[dspy]")


@runtime_checkable
class DSPyProgramProtocol(Protocol):
    """Контракт для саморегистрирующихся программ."""

    program_id: str
    agents: tuple[str, ...]
    strategy: str
    description: str

    def build(self) -> Any:  # pragma: no cover - реализация в наследниках
        ...

    def get_metric(self) -> Any:  # pragma: no cover - реализация в наследниках
        ...

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:  # pragma: no cover - реализация в наследниках
        ...


@dataclass
class ProgramDefinition:
    """Метаданные и фабрики зарегистрированной программы."""

    program_id: str
    agents: tuple[str, ...]
    strategy: str
    description: str
    factory: Any
    metric: Any
    inputs_builder: Any

    @property
    def primary_agent(self) -> str:
        return self.agents[0] if self.agents else "unknown"


class BaseProgram:
    """Упрощённая база для встроенных программ."""

    program_id: str = ""
    agents: tuple[str, ...] = ()
    strategy: str = "predict"
    description: str = ""

    # --- интерфейс -----------------------------------------------------

    def build(self) -> Any:
        _require_dspy()
        raise NotImplementedError

    def get_metric(self) -> Any:
        from codeops.dspy.metrics import docs_metric

        return docs_metric

    def get_inputs(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        return {"task": task}

    # --- утилиты -------------------------------------------------------

    @staticmethod
    def _extract_diff(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and ("--- " in content or "+++ " in content or "@@ " in content):
                return content[:4000]
        return ""

    @staticmethod
    def _extract_code_context(messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for msg in messages[-5:]:
            content = msg.get("content")
            if isinstance(content, str) and len(content.strip()) > 20:
                parts.append(content[:800])
        return "\n---\n".join(parts)[:3000]

    @staticmethod
    def _extract_project_context(route: Any) -> str:
        parts: list[str] = []
        agent = getattr(route, "agent", "")
        if agent:
            parts.append(f"agent={agent}")
        config = getattr(route, "config", {})
        if isinstance(config, dict):
            system_prompt = config.get("system_prompt", "")
            if system_prompt:
                parts.append(system_prompt[:300])
        return "\n".join(parts) or "CodeOps project"

    @staticmethod
    def _extract_stack_trace(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and (
                "Traceback" in content or "Error:" in content or "Exception" in content
            ):
                return content[:2000]
        return ""

    @staticmethod
    def ensure_dspy() -> None:
        _require_dspy()
