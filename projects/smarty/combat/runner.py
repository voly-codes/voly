"""Combat mission execution."""
from __future__ import annotations

from pathlib import Path

import click

from projects.smarty.combat.registry import get_combat_missions
from projects.smarty.context import SMARTY_PROJECT, SMARTY_REPORTS, SMARTY_SYSTEM


def build_combat_tasks(mission_name: str, mission: dict, sys_prompt: str) -> list:
    from voly.executor import AgentTask

    task_defs = mission["tasks"]
    supervisor = None
    step_specs = []

    if mission.get("supervised"):
        from voly.catalog.supervisor import CombatSupervisor

        voly_root = Path(SMARTY_PROJECT) / "voly"
        supervisor = CombatSupervisor(SMARTY_PROJECT, voly_root=voly_root)
        plan = supervisor.plan(mission_name)
        step_specs = plan.steps
        click.echo(f"  Supervisor plan: {len(step_specs)} steps (Zen catalog routing)\n")

    tasks = []
    for i, tdef in enumerate(task_defs):
        spec = step_specs[i] if i < len(step_specs) else None
        agent = spec.executor if spec else tdef["agent"]
        model = spec.model if spec else None
        agent_role = spec.agent_role if spec else agent
        skills = list(spec.skills) if spec else []
        readonly = spec.readonly if spec else False

        needs_system = agent in ("cursor", "opencode", "zen", "claude-code") or skills or readonly
        system = None
        if needs_system:
            if supervisor and spec:
                system = supervisor.build_system_prompt(sys_prompt, spec)
            elif agent == "cursor":
                system = sys_prompt

        is_heavy = agent in ("cursor", "opencode", "claude-code")
        tasks.append(
            AgentTask(
                agent=agent,
                task=tdef["task"],
                cwd=SMARTY_PROJECT,
                label=tdef.get("label", ""),
                system=system,
                model=model,
                agent_role=agent_role,
                skills=skills,
                readonly=readonly,
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
    sync_catalog: bool = False,
    from_step: int = 1,
) -> None:
    from voly.executor import MultiAgentOrchestrator

    missions = get_combat_missions()
    mission = missions[mission_name]
    sys_prompt = system or SMARTY_SYSTEM

    if sync_catalog or mission.get("supervised"):
        try:
            from voly.catalog.supervisor import CombatSupervisor

            voly_root = Path(SMARTY_PROJECT) / "voly"
            sup = CombatSupervisor(SMARTY_PROJECT, voly_root=voly_root)
            n = sup.sync_catalog()
            click.echo(f"[Combat] Catalog synced: {n} Zen models → .voly/catalog/models.json")
        except Exception as exc:
            click.echo(f"[Combat] Catalog sync skipped: {exc}")

    tasks = build_combat_tasks(mission_name, mission, sys_prompt)
    total_steps = len(tasks)
    if from_step < 1 or from_step > total_steps:
        raise click.ClickException(f"--from-step must be between 1 and {total_steps}")
    if from_step > 1:
        tasks = tasks[from_step - 1 :]
        click.echo(f"[Combat] Resuming from step {from_step}/{total_steps}\n")

    reports_dir = SMARTY_REPORTS if save else None
    orch = MultiAgentOrchestrator(reports_dir=reports_dir)

    click.echo(f"[Combat] Mission: {mission_name}")
    click.echo(f"  {mission['description']}")
    click.echo(f"  Project: {SMARTY_PROJECT}")
    click.echo(f"  Steps: {len(tasks)} ({'sequential' if sequential else 'parallel'})\n")
    for i, t in enumerate(tasks, 1):
        model_part = f" · {t.model}" if t.model else ""
        click.echo(f"  {i}. [{t.agent}{model_part}] {t.label}")

    report = (
        orch.run_sequential(
            tasks,
            report_title=f"Combat: {mission_name}",
            stop_on_failure=False,
            emit_telemetry=True,
        )
        if sequential
        else orch.run_parallel(tasks, report_title=f"Combat: {mission_name}")
    )

    click.echo(f"\n[Combat] Done in {report.total_duration_ms/1000:.1f}s")
    click.echo(f"  ✅ {report.success_count} succeeded, ❌ {report.failure_count} failed")
    click.echo(f"  Cost: ${report.total_cost_usd:.4f}")

    for tr in report.tasks:
        icon = "✅" if tr.result.success else "❌"
        click.echo(f"  {icon} [{tr.agent_name}] {tr.task.label[:70]}")
        if tr.result.success and tr.result.output:
            preview = tr.result.output.strip().replace("\n", " ")[:180]
            click.echo(f"     {preview}...")
        elif tr.result.error:
            click.echo(f"     Error: {tr.result.error[:120]}")

    if save and reports_dir:
        click.echo(f"\nReport: {SMARTY_REPORTS}/")

    if report.failure_count > 0:
        raise SystemExit(1)
