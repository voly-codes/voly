"""CLI command: codeops config."""

from __future__ import annotations

import click


@click.command("config")
@click.option("--show", is_flag=True, help="Show current config")
@click.option("--path", is_flag=True, help="Show config file path")
@click.option("--export", "export_path", default=None, help="Export config to file")
@click.pass_context
def config_cmd(ctx: click.Context, show: bool, path: bool, export_path: str | None) -> None:
    """Show or export CodeOps configuration."""
    config = ctx.obj["config"]
    cfg_path = ctx.obj.get("config_path") or "codeops.yaml"

    if path:
        click.echo(cfg_path)
        return

    if export_path:
        import yaml

        with open(export_path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)
        click.echo(f"Config exported to: {export_path}")
        return

    if show or True:
        click.echo(f"Config: {cfg_path}")
        click.echo(f"Models: {list(config.models.keys()) if hasattr(config, 'models') else 'N/A'}")
        click.echo(f"RTK: {'enabled' if config.rtk.enabled else 'disabled'} ({config.rtk.binary_path})")
        click.echo(
            f"Headroom: {'enabled' if config.headroom.enabled else 'disabled'} "
            f"(port {config.headroom.port})"
        )
        fed = config.a2a.federation_url or "local"
        click.echo(
            f"A2A: {'enabled' if config.a2a.enabled else 'disabled'} "
            f"(federation: {fed}, remote: {len(config.a2a.remote_agents)})"
        )
        click.echo(f"AI Gateway: {'enabled' if config.ai_gateway.enabled else 'disabled'}")
