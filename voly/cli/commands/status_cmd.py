"""CLI command: voly status."""

from __future__ import annotations

import click


@click.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show status of all VOLY components."""
    from voly.pipeline import Pipeline
    from voly.telemetry import resolve_pipeline_endpoint

    config = ctx.obj["config"]
    pipeline = Pipeline(config)
    pipeline.setup_environment()

    click.echo("VOLY Status")
    click.echo("=" * 40)

    click.echo("\n[RTK]")
    if pipeline.rtk.is_installed():
        click.echo(f"  Installed: {pipeline.rtk.binary_path}")
        stats = pipeline.rtk.get_stats()
        if stats:
            summary = stats.get("summary", {})
            click.echo(f"  Tokens saved: {summary.get('total_saved', 0)}")
            click.echo(f"  Savings rate: {summary.get('avg_savings_pct', 0):.1f}%")
    else:
        click.echo("  Not installed")

    click.echo("\n[Headroom]")
    if pipeline.headroom_mgr:
        hstatus = pipeline.headroom_mgr.status()
        click.echo(f"  Proxy: {'running' if hstatus.running else 'stopped'}")
        click.echo(f"  Port: {hstatus.port}")
        click.echo(f"  Tokens saved: {hstatus.tokens_saved}")
    else:
        click.echo("  Not configured")

    click.echo("\n[Telemetry]")
    tel = config.telemetry
    endpoint = resolve_pipeline_endpoint(tel.pipeline_url)
    click.echo(f"  Local:    {tel.events_dir}/")
    click.echo(f"  Pipeline: {endpoint or 'not configured'}")

    click.echo("\n[Memory]")
    mem_count = pipeline.memory.count()
    remote = config.memory.remote_url or "local only"
    click.echo(f"  Entries: {mem_count}")
    click.echo(f"  DB: {pipeline.memory.db_path}")
    click.echo(f"  Remote: {remote}")

    click.echo("\n[Tunnel]")
    import os

    pipeline_url = os.environ.get("PIPELINE_RUNNER_URL", "")
    token_set = bool(os.environ.get("PIPELINE_RUNNER_TOKEN", ""))
    click.echo(f"  PIPELINE_RUNNER_URL: {pipeline_url or 'not set'}")
    click.echo(f"  PIPELINE_RUNNER_TOKEN: {'set' if token_set else 'not set'}")
    click.echo(f"  Agent worker: {os.environ.get('CF_WORKER_AGENT_URL', 'not set')}")
    spend_url = config.spend.remote_url or "not set"
    click.echo(f"  Spend worker: {spend_url}")

    click.echo("\n[Metrics]")
    click.echo(f"  Total tasks: {pipeline.metrics.total_tasks}")
    click.echo(f"  Total tokens in: {pipeline.metrics.total_tokens_in}")
    click.echo(f"  Avg duration: {pipeline.metrics.avg_duration_ms:.0f}ms")

    click.echo("\n[Environment]")
    from voly.environment import collect_environment_report

    report = collect_environment_report(config)
    click.echo(f"  Ready: {'yes' if report.ready else 'no'} — {report.summary}")
    for check in report.checks:
        if check.group == "providers" and check.id.startswith("provider:"):
            continue  # summary row is enough
        if check.group == "executors" and check.id.startswith("executor:"):
            mark = {"ok": "✓", "warn": "!", "error": "✗", "skip": "·"}.get(check.status, "?")
            click.echo(f"  [{mark}] {check.label}: {check.detail}")
            continue
        if check.id in ("providers", "executors", "cwd", "cloud", "runtime"):
            mark = {"ok": "✓", "warn": "!", "error": "✗", "skip": "·"}.get(check.status, "?")
            click.echo(f"  [{mark}] {check.label}: {check.detail}")
            if check.hint and check.status in ("warn", "error"):
                click.echo(f"      → {check.hint}")

    pipeline.shutdown()
