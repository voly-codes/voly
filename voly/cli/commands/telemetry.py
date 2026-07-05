"""Telemetry CLI — pipeline status and test delivery."""
from __future__ import annotations

import click

from voly.telemetry import (
    TaskEvent,
    TokenMetrics,
    emit_event_from_config,
    event_to_pipeline_record,
    new_task_id,
    resolve_pipeline_endpoint,
    resolve_pipeline_token,
    send_to_pipeline,
    TelemetryDeliveryError,
)


@click.group()
def telemetry() -> None:
    """Task telemetry — local events, CF Pipelines, R2."""
    pass


@telemetry.command("status")
@click.pass_context
def telemetry_status(ctx: click.Context) -> None:
    """Show telemetry sinks configuration."""
    import os

    config = ctx.obj["config"]
    tel = config.telemetry
    endpoint = resolve_pipeline_endpoint(tel.pipeline_url)

    click.echo("Telemetry sinks")
    click.echo("=" * 40)
    click.echo(f"  Local events:  {tel.events_dir}/")
    click.echo(f"  Pipeline:      {'enabled' if tel.pipeline_enabled else 'disabled'}")
    click.echo(f"  Pipeline URL:  {endpoint or '(not configured)'}")
    click.echo(f"  Pipeline auth: {'yes' if resolve_pipeline_token() else 'no'}")
    click.echo(f"  R2 direct:     {'yes' if tel.r2_enabled and os.environ.get('CF_R2_ENDPOINT') else 'no'}")
    if os.environ.get("CF_PIPELINE_TELEMETRY_NAME"):
        click.echo(f"  Pipeline name: {os.environ['CF_PIPELINE_TELEMETRY_NAME']}")


@telemetry.command("errors")
@click.pass_context
def telemetry_errors(ctx: click.Context) -> None:
    """Failure breakdown by error class; unrecognized share = CLI drift (R4)."""
    from voly.telemetry import load_events, summarize_error_classes

    config = ctx.obj["config"]
    summary = summarize_error_classes(load_events(config.telemetry.events_dir))

    click.echo("Executor failures by error class")
    click.echo("=" * 40)
    click.echo(f"  Events total:  {summary['total_events']}")
    click.echo(f"  Failed:        {summary['failed']}")
    for name, count in sorted(summary["by_class"].items(), key=lambda kv: -kv[1]):
        click.echo(f"    {name:<16} {count}")
    share = summary["unrecognized_share"]
    click.echo(f"  Unrecognized share: {share:.1%}")
    if share > 0.2:
        click.echo("  ⚠ high unrecognized share — CLI output formats may have "
                   "drifted past the billing signal tables (see executors.md)")


@telemetry.command("test")
@click.option("--dry-run", is_flag=True, help="Build payload only, do not send")
@click.pass_context
def telemetry_test(ctx: click.Context, dry_run: bool) -> None:
    """Send a test TaskEvent to CF Pipelines."""
    config = ctx.obj["config"]
    tel = config.telemetry
    endpoint = resolve_pipeline_endpoint(tel.pipeline_url)

    if not endpoint:
        raise click.ClickException(
            "Pipeline URL not configured. Set telemetry.pipeline_url in voly.yaml "
            "or CF_PIPELINE_TELEMETRY_ENDPOINT in .env"
        )

    event = TaskEvent(
        task_id=new_task_id(),
        agent="telemetry-test",
        status="completed",
        tokens=TokenMetrics(input=1, output=1),
        cost_usd=0.0,
        duration_ms=1.0,
        model="test",
        provider="test",
        executor="cli",
    )

    if dry_run:
        click.echo(event_to_pipeline_record(event))
        return

    try:
        send_to_pipeline(
            endpoint,
            event,
            timeout=tel.pipeline_timeout_seconds,
        )
    except TelemetryDeliveryError as exc:
        raise click.ClickException(str(exc)) from exc

    path = emit_event_from_config(event, config)
    click.echo(f"Pipeline: OK ({endpoint})")
    if path:
        click.echo(f"Local:    {path}")
