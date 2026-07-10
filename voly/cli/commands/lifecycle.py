"""Core CLI commands: init, setup, run, serve, status, config."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from voly.config import create_default_config

# Official hosted catalog/marketplace workers (opt-in via `voly setup` or
# .env.example — never enabled silently; self-deploy from cf-workers/ instead).
OFFICIAL_CATALOG_URL = "https://voly-catalog.margolanies.workers.dev"
OFFICIAL_MARKETPLACE_URL = "https://voly-marketplace.margolanies.workers.dev"


def _offer_official_catalog(env_path: Path | None = None) -> bool:
    """Opt-in prompt: write hosted catalog/marketplace URLs into .env.

    Returns True when something was written. Skips silently when the vars are
    already set, or stdin is not a TTY (CI / scripted runs must not block).
    """
    if os.environ.get("CF_WORKER_CATALOG_URL") and os.environ.get("CF_WORKER_MARKETPLACE_URL"):
        return False
    if not sys.stdin.isatty():
        return False
    if not click.confirm(
        "\nUse the official hosted VOLY catalog & marketplace?\n"
        f"  (catalog/skill queries will go to {OFFICIAL_CATALOG_URL})",
        default=False,
    ):
        return False

    path = env_path or (Path.cwd() / ".env")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = []
    if "CF_WORKER_CATALOG_URL" not in existing:
        lines.append(f"CF_WORKER_CATALOG_URL={OFFICIAL_CATALOG_URL}")
    if "CF_WORKER_MARKETPLACE_URL" not in existing:
        lines.append(f"CF_WORKER_MARKETPLACE_URL={OFFICIAL_MARKETPLACE_URL}")
    if not lines:
        return False
    with path.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("# Official hosted VOLY catalog/marketplace (added by `voly setup`)\n")
        f.write("\n".join(lines) + "\n")
    click.echo(f"  Catalog URLs written to {path}")
    return True


@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing config")
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize VOLY in the current project."""
    cfg_path = Path.cwd() / "voly.yaml"
    if cfg_path.exists() and not force:
        click.echo(f"Config already exists: {cfg_path}")
        click.echo("Use --force to overwrite")
        return

    create_default_config(cfg_path)
    click.echo(f"VOLY config created: {cfg_path}")

    from voly.rtk.installer import RTKManager

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

    click.echo("\nSetup complete. Edit voly.yaml to configure models and agents.")
    click.echo("Run 'voly setup' to start all components.")


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
        from voly.rtk.installer import RTKManager

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
        from voly.headroom.proxy import HeadroomManager

        hm = HeadroomManager(port=config.headroom.port)
        try:
            hm.start(wait=False)
            click.echo(f"  Proxy started on port {config.headroom.port}")
        except Exception as e:
            click.echo(f"  Error: {e}")

    if a2a and config.a2a.enabled:
        click.echo("[A2A] Checking federation and remote agents...")
        from voly.a2a import create_a2a_orchestrator

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

    _offer_official_catalog()

    click.echo("\nSetup complete.")
