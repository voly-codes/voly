"""CLI command: codeops ui — start the VOLY web dashboard."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import click


@click.command("ui")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host")
@click.option("--port", "-p", default=7788, show_default=True, help="HTTP port")
@click.option("--events-dir", default=None, help="Path to .codeops/events/ directory")
@click.option("--dev", is_flag=True, help="Start Vite dev server instead of production build")
@click.option("--build", "do_build", is_flag=True, help="Build the Svelte app before serving")
@click.option("--reload", "hot_reload", is_flag=True, help="Auto-reload server on code changes (dev)")
@click.pass_context
def ui(
    ctx: click.Context,
    host: str,
    port: int,
    events_dir: str | None,
    dev: bool,
    do_build: bool,
    hot_reload: bool,
) -> None:
    """Start VOLY web dashboard (FastAPI + Svelte UI).

    Production: codeops ui
    Development: codeops ui --dev  (requires Node.js + npm)
    """
    try:
        import uvicorn
    except ImportError:
        click.echo("Missing dependencies. Install with:", err=True)
        click.echo("  pip install 'codeops[ui]'", err=True)
        sys.exit(1)

    ui_dir = pathlib.Path(__file__).parents[3] / "ui"
    static_dir = pathlib.Path(__file__).parents[2] / "web" / "static"

    if do_build:
        if not ui_dir.exists():
            click.echo(f"UI source not found at {ui_dir}", err=True)
            sys.exit(1)
        click.echo("Building Svelte UI…")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=ui_dir,
            check=False,
        )
        if result.returncode != 0:
            click.echo("Build failed.", err=True)
            sys.exit(1)
        click.echo("Build done.")

    if dev:
        _start_dev(ui_dir, port)
        return

    if not static_dir.exists():
        click.echo(
            "Svelte app not built yet. Run:\n"
            "  cd ui && npm install && npm run build\n"
            "Or use --build flag: codeops ui --build\n"
            "Or run in dev mode: codeops ui --dev",
            err=True,
        )
        sys.exit(1)

    ev_path = pathlib.Path(events_dir) if events_dir else None
    config = ctx.obj.get("config") if ctx.obj else None

    from codeops.web.server import create_app

    app = create_app(events_dir=ev_path, config=config)
    click.echo(f"VOLY UI: http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")

    if hot_reload:
        uvicorn.run(
            "codeops.web.server:_dev_app",
            host=host, port=port, log_level="info", reload=True,
            reload_dirs=[str(pathlib.Path(__file__).parents[2])],
        )
    else:
        uvicorn.run(app, host=host, port=port, log_level="warning")


def _start_dev(ui_dir: pathlib.Path, api_port: int) -> None:
    import os

    if not ui_dir.exists():
        click.echo(f"UI source not found at {ui_dir}", err=True)
        sys.exit(1)

    node_modules = ui_dir / "node_modules"
    if not node_modules.exists():
        click.echo("Installing npm dependencies…")
        subprocess.run(["npm", "install"], cwd=ui_dir, check=True)

    env = os.environ.copy()
    env["CODEOPS_UI_API_PORT"] = str(api_port)

    click.echo(f"Vite dev server: http://127.0.0.1:5173")
    click.echo(f"API proxy target: http://127.0.0.1:{api_port}")
    click.echo("Press Ctrl+C to stop")

    subprocess.run(["npm", "run", "dev"], cwd=ui_dir, env=env)
