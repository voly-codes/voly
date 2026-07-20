"""CLI: voly repo — repository intelligence."""

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


def _clone_path(url: str, *, allow_private: bool) -> str:
    from voly.intelligence.admission import AdmissionConfig
    from voly.intelligence.repo_analyzer import AnalyzeConfig, clone_repository

    cfg = AnalyzeConfig(admission=AdmissionConfig(allow_private=allow_private))
    try:
        return clone_repository(url, cfg)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@repo_cmd.command("analyze")
@click.argument("url")
@click.option("--for", "task_context", default="", help="Task context for AI mapper")
@click.option("--allow-private", is_flag=True)
@click.option("--refresh", is_flag=True, help="Force re-analysis even if cached")
def repo_analyze(url: str, task_context: str, allow_private: bool, refresh: bool) -> None:
    """Full repository intelligence analysis."""
    from voly.intelligence.admission import AdmissionConfig
    from voly.intelligence.repo_analyzer import AnalyzeConfig, analyze

    cfg = AnalyzeConfig(
        admission=AdmissionConfig(allow_private=allow_private),
        use_ai_mapper=bool(task_context),
        refresh=refresh,
    )
    report = analyze(url, cfg)
    click.echo(report.to_json())


@repo_cmd.command("map")
@click.argument("url")
def repo_map(url: str) -> None:
    """Architecture map only (admission + clone + heuristics)."""
    from voly.intelligence.architecture_mapper import map_architecture

    clone_path = _clone_path(url, allow_private=False)
    result = map_architecture(clone_path)
    click.echo(json.dumps(result, indent=2))


@repo_cmd.command("license")
@click.argument("url")
def repo_license(url: str) -> None:
    """License analysis only (admission + clone + LICENSE file)."""
    import dataclasses as dc

    from voly.intelligence.license_analyzer import analyze as analyze_license
    from voly.intelligence.repo_analyzer import find_license

    clone_path = _clone_path(url, allow_private=False)
    license_path = find_license(clone_path)
    info = analyze_license(license_path, spdx_hint=None)
    click.echo(json.dumps(dc.asdict(info), indent=2))
