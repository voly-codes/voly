"""CLI: voly repo — repository intelligence (Phase 1: admission inspect)."""

from __future__ import annotations

import dataclasses
import json

import click


@click.group("repo")
def repo_cmd() -> None:
    """Pre-run analysis of external repositories."""
    pass


@repo_cmd.command("inspect")
@click.argument("url")
def repo_inspect(url: str) -> None:
    """Pre-clone admission check only. Prints AdmissionResult as JSON."""
    from voly.intelligence.admission import AdmissionConfig, check

    result = check(url, AdmissionConfig())
    click.echo(json.dumps(dataclasses.asdict(result), indent=2))
