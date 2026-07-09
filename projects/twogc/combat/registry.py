"""Combat mission registry for 2GC."""
from __future__ import annotations

from pathlib import Path

import click

from projects.twogc.missions._loader import MISSIONS_DIR, load_missions_from_dir


def get_combat_missions() -> dict[str, dict]:
    return load_missions_from_dir(MISSIONS_DIR)


def combat_mission_names() -> list[str]:
    return sorted(get_combat_missions().keys())


def mission_source_tag(mission: dict) -> str:
    src = mission.get("_source")
    if src:
        return f"file:{Path(src).name}"
    return "inline"


class CombatMissionName(click.ParamType):
    name = "mission_name"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        names = combat_mission_names()
        if value not in names:
            self.fail(
                f"Unknown mission '{value}'. Available: {', '.join(names)}\n"
                f"  New mission: voly twogc combat init <name>"
            )
        return value


COMBAT_MISSION_NAME = CombatMissionName()
