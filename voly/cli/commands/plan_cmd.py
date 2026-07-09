"""CLI: voly plan — run / list / show gated multi-step plans (Rung B PR3)."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.group("plan")
def plan_cmd() -> None:
    """Plan state machine: run YAML/JSON plans with acceptance gates."""
    pass


def _store(ctx: click.Context):
    from voly.plan.store import PlanStore

    config = ctx.obj["config"]
    plans_dir = getattr(config.plan, "store_dir", ".voly/plans")
    return PlanStore(plans_dir)


@plan_cmd.command("run")
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--cwd", default=None, help="Target project path (overrides plan.cwd)")
@click.option(
    "--mode",
    type=click.Choice(["shadow", "active", "off"], case_sensitive=False),
    default=None,
    help="Override plan.mode from config (shadow|active)",
)
@click.option("--json-out", "json_out", is_flag=True, help="Print result summary as JSON")
@click.pass_context
def plan_run(
    ctx: click.Context,
    plan_file: str,
    cwd: str | None,
    mode: str | None,
    json_out: bool,
) -> None:
    """Load a plan file and execute steps with dependency + verify gates."""
    from voly.plan.loader import load_plan_file
    from voly.plan.runner import PlanRunner

    config = ctx.obj["config"]
    default_cwd = cwd or getattr(config, "default_cwd", "") or ""
    try:
        plan = load_plan_file(plan_file, default_cwd=default_cwd)
    except Exception as exc:
        click.echo(f"Failed to load plan: {exc}", err=True)
        raise SystemExit(2) from exc

    runner = PlanRunner(config)
    result = runner.run(plan, mode=mode, cwd=cwd)

    if json_out:
        click.echo(json.dumps(result.summary, ensure_ascii=False, indent=2))
    else:
        click.echo(f"plan_id:  {result.plan.plan_id}")
        click.echo(f"status:   {result.plan.status}")
        click.echo(f"task_id:  {result.task_id}")
        click.echo(f"duration: {result.duration_ms:.0f}ms")
        for s in result.plan.steps:
            mark = {
                "verified": "✓",
                "failed": "✗",
                "skipped": "·",
                "pending": " ",
            }.get(s.status, "?")
            click.echo(f"  [{mark}] {s.id:<16} {s.status:<10} {s.role}/{s.mode}")
            if s.error:
                click.echo(f"       error: {s.error[:160]}")
        if result.error:
            click.echo(f"error:    {result.error}")

    raise SystemExit(0 if result.success else 1)


@plan_cmd.command("list")
@click.option("--status", default=None, help="Filter by plan status")
@click.pass_context
def plan_list(ctx: click.Context, status: str | None) -> None:
    """List stored plans (newest first)."""
    store = _store(ctx)
    plans = store.list()
    if not plans:
        click.echo("No plans in store.")
        return
    click.echo(f"{'PLAN_ID':<28} {'STATUS':<12} {'STEPS':<8} TASK")
    for p in plans:
        if status and p.status != status:
            continue
        done = sum(1 for s in p.steps if s.status == "verified")
        total = len(p.steps)
        task = (p.task or "")[:40]
        click.echo(f"{p.plan_id:<28} {p.status:<12} {done}/{total:<6} {task}")


@plan_cmd.command("show")
@click.argument("plan_id")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def plan_show(ctx: click.Context, plan_id: str, json_out: bool) -> None:
    """Show a stored plan in detail."""
    from voly.plan.loader import plan_summary

    store = _store(ctx)
    plan = store.load(plan_id)
    if plan is None:
        click.echo(f"No plan {plan_id!r}", err=True)
        raise SystemExit(1)
    if json_out:
        click.echo(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"plan_id:  {plan.plan_id}")
    click.echo(f"status:   {plan.status}")
    click.echo(f"task_id:  {plan.task_id}")
    click.echo(f"cwd:      {plan.cwd or '—'}")
    click.echo(f"task:     {(plan.task or '—')[:200]}")
    if plan.error:
        click.echo(f"error:    {plan.error}")
    click.echo("steps:")
    for s in plan.steps:
        click.echo(
            f"  - {s.id}: status={s.status} role={s.role} mode={s.mode} "
            f"deps={s.depends_on or []}"
        )
        if s.acceptance:
            types = ", ".join(a.type for a in s.acceptance)
            click.echo(f"      acceptance: {types}")
        if s.verify_log:
            for v in s.verify_log:
                flag = "ok" if v.get("ok") else "FAIL"
                click.echo(f"      verify[{flag}] {v.get('type')}: {v.get('message', '')[:100]}")
        if s.error:
            click.echo(f"      error: {s.error[:160]}")


@plan_cmd.command("status")
@click.argument("plan_id")
@click.pass_context
def plan_status(ctx: click.Context, plan_id: str) -> None:
    """Short status line for a stored plan."""
    from voly.plan.loader import plan_summary

    store = _store(ctx)
    plan = store.load(plan_id)
    if plan is None:
        click.echo(f"No plan {plan_id!r}", err=True)
        raise SystemExit(1)
    s = plan_summary(plan)
    click.echo(
        f"{plan.plan_id}  {plan.status}  "
        f"verified={s['verified']}/{s['total']} failed={s['failed']}"
    )


@plan_cmd.command("validate")
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def plan_validate(ctx: click.Context, plan_file: str) -> None:
    """Validate plan structure without executing."""
    from voly.plan.engine import PlanEngine
    from voly.plan.loader import load_plan_file

    config = ctx.obj["config"]
    try:
        plan = load_plan_file(plan_file, default_cwd=getattr(config, "default_cwd", "") or "")
        engine = PlanEngine()
        engine.validate(plan)
        order = engine.topo_order(plan)
    except Exception as exc:
        click.echo(f"invalid: {exc}", err=True)
        raise SystemExit(1) from exc
    click.echo(f"ok: {plan.plan_id}  steps={len(plan.steps)}  order={order}")
