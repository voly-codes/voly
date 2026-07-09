"""
2GC CloudBridge — VOLY plugin for MTS B2B Store missions.

Register locally:
    from voly.cli.main import main
    from projects.twogc.cli_commands import twogc
    main.add_command(twogc)

Or:
    python -m projects.twogc
"""
from __future__ import annotations

import click

from voly.cli.main import main
from projects.twogc.cli_commands import twogc

main.add_command(twogc)


def main_cli() -> None:
    main()


if __name__ == "__main__":
    main_cli()
