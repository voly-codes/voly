"""Smarty CRM Next — VOLY CLI (thin entry point).

Mission definitions: projects/smarty/missions/*.yaml
Analytical tasks:      projects/smarty/tasks/*.yaml
Shared context:        projects/smarty/context.py
"""
from __future__ import annotations

from pathlib import Path

import click

from projects.smarty.combat.registry import (
    COMBAT_MISSION_NAME,
    combat_mission_names,
    get_combat_missions,
    mission_source_tag,
)
from projects.smarty.combat.runner import run_mission
from projects.smarty.context import SMARTY_PROJECT, SMARTY_REPORTS
from projects.smarty.missions._loader import MISSIONS_DIR, mission_template_yaml
from projects.smarty.tasks._loader import TASKS_DIR, load_analytical_tasks


class _AnalyticalTaskName(click.ParamType):
    name = "task_name"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        names = sorted(load_analytical_tasks().keys())
        if value not in names:
            self.fail(f"Unknown task '{value}'. Available: {', '.join(names)}")
        return value


ANALYTICAL_TASK_NAME = _AnalyticalTaskName()


def _analytical_tasks() -> dict[str, list[dict[str, str]]]:
    return load_analytical_tasks()


@click.group()
def smarty() -> None:
    """Smarty CRM Next — VOLY tasks and combat missions."""
    pass


@smarty.group("combat")
def smarty_combat() -> None:
    """Боевые задания — cursor реализует код на smarty-crm-next."""
    pass


@smarty_combat.command("list")
def combat_list() -> None:
    """List available combat missions."""
    click.echo("Combat missions (voly smarty combat run <name>):\n")
    click.echo(f"  Missions dir: {MISSIONS_DIR}\n")
    for name in combat_mission_names():
        mission = get_combat_missions()[name]
        agents = " → ".join(t["agent"] for t in mission["tasks"])
        tag = mission_source_tag(mission)
        click.echo(f"  {name:22s}  [{tag}]  {mission['description']}")
        click.echo(f"  {'':22s}  [{agents}]")
        click.echo()


@smarty_combat.command("show")
@click.argument("mission_name", type=COMBAT_MISSION_NAME)
def combat_show(mission_name: str) -> None:
    """Show mission steps and source file."""
    mission = get_combat_missions()[mission_name]
    click.echo(f"Mission: {mission_name}")
    click.echo(f"  Source: {mission_source_tag(mission)}")
    if mission.get("_source"):
        click.echo(f"  Path:   {mission['_source']}")
    click.echo(f"  {mission['description']}\n")
    for i, step in enumerate(mission["tasks"], 1):
        click.echo(f"  {i}. [{step['agent']}] {step['label']}")
        preview = step["task"].strip().split("\n", 1)[0][:100]
        click.echo(f"     {preview}…")


@smarty_combat.command("init")
@click.argument("mission_name")
@click.option("--force", is_flag=True, help="Overwrite existing mission file")
def combat_init(mission_name: str, force: bool) -> None:
    """Create a new mission YAML scaffold in missions/."""
    if not mission_name.replace("-", "").replace("_", "").isalnum():
        raise click.ClickException("Mission name must be alphanumeric (hyphens/underscores ok)")
    path = MISSIONS_DIR / f"{mission_name}.yaml"
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists — use --force to overwrite")
    path.write_text(mission_template_yaml(mission_name), encoding="utf-8")
    click.echo(f"Created {path}")
    click.echo(f"Edit the file, then: voly smarty combat run {mission_name} --sequential")


@smarty_combat.command("run")
@click.argument("mission_name", type=COMBAT_MISSION_NAME)
@click.option("--parallel/--sequential", default=False, show_default=True)
@click.option("--sync-catalog/--no-sync-catalog", default=False, help="Force Zen catalog sync before run")
@click.option("--save/--no-save", default=True)
@click.option("--from-step", default=1, show_default=True, help="Resume from step N (1-based)")
def combat_run(mission_name: str, parallel: bool, save: bool, sync_catalog: bool, from_step: int) -> None:
    """Run a combat mission on smarty-crm-next."""
    run_mission(
        mission_name,
        sequential=not parallel,
        save=save,
        sync_catalog=sync_catalog,
        from_step=from_step,
    )


@smarty.command("run")
@click.argument("task_name", type=ANALYTICAL_TASK_NAME)
@click.option("--parallel/--sequential", default=True)
@click.option("--save/--no-save", default=True)
def smarty_run(task_name: str, parallel: bool, save: bool) -> None:
    """Run an analytical multi-agent task (zen/deepseek/mimo)."""
    from voly.executor import AgentTask, MultiAgentOrchestrator

    task_defs = _analytical_tasks()[task_name]
    tasks = [
        AgentTask(
            agent=t["agent"],
            task=t["task"],
            cwd=SMARTY_PROJECT,
            label=t.get("label", ""),
        )
        for t in task_defs
    ]

    reports_dir = SMARTY_REPORTS if save else None
    orch = MultiAgentOrchestrator(reports_dir=reports_dir)

    click.echo(f"[Smarty] Running '{task_name}' with {len(tasks)} agent tasks...")
    report = (
        orch.run_parallel(tasks, report_title=f"Smarty: {task_name}")
        if parallel
        else orch.run_sequential(tasks, report_title=f"Smarty: {task_name}")
    )

    click.echo(f"\n[Smarty] Done in {report.total_duration_ms/1000:.1f}s")
    click.echo(f"  {report.success_count} /  {report.failure_count}")
    if save:
        click.echo(f"  Report: {SMARTY_REPORTS}/")


@smarty.command("list-tasks")
def smarty_list_tasks() -> None:
    """List analytical tasks and combat missions."""
    click.echo("Combat missions:\n")
    for name in combat_mission_names():
        mission = get_combat_missions()[name]
        click.echo(f"  combat run {name:16s} — {mission['description']}")
    click.echo(f"\nAnalytical tasks ({TASKS_DIR}):\n")
    for name, tasks in _analytical_tasks().items():
        agents = ", ".join(t["agent"] for t in tasks)
        click.echo(f"  run {name:20s} — [{agents}]")


@smarty.command("reports")
def smarty_reports() -> None:
    """List agent reports for smarty-crm-next."""
    reports_path = Path(SMARTY_REPORTS)
    if not reports_path.is_dir():
        click.echo(f"No reports dir: {SMARTY_REPORTS}")
        return
    files = sorted(
        [f for f in reports_path.iterdir() if f.suffix == ".md" and f.name != "README.md"],
        key=lambda p: p.name,
        reverse=True,
    )
    if not files:
        click.echo("No reports yet. Run: voly smarty combat run <mission>")
        return
    click.echo(f"Reports in {SMARTY_REPORTS}:\n")
    for f in files[:20]:
        click.echo(f"  {f.name}")
