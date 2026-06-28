"""
CodeOps CLI entry point.

Subcommands live in codeops.cli.commands.*
"""

from __future__ import annotations

import click

from codeops.config import load_config
from codeops.cli.commands import (
    a2a,
    agui,
    memory,
    rtk,
    headroom,
    mcp,
    workflow,
    registry,
    model,
    ai_gateway,
    scan_project,
    match_task,
    skill,
    runner,
    telemetry,
    compare,
    savings,
    balance,
    init,
    setup,
    serve,
    run,
    status,
    config_cmd,
    tunnel,
    spend,
    catalog,
    dspy_cmd,
)


@click.group()
@click.version_option(version="0.1.0", prog_name="CodeOps")
@click.option("--config", "-c", default=None, help="Path to codeops.yaml")
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["config"] = load_config(config)


# Platform & infra groups
main.add_command(a2a)
main.add_command(agui)
main.add_command(memory)
main.add_command(rtk)
main.add_command(headroom)
main.add_command(mcp)
main.add_command(workflow)
main.add_command(registry)
main.add_command(skill)
main.add_command(runner)
main.add_command(telemetry)
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
main.add_command(dspy_cmd, name="dspy")

# Core commands
main.add_command(init)
main.add_command(setup)
main.add_command(serve)
main.add_command(run)
main.add_command(status)
main.add_command(config_cmd)


if __name__ == "__main__":
    main()
