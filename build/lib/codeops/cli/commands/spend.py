"""CLI: codeops spend — persistent spend tracking."""

from __future__ import annotations

import click


@click.group()
def spend() -> None:
    """Persistent spend tracking (CF Durable Objects)."""
    pass


@spend.command("status")
@click.pass_context
def spend_status(ctx: click.Context) -> None:
    """Show spend worker status."""
    from codeops.spend.client import create_spend_client, resolve_spend_url

    config = ctx.obj["config"]
    url = resolve_spend_url(config.spend.remote_url)
    if not url:
        click.echo("Spend worker URL not configured (CF_WORKER_SPEND_URL).")
        raise SystemExit(1)

    client = create_spend_client(url)
    if not client:
        raise SystemExit(1)

    try:
        health = client.health()
        summary = client.summary(days=1)
    except Exception as exc:
        click.echo(f"Spend worker unreachable: {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(f"Spend worker: {url}")
    click.echo(f"Status: {health.get('status', 'unknown')}")
    click.echo(f"Today total: ${summary.get('total', 0):.4f}")
    click.echo(f"Daily budget: ${config.spend.daily_budget_usd:.2f}")


@spend.command("summary")
@click.option("--days", "-d", default=1, help="Lookback days")
@click.pass_context
def spend_summary(ctx: click.Context, days: int) -> None:
    """Show spend summary by agent."""
    from codeops.spend.client import create_spend_client, resolve_spend_url

    config = ctx.obj["config"]
    url = resolve_spend_url(config.spend.remote_url)
    client = create_spend_client(url)
    if not client:
        click.echo("Spend worker not configured.", err=True)
        raise SystemExit(1)

    data = client.summary(days=days)
    click.echo(f"Spend last {days} day(s): ${data.get('total', 0):.4f}")
    for row in data.get("agents", []):
        click.echo(
            f"  {row['agent']:<16} ${row['spent']:.4f}  ({row['tasks']} tasks)"
        )


@spend.command("recent")
@click.option("--limit", "-n", default=10)
@click.pass_context
def spend_recent(ctx: click.Context, limit: int) -> None:
    """Show recent spend entries."""
    from codeops.spend.client import create_spend_client, resolve_spend_url

    config = ctx.obj["config"]
    client = create_spend_client(resolve_spend_url(config.spend.remote_url))
    if not client:
        click.echo("Spend worker not configured.", err=True)
        raise SystemExit(1)

    for row in client.recent(limit=limit):
        click.echo(
            f"{row.get('agent', '?')}: ${row.get('cost_usd', 0):.4f} "
            f"task={row.get('task_id', '')[:8]} model={row.get('model', '')}"
        )
