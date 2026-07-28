"""CLI commands for inspecting local evidence and recording human feedback."""

from __future__ import annotations

import json
from pathlib import Path

import click

from voly.evidence.store import VALID_HUMAN_FEEDBACK, EvidenceStore


def _store(ctx: click.Context, store_dir: str | None) -> EvidenceStore:
    configured = ctx.obj["config"].evidence.store_dir
    return EvidenceStore(Path(store_dir or configured))


@click.group("evidence")
def evidence_cmd() -> None:
    """Inspect local EvidenceRecord files and add explicit feedback."""


@evidence_cmd.command("show")
@click.argument("task_id")
@click.option("--store-dir", type=click.Path(file_okay=False), default=None)
@click.pass_context
def evidence_show(
    ctx: click.Context,
    task_id: str,
    store_dir: str | None,
) -> None:
    """Print one local EvidenceRecord as JSON."""
    try:
        record = _store(ctx, store_dir).load(task_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if record is None:
        raise click.ClickException(f"evidence record not found: {task_id}")
    click.echo(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))


@evidence_cmd.command("feedback")
@click.argument("task_id")
@click.argument(
    "kind",
    type=click.Choice(sorted(VALID_HUMAN_FEEDBACK), case_sensitive=False),
)
@click.option("--comment", default="", help="Optional local-only feedback note.")
@click.option("--store-dir", type=click.Path(file_okay=False), default=None)
@click.pass_context
def evidence_feedback(
    ctx: click.Context,
    task_id: str,
    kind: str,
    comment: str,
    store_dir: str | None,
) -> None:
    """Append explicit human feedback to an existing EvidenceRecord."""
    try:
        record = _store(ctx, store_dir).add_human_feedback(
            task_id,
            kind,
            source="cli",
            comment=comment,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "task_id": record.task_id,
                "feedback": record.human_feedback[-1].__dict__,
            },
            ensure_ascii=False,
        )
    )
