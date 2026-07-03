"""Core CLI commands: init, setup, run, serve, status, config."""

from __future__ import annotations

from pathlib import Path

import click

from codeops.config import create_default_config


@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing config")
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize VOLY in the current project."""
    cfg_path = Path.cwd() / "codeops.yaml"
    if cfg_path.exists() and not force:
        click.echo(f"Config already exists: {cfg_path}")
        click.echo("Use --force to overwrite")
        return

    create_default_config(cfg_path)
    click.echo(f"VOLY config created: {cfg_path}")

    from codeops.rtk.installer import RTKManager

    config = ctx.obj["config"]
    rtk_mgr = RTKManager(config.rtk.binary_path)

    try:
        click.echo("Installing RTK...")
        rtk_path = rtk_mgr.install()
        click.echo(f"  RTK installed: {rtk_path}")
    except Exception as e:
        click.echo(f"  RTK skipped: {e}")

    try:
        click.echo("Registering Claude Code hooks...")
        if rtk_mgr.register_hooks("claude"):
            click.echo("  Hooks registered")
    except Exception as e:
        click.echo(f"  Hooks skipped: {e}")

    click.echo("\nSetup complete. Edit codeops.yaml to configure models and agents.")
    click.echo("Run 'codeops setup' to start all components.")


@click.command()
@click.option("--rtk/--no-rtk", default=True, help="Enable/disable RTK")
@click.option("--headroom/--no-headroom", default=True, help="Enable/disable Headroom proxy")
@click.option("--a2a/--no-a2a", default=True, help="Enable/disable A2A orchestrator")
@click.option("--agui/--no-agui", default=False, help="Enable/disable AG-UI gateway")
@click.pass_context
def setup(ctx: click.Context, rtk: bool, headroom: bool, a2a: bool, agui: bool) -> None:
    """Set up all VOLY components."""
    config = ctx.obj["config"]

    if rtk and config.rtk.enabled:
        click.echo("[RTK] Setting up...")
        from codeops.rtk.installer import RTKManager

        rtk_mgr = RTKManager(config.rtk.binary_path)
        try:
            path = rtk_mgr.ensure_installed(auto_install=True)
            click.echo(f"  Binary: {path}")
            if rtk_mgr.register_hooks("claude"):
                click.echo("  Claude Code hooks: registered")
            stats = rtk_mgr.get_stats()
            if stats:
                saved = stats.get("summary", {}).get("total_saved", 0)
                click.echo(f"  Lifetime tokens saved: {saved}")
        except Exception as e:
            click.echo(f"  Error: {e}")

    if headroom and config.headroom.enabled:
        click.echo("[Headroom] Setting up...")
        from codeops.headroom.proxy import HeadroomManager

        hm = HeadroomManager(port=config.headroom.port)
        try:
            hm.start(wait=False)
            click.echo(f"  Proxy started on port {config.headroom.port}")
        except Exception as e:
            click.echo(f"  Error: {e}")

    if a2a and config.a2a.enabled:
        click.echo("[A2A] Checking federation and remote agents...")
        from codeops.a2a import create_a2a_orchestrator

        orch = create_a2a_orchestrator(config.a2a.federation_url)
        if config.a2a.federation_url:
            try:
                cards = orch.refresh_federation()
                click.echo(f"  Federation: {config.a2a.federation_url} ({len(cards)} agents)")
            except Exception as e:
                click.echo(f"  Federation: ✗ {e}")
        for url in config.a2a.remote_agents:
            card = orch.register_remote_agent(url)
            status = f"✓ {card.name}" if card else "✗ unreachable"
            click.echo(f"  {url}: {status}")

    click.echo("\nSetup complete.")
