"""Combat mission execution for 2GC."""
from __future__ import annotations

from pathlib import Path

import click

from projects.twogc.combat.registry import get_combat_missions
from projects.twogc.context import MTS_2GC, TGC_SYSTEM


def build_combat_tasks(mission_name: str, mission: dict, sys_prompt: str) -> list:
    from voly.executor import AgentTask

    tasks = []
    for i, tdef in enumerate(mission["tasks"]):
        agent = tdef["agent"]
        is_heavy = agent in ("cursor", "opencode", "claude-code")
        system = sys_prompt if agent == "cursor" else None
        tasks.append(
            AgentTask(
                agent=agent,
                task=tdef["task"],
                cwd=MTS_2GC,
                label=tdef.get("label", ""),
                system=system,
                mission_id=mission_name,
                step_index=i + 1,
                max_turns=40 if is_heavy else 20,
                timeout=900 if is_heavy else 300,
            )
        )
    return tasks


def run_mission(
    mission_name: str,
    *,
    sequential: bool = True,
    save: bool = True,
    system: str | None = None,
    from_step: int = 1,
) -> None:
    from voly.executor import MultiAgentOrchestrator

    mission = get_combat_missions()[mission_name]
    sys_prompt = system or TGC_SYSTEM
    reports_dir = Path(MTS_2GC) / "docs" / "reports" if save else None

    tasks = build_combat_tasks(mission_name, mission, sys_prompt)
    if from_step > 1:
        tasks = tasks[from_step - 1 :]

    click.echo(f"[2GC] Mission: {mission_name}")
    click.echo(f"  Steps: {len(tasks)} ({'sequential' if sequential else 'parallel'})\n")

    orch = MultiAgentOrchestrator(reports_dir=reports_dir)
    report = (
        orch.run_sequential(tasks, report_title=f"2GC: {mission_name}")
        if sequential
        else orch.run_parallel(tasks, report_title=f"2GC: {mission_name}")
    )

    click.echo(f"\n[2GC] Done in {report.total_duration_ms / 1000:.1f}s")
    click.echo(f"  OK {report.success_count} / FAIL {report.failure_count}")
    if save and reports_dir:
        reports_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"  Reports: {reports_dir}/")
