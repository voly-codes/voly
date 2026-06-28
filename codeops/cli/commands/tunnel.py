"""CLI: codeops tunnel — cloudflared quick tunnel + worker secrets."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import click

from codeops.tunnel_util import (
    ensure_pipeline_token,
    find_cloudflared,
    install_cloudflared,
    run_pipeline_server_background,
    start_cloudflared_tunnel,
    sync_agent_worker_secrets,
    update_env_pipeline_url,
    wait_for_local_server,
)


def _codeops_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _env_path() -> Path:
    return _codeops_root() / ".env"


def _agent_worker_dir() -> Path:
    return _codeops_root() / "cf-workers/agent"


@click.group()
def tunnel() -> None:
    """Manage cloudflared tunnel for CF agent workers."""
    pass


@tunnel.command("setup")
@click.option("--install-cloudflared", is_flag=True, help="Download cloudflared to ~/.local/bin")
@click.pass_context
def tunnel_setup(ctx: click.Context, install_cloudflared: bool) -> None:
    """Generate PIPELINE_RUNNER_TOKEN and sync secrets to codeops-agent worker."""
    env_path = _env_path()
    token = ensure_pipeline_token(env_path)
    click.echo(f"PIPELINE_RUNNER_TOKEN: set in {env_path}")

    cf_bin = find_cloudflared()
    if not cf_bin and install_cloudflared:
        click.echo("Installing cloudflared...")
        cf_bin = install_cloudflared()
        click.echo(f"  Installed: {cf_bin}")
    elif cf_bin:
        click.echo(f"cloudflared: {cf_bin}")
    else:
        click.echo("cloudflared: not found (run with --install-cloudflared)")

    existing_url = os.environ.get("PIPELINE_RUNNER_URL", "").strip()
    if not existing_url and env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("PIPELINE_RUNNER_URL="):
                existing_url = line.split("=", 1)[1].strip()

    if existing_url:
        click.echo(f"PIPELINE_RUNNER_URL: {existing_url}")
        _sync_secrets(existing_url, token)
        click.echo("Worker secrets synced.")
    else:
        click.echo("PIPELINE_RUNNER_URL not set yet — run: codeops tunnel start")


@tunnel.command("start")
@click.option("--host", default="127.0.0.1")
@click.option("--port", "-p", default=9202)
@click.option(
    "--cwd",
    default="/home/user1/smarty/smarty-crm-next",
    show_default=True,
    help="Default working directory for pipeline tasks",
)
@click.option("--no-sync", is_flag=True, help="Skip wrangler secret sync")
@click.pass_context
def tunnel_start(ctx: click.Context, host: str, port: int, cwd: str, no_sync: bool) -> None:
    """Start pipeline server + cloudflared quick tunnel, sync worker secrets."""
    config = ctx.obj["config"]
    env_path = _env_path()

    cf_bin = find_cloudflared()
    if not cf_bin:
        click.echo("cloudflared not found — installing to ~/.local/bin ...")
        cf_bin = install_cloudflared()

    token = ensure_pipeline_token(env_path)
    local_url = f"http://{host}:{port}"

    click.echo(f"Starting pipeline server on {local_url} ...")
    run_pipeline_server_background(config, host, port, cwd)

    if not wait_for_local_server(host, port):
        click.echo("Pipeline server failed to start", err=True)
        raise SystemExit(1)
    click.echo("Pipeline server: OK")

    click.echo("Starting cloudflared quick tunnel ...")
    tunnel_url: str | None = None

    def on_url(url: str) -> None:
        nonlocal tunnel_url
        tunnel_url = url

    proc = start_cloudflared_tunnel(cf_bin, local_url, on_url=on_url)
    if not tunnel_url:
        click.echo("Failed to obtain tunnel URL", err=True)
        raise SystemExit(1)

    update_env_pipeline_url(env_path, tunnel_url)
    click.echo(f"Tunnel URL: {tunnel_url}")
    click.echo(f"Saved to {env_path} as PIPELINE_RUNNER_URL")

    if not no_sync:
        click.echo("Syncing secrets to codeops-agent worker ...")
        try:
            _sync_secrets(tunnel_url, token)
            click.echo("Worker secrets synced.")
        except Exception as exc:
            click.echo(f"Secret sync failed: {exc}", err=True)
            click.echo("Run manually after tunnel is up:")
            click.echo(f"  cd cf-workers/agent && wrangler secret put PIPELINE_RUNNER_URL")
            click.echo(f"  cd cf-workers/agent && wrangler secret put PIPELINE_RUNNER_TOKEN")

    click.echo("")
    click.echo("Ready. CF agents can now call your local pipeline.")
    click.echo("Test: codeops a2a call developer 'health check' --remote")
    click.echo("Press Ctrl+C to stop tunnel and server.")

    def _shutdown(signum: int, frame: object) -> None:
        click.echo("\nStopping tunnel ...")
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        proc.terminate()


def _sync_secrets(pipeline_url: str, pipeline_token: str) -> None:
    agent_dir = _agent_worker_dir()
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not cf_token and _env_path().is_file():
        for line in _env_path().read_text().splitlines():
            if line.startswith("CLOUDFLARE_API_TOKEN="):
                cf_token = line.split("=", 1)[1].strip()
    sync_agent_worker_secrets(agent_dir, pipeline_url, pipeline_token, cf_token)
