"""CLI for persisted business Decisions backed by PlanStore."""

from __future__ import annotations

import click


@click.group("decide")
def decide_cmd() -> None:
    """List, approve, or reject pending business Decisions."""


def _service(ctx: click.Context):
    from voly.decisions import DecisionService
    from voly.plan.store import PlanStore

    return DecisionService(PlanStore(ctx.obj["config"].plan.store_dir))


@decide_cmd.command("list")
@click.pass_context
def decide_list(ctx: click.Context) -> None:
    plans = _service(ctx).list()
    if not plans:
        click.echo("No business decisions in store.")
        return
    click.echo(f"{'PLAN_ID':<28} {'DECISION':<10} {'URGENCY':<8} TITLE")
    for plan in plans:
        meta = plan.metadata
        click.echo(f"{plan.plan_id:<28} {meta.get('decision', 'pending'):<10} {meta.get('urgency', ''):<8} {plan.task[:60]}")


def _record(ctx: click.Context, plan_id: str, decision: str, comment: str) -> None:
    from voly.decisions import DecisionConflictError

    try:
        result = _service(ctx).decide(plan_id, decision, comment=comment)
    except FileNotFoundError as exc:
        raise click.ClickException("decision not found") from exc
    except DecisionConflictError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{plan_id}: {result.decision}{'' if result.changed else ' (unchanged)'}")


@decide_cmd.command("approve")
@click.argument("plan_id")
@click.option("--comment", default="")
@click.pass_context
def decide_approve(ctx: click.Context, plan_id: str, comment: str) -> None:
    _record(ctx, plan_id, "approve", comment)


@decide_cmd.command("reject")
@click.argument("plan_id")
@click.option("--comment", default="")
@click.pass_context
def decide_reject(ctx: click.Context, plan_id: str, comment: str) -> None:
    _record(ctx, plan_id, "reject", comment)
