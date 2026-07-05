"""CLI: voly runs — inspect in-flight run records + watchdog (Этап 2, Rung A)."""

from __future__ import annotations

import time

import click


def _fmt_age(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _tracker_and_watchdog(ctx: click.Context):
    from voly.runtime.runs import RunTracker, Watchdog

    config = ctx.obj["config"]
    runs_dir = config.telemetry.runs_dir
    task_timeout = getattr(config.a2a, "task_timeout_seconds", 120.0)
    stale_factor = getattr(config.telemetry, "watchdog_stale_factor", 2.0)
    return (
        RunTracker(runs_dir),
        Watchdog(runs_dir, task_timeout=task_timeout, stale_factor=stale_factor),
    )


@click.group()
def runs() -> None:
    """In-flight multi-agent run records (heartbeat + watchdog)."""
    pass


@runs.command("list")
@click.option("--status", default=None, help="Filter: running|completed|failed|stale")
@click.pass_context
def runs_list(ctx: click.Context, status: str | None) -> None:
    """List run records, newest first."""
    tracker, watchdog = _tracker_and_watchdog(ctx)
    records = tracker.list()
    if not records:
        click.echo("No run records.")
        return

    click.echo(f"{'TASK_ID':<26} {'STATUS':<10} {'PROGRESS':<9} {'AGE':<8} ROLE")
    for r in records:
        shown = "stale" if watchdog.is_stale(r) else r.status
        if status and shown != status:
            continue
        progress = f"{r.done_roles}/{r.total_roles}"
        click.echo(
            f"{r.task_id:<26} {shown:<10} {progress:<9} {_fmt_age(r.age_seconds):<8} {r.current_role}"
        )


@runs.command("show")
@click.argument("task_id")
@click.pass_context
def runs_show(ctx: click.Context, task_id: str) -> None:
    """Show one run record in detail."""
    tracker, watchdog = _tracker_and_watchdog(ctx)
    r = tracker.load(task_id)
    if r is None:
        click.echo(f"No record for {task_id}", err=True)
        raise SystemExit(1)
    shown = "stale" if watchdog.is_stale(r) else r.status
    click.echo(f"task_id:   {r.task_id}")
    click.echo(f"status:    {shown}")
    click.echo(f"task:      {r.task}")
    click.echo(f"progress:  {r.done_roles}/{r.total_roles}  (current: {r.current_role or '—'})")
    click.echo(f"roles:     {', '.join(r.roles)}")
    click.echo(f"elapsed:   {_fmt_age(r.elapsed_seconds)}")
    click.echo(f"heartbeat: {_fmt_age(r.age_seconds)} ago")
    if r.error:
        click.echo(f"error:     {r.error}")


@runs.command("reap")
@click.option("--yes", is_flag=True, help="Mark stale running records as 'stale'.")
@click.pass_context
def runs_reap(ctx: click.Context, yes: bool) -> None:
    """Find (and optionally mark) runs that stopped sending heartbeats."""
    _tracker, watchdog = _tracker_and_watchdog(ctx)
    stale = watchdog.scan()
    if not stale:
        click.echo(f"No stale runs (threshold: {int(watchdog.stale_after)}s without heartbeat).")
        return
    for r in stale:
        click.echo(f"  {r.task_id}  {r.done_roles}/{r.total_roles}  silent {_fmt_age(r.age_seconds)}")
    if yes:
        watchdog.reap()
        click.echo(f"Marked {len(stale)} run(s) as stale.")
    else:
        click.echo(f"\n{len(stale)} stale run(s). Re-run with --yes to mark them.")
