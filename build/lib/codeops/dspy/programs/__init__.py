"""DSPy program registry and built-in program definitions."""

from __future__ import annotations

from codeops.dspy.programs.registry import (
    DSPyProgramRegistry,
    get_registry,
    list_program_ids,
    register_program,
)

__all__ = [
    "DSPyProgramRegistry",
    "get_registry",
    "list_program_ids",
    "register_program",
]
