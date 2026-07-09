"""2GC CloudBridge — VOLY combat missions for MTS B2B Store."""
from __future__ import annotations

import click

from projects.twogc.combat.registry import (
    COMBAT_MISSION_NAME,
    combat_mission_names,
    get_combat_missions,
    mission_source_tag,
)
from projects.twogc.combat.runner import run_mission
from projects.twogc.context import MTS_2GC
from projects.twogc.missions._loader import MISSIONS_DIR


@click.group()
def twogc() -> None:
    """2GC CloudBridge — MTS B2B Store deployment missions."""
    pass


@twogc.group("combat")
def twogc_combat() -> None:
    """Combat missions for mts-2gc and CloudBridge Relay bundle."""
    pass


@twogc_combat.command("list")
def combat_list() -> None:
    click.echo("2GC combat missions:\n")
    click.echo(f"  Missions dir: {MISSIONS_DIR}\n")
    for name in combat_mission_names():
        mission = get_combat_missions()[name]
        agents = " → ".join(t["agent"] for t in mission["tasks"])
        click.echo(f"  {name:30s}  [{mission_source_tag(mission)}]  {mission['description']}")
        click.echo(f"  {'':30s}  [{agents}]")
        click.echo()


@twogc_combat.command("show")
@click.argument("mission_name", type=COMBAT_MISSION_NAME)
def combat_show(mission_name: str) -> None:
    mission = get_combat_missions()[mission_name]
    click.echo(f"Mission: {mission_name}")
    if mission.get("_source"):
        click.echo(f"  Path: {mission['_source']}")
    click.echo(f"  {mission['description']}\n")
    for i, step in enumerate(mission["tasks"], 1):
        click.echo(f"  {i}. [{step['agent']}] {step['label']}")
        preview = step["task"].strip().split("\n", 1)[0][:100]
        click.echo(f"     {preview}…")


@twogc_combat.command("run")
@click.argument("mission_name", type=COMBAT_MISSION_NAME)
@click.option("--parallel/--sequential", default=True, show_default=True)
@click.option("--save/--no-save", default=True)
@click.option("--from-step", default=1, show_default=True)
def combat_run(mission_name: str, parallel: bool, save: bool, from_step: int) -> None:
    """Run combat mission (default cwd: mts-2gc)."""
    run_mission(
        mission_name,
        sequential=not parallel,
        save=save,
        from_step=from_step,
    )


@twogc.command("info")
def twogc_info() -> None:
    click.echo(f"MTS_2GC_PATH={MTS_2GC}")
    click.echo("Run: voly twogc combat list")
