"""CLI command: voly serve — pipeline HTTP server."""

from __future__ import annotations

import click


@click.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", "-p", default=9202, help="HTTP port")
@click.option("--cwd", default=None, help="Default working directory for tasks")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, cwd: str | None) -> None:
    """Start pipeline HTTP server (for CF agent workers via tunnel)."""
    from voly.pipeline_server import run_pipeline_server

    config = ctx.obj["config"]
    click.echo(f"Pipeline server: http://{host}:{port}")
    click.echo("Secrets and git repo stay on this machine.")
    click.echo("")
    click.echo("Expose to Cloudflare:")
    click.echo(f"  voly tunnel start")
    click.echo(f"  # or: cloudflared tunnel --url http://{host}:{port}")
    click.echo("")
    click.echo("Press Ctrl+C to stop")

    try:
        run_pipeline_server(
            config,
            host=host,
            port=port,
            default_cwd=cwd or "",
        )
    except KeyboardInterrupt:
        click.echo("\nServer stopped")
