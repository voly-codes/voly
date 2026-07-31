"""CLI for the offline research-first shadow pilot."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.group("research")
def research_cmd() -> None:
    """Inspect local evidence before choosing reuse, adapt, or build."""


@research_cmd.command("shadow")
@click.argument("task")
@click.option("--cwd", type=click.Path(path_type=Path), default=Path("."))
@click.option("--json-out", is_flag=True)
@click.pass_context
def research_shadow(
    ctx: click.Context, task: str, cwd: Path, json_out: bool
) -> None:
    """Record a local-only recommendation without changing routing."""
    from voly.research import run_research, save_report

    config = ctx.obj["config"].research
    report = run_research(
        task,
        cwd,
        max_candidates=config.max_candidates,
        max_duration_ms=config.max_duration_ms,
    )
    reports_dir = Path(config.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = cwd / reports_dir
    path = save_report(report, reports_dir)
    if json_out:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(
        f"{report.decision.value}: eligible={str(report.eligible).lower()} "
        f"candidates={len(report.candidates)} duration_ms={report.duration_ms:.1f}"
    )
    if report.candidates:
        click.echo(f"selected: {report.candidates[0].location}")
    click.echo(f"report: {path}")


@research_cmd.command("benchmark")
@click.argument("tasks", nargs=-1, required=True)
@click.option("--cwd", type=click.Path(path_type=Path), default=Path("."))
def research_benchmark(tasks: tuple[str, ...], cwd: Path) -> None:
    """Compare build-only baseline with local research recommendations."""
    from voly.research import run_research

    reports = [run_research(task, cwd) for task in tasks]
    avoided = sum(report.decision.value != "build" for report in reports)
    click.echo(json.dumps({
        "tasks": len(reports),
        "baseline_builds": len(reports),
        "research_builds": len(reports) - avoided,
        "builds_avoided": avoided,
        "network_calls": 0,
        "total_duration_ms": round(sum(r.duration_ms for r in reports), 2),
    }, ensure_ascii=False, indent=2))
