"""CLI for versioned golden datasets and offline regression replay."""

from __future__ import annotations

import json
from pathlib import Path

import click

from voly.evaluation.golden import (
    GoldenDatasetError,
    load_golden_dataset,
    run_golden_dataset,
    save_golden_report,
)


@click.group("eval")
def eval_cmd() -> None:
    """Validate and replay deterministic golden datasets offline."""


@eval_cmd.command("validate")
@click.argument("dataset", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def eval_validate(dataset: Path) -> None:
    """Validate a versioned golden dataset and all referenced fixtures."""
    try:
        loaded = load_golden_dataset(dataset)
    except GoldenDatasetError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "valid": True,
                "dataset_id": loaded.dataset_id,
                "version": loaded.version,
                "fingerprint_sha256": loaded.fingerprint,
                "case_count": len(loaded.cases),
            },
            ensure_ascii=False,
        )
    )


@eval_cmd.command("run")
@click.argument("dataset", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--case",
    "case_ids",
    multiple=True,
    help="Replay only this case ID; may be repeated.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Report path (default: .voly/eval-runs/<dataset>-<version>.json).",
)
def eval_run(dataset: Path, case_ids: tuple[str, ...], output: Path | None) -> None:
    """Replay a golden dataset in isolated temporary workspaces."""
    try:
        loaded = load_golden_dataset(dataset)
        report = run_golden_dataset(
            loaded,
            case_ids=set(case_ids) if case_ids else None,
        )
        report_path = output or Path(".voly/eval-runs") / (
            f"{loaded.dataset_id}-{loaded.version}.json"
        )
        save_golden_report(report, report_path)
    except GoldenDatasetError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "dataset_id": loaded.dataset_id,
                "version": loaded.version,
                **report["summary"],
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    if report["summary"]["failed"]:
        raise click.exceptions.Exit(1)
