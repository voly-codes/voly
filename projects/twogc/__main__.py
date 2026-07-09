"""Entry: python -m projects.twogc combat list"""
from __future__ import annotations

import click

from voly.cli.main import main as voly_main
from projects.twogc.cli_commands import twogc

voly_main.add_command(twogc)

if __name__ == "__main__":
    voly_main()
