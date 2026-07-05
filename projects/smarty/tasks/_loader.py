"""Load analytical Smarty tasks from tasks/*.yaml."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from projects.smarty.context import mission_context

TASKS_DIR = Path(__file__).resolve().parent
_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


def _expand(text: str) -> str:
    ctx = mission_context()

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            raise ValueError(f"Unknown task template variable {{{{{key}}}}}")
        return ctx[key]

    return _TEMPLATE_VAR.sub(repl, text)


def load_analytical_tasks(tasks_dir: Path | None = None) -> dict[str, list[dict[str, str]]]:
    root = tasks_dir or TASKS_DIR
    loaded: dict[str, list[dict[str, str]]] = {}
    if not root.is_dir():
        return loaded

    for path in sorted(root.glob("*.yaml")):
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        name = raw.get("name") or path.stem
        steps = raw.get("tasks")
        if not isinstance(name, str) or not isinstance(steps, list):
            continue
        loaded[name] = [
            {
                "agent": s["agent"],
                "label": s["label"],
                "task": _expand(s["task"]),
            }
            for s in steps
        ]
    return loaded
