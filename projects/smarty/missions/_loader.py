"""Load combat missions from missions/*.yaml (and optional *.py)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import yaml

from projects.smarty.missions._constants import mission_context

MISSIONS_DIR = Path(__file__).resolve().parent
_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


class MissionLoadError(Exception):
    pass


def _expand_template(text: str, ctx: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            raise MissionLoadError(f"Unknown template variable {{{{{key}}}}} in mission text")
        return ctx[key]

    return _TEMPLATE_VAR.sub(repl, text)


def _validate_mission(name: str, data: dict[str, Any], source: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MissionLoadError(f"{source}: root must be a mapping")

    description = data.get("description")
    if not description or not isinstance(description, str):
        raise MissionLoadError(f"{source}: missing string field 'description'")

    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise MissionLoadError(f"{source}: 'tasks' must be a non-empty list")

    ctx = mission_context()
    normalized_tasks: list[dict[str, str]] = []
    for i, step in enumerate(tasks, 1):
        if not isinstance(step, dict):
            raise MissionLoadError(f"{source}: task #{i} must be a mapping")
        for field in ("agent", "label", "task"):
            if field not in step or not isinstance(step[field], str):
                raise MissionLoadError(f"{source}: task #{i} missing string '{field}'")
        normalized_tasks.append(
            {
                "agent": step["agent"],
                "label": step["label"],
                "task": _expand_template(step["task"], ctx),
            }
        )

    mission: dict[str, Any] = {
        "description": _expand_template(description, ctx),
        "tasks": normalized_tasks,
        "_source": str(source),
    }
    if data.get("supervised"):
        mission["supervised"] = True
    return mission


def _load_yaml(path: Path) -> tuple[str, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MissionLoadError(f"{path}: YAML root must be a mapping")
    name = raw.get("name") or path.stem
    if not isinstance(name, str):
        raise MissionLoadError(f"{path}: 'name' must be a string")
    payload = {k: v for k, v in raw.items() if k != "name"}
    return name, _validate_mission(name, payload, path)


def _load_py(path: Path) -> tuple[str, dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(f"smarty_mission_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise MissionLoadError(f"{path}: cannot import module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    name = getattr(module, "MISSION_NAME", path.stem)
    data = getattr(module, "MISSION", None)
    if not isinstance(name, str) or not isinstance(data, dict):
        raise MissionLoadError(f"{path}: must define MISSION_NAME: str and MISSION: dict")
    mission = _validate_mission(name, data, path)
    return name, mission


def load_missions_from_dir(missions_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Discover and load all file-based combat missions."""
    root = missions_dir or MISSIONS_DIR
    if not root.is_dir():
        return {}

    loaded: dict[str, dict[str, Any]] = {}
    for path in sorted(root.iterdir()):
        if path.name.startswith("_") or path.suffix not in {".yaml", ".yml", ".py"}:
            continue
        try:
            if path.suffix == ".py":
                name, mission = _load_py(path)
            else:
                name, mission = _load_yaml(path)
        except MissionLoadError:
            raise
        except Exception as exc:
            raise MissionLoadError(f"{path}: {exc}") from exc
        if name in loaded:
            raise MissionLoadError(f"Duplicate mission name '{name}' in {root}")
        loaded[name] = mission
    return loaded


def merge_combat_missions(
    inline: dict[str, dict[str, Any]],
    *,
    missions_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge inline dict with file missions; files override inline on name clash."""
    file_missions = load_missions_from_dir(missions_dir)
    merged = dict(inline)
    for name, mission in file_missions.items():
        merged[name] = mission
    return merged


def mission_template_yaml(name: str) -> str:
    """Scaffold for `combat init`."""
    return f"""# Combat mission: {name}
# Run: python3 -m voly.cli smarty combat run {name} --sequential
# Template vars: {{{{SMARTY_PROJECT}}}}, {{{{LEGACY_GAP_REF}}}}, … — see projects/smarty/context.py

name: {name}

description: >
  Short one-line description of the mission.

# supervised: true   # optional — enable Zen catalog routing

tasks:
  - agent: cursor
    label: "cursor: step 1 title"
    task: |
      STEP 1/N — What to implement.

      {{{{LEGACY_GAP_REF}}}}

      Concrete instructions for the agent…

  - agent: cursor
    label: "cursor: review"
    task: |
      STEP N/N — Review.

      npm run build.
      UPDATE docs/reports/CURRENT_STATUS.md.
"""
