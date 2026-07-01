"""Реестр DSPy программ."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from codeops.dspy.programs.base import BaseProgram, ProgramDefinition

logger = logging.getLogger(__name__)


class DSPyProgramRegistry:
    """Хранит определения программ, регистрируемых плагинами."""

    def __init__(self) -> None:
        self._programs: dict[str, ProgramDefinition] = {}

    def register(self, program: BaseProgram) -> None:
        if not program.program_id:
            raise ValueError(f"DSPy программа {type(program).__name__} не имеет program_id")

        definition = ProgramDefinition(
            program_id=program.program_id,
            agents=tuple(program.agents),
            strategy=program.strategy,
            description=program.description,
            factory=program.build,
            metric=program.get_metric(),
            inputs_builder=program.get_inputs,
        )

        previous = self._programs.get(program.program_id)
        if previous:
            logger.debug(
                "dspy.registry: перезапись %s (было agents=%s → стало agents=%s)",
                program.program_id,
                previous.agents,
                definition.agents,
            )

        self._programs[program.program_id] = definition
        logger.debug(
            "dspy.registry: зарегистрирована %s → agents=%s",
            program.program_id,
            definition.agents,
        )

    def get(self, program_id: str) -> ProgramDefinition | None:
        return self._programs.get(program_id)

    def get_for_agent(self, agent: str) -> list[ProgramDefinition]:
        return [p for p in self._programs.values() if agent in p.agents]

    def get_primary(self, agent: str) -> ProgramDefinition | None:
        for definition in self._programs.values():
            if definition.agents and definition.agents[0] == agent:
                return definition
        matches = self.get_for_agent(agent)
        return matches[0] if matches else None

    def list_all(self) -> list[ProgramDefinition]:
        return list(self._programs.values())

    def agents(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for definition in self._programs.values():
            for agent in definition.agents:
                if agent not in seen:
                    seen.add(agent)
                    result.append(agent)
        return result

    def program_ids(self) -> list[str]:
        return list(self._programs.keys())


_registry: DSPyProgramRegistry | None = None


def get_registry() -> DSPyProgramRegistry:
    global _registry
    if _registry is None:
        _registry = DSPyProgramRegistry()
        _load_builtins()
    return _registry


def register_program(program: BaseProgram) -> None:
    get_registry().register(program)


def list_program_ids() -> list[str]:
    return get_registry().program_ids()


def _load_builtins() -> None:
    builtin_modules = [
        "codeops.dspy.programs.task_planner",
        "codeops.dspy.programs.reviewer",
        "codeops.dspy.programs.architect",
        "codeops.dspy.programs.documenter",
        "codeops.dspy.programs.bugfixer",
        "codeops.dspy.programs.router",
    ]

    for module_path in builtin_modules:
        try:
            importlib.import_module(module_path)
        except ImportError as exc:  # pragma: no cover - окружения без dspy
            logger.debug("dspy.registry: не удалось импортировать %s: %s", module_path, exc)
