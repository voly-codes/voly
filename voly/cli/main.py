"""
VOLY CLI entry point.

Subcommands live in voly.cli.commands.*
"""

from __future__ import annotations

import logging
import sys

import click

if sys.platform == "win32":
    # Windows consoles default stdout/stderr to the OS locale codepage
    # (e.g. cp1251), not UTF-8. Every CLI command that prints Cyrillic task
    # text or agent output (review reports, multi-agent summaries, error
    # messages) would otherwise come out as mojibake or raise
    # UnicodeEncodeError outright — see docs/backend/executors.md for the
    # matching subprocess-capture fix.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

from voly.capability.sync import startup_sync
from voly.cli.commands import (
    a2a,
    agui,
    ai_gateway,
    balance,
    capability_cmd,
    catalog,
    cloud,
    compare,
    config_cmd,
    dspy_cmd,
    headroom,
    init,
    match_task,
    mcp,
    memory,
    model,
    plan_cmd,
    pxpipe,
    registry,
    repo_cmd,
    reuse_cmd,
    rtk,
    run,
    runner,
    runs,
    savings,
    scan_project,
    serve,
    setup,
    skill,
    spend,
    status,
    telemetry,
    tunnel,
    ui,
    workflow_cmd,
)
from voly.config import load_config


@click.group()
@click.version_option(version="0.1.0", prog_name="VOLY")
@click.option("--config", "-c", default=None, help="Path to voly.yaml")
@click.option("-v", "--verbose", is_flag=True, help="DEBUG logs for all voly.* loggers")
@click.pass_context
def main(ctx: click.Context, config: str | None, verbose: bool) -> None:
    # Surface [PIPELINE:SETUP] / [PIPELINE:A2A] on every CLI run (see docs/post-run-checklist.md).
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logging.getLogger("voly.pipeline").setLevel(logging.INFO)
    logging.getLogger("voly.a2a").setLevel(logging.INFO)
    if verbose:
        logging.getLogger("voly").setLevel(logging.DEBUG)
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    cfg = load_config(config)
    ctx.obj["config"] = cfg
    if cfg.capability.worker_url:
        startup_sync(cfg.capability.worker_url)


# Platform & infra groups
main.add_command(a2a)
main.add_command(agui)
main.add_command(memory)
main.add_command(rtk)
main.add_command(headroom)
main.add_command(pxpipe)
main.add_command(mcp)
main.add_command(registry)
main.add_command(skill)
main.add_command(runner)
main.add_command(telemetry)
main.add_command(runs)
main.add_command(model)
main.add_command(ai_gateway, name="ai-gateway")
main.add_command(scan_project)
main.add_command(match_task)
main.add_command(compare)
main.add_command(savings)
main.add_command(balance)
main.add_command(tunnel)
main.add_command(spend)
main.add_command(catalog)
main.add_command(cloud)
main.add_command(dspy_cmd, name="dspy")
main.add_command(plan_cmd)
main.add_command(reuse_cmd)
main.add_command(repo_cmd)
main.add_command(capability_cmd)
main.add_command(workflow_cmd)

# Core commands
main.add_command(init)
main.add_command(setup)
main.add_command(serve)
main.add_command(ui)
main.add_command(run)
main.add_command(status)
main.add_command(config_cmd)


if __name__ == "__main__":
    main()
