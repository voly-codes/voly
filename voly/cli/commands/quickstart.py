"""Safe, deterministic first-run readiness check for VOLY."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import click

from voly.config import create_default_config, load_config
from voly.environment import collect_environment_report

_EXECUTOR_PREFERENCE = ("claude-code", "cursor", "opencode", "zen", "wrangler")


def _quote_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _recommended_executor(executors: dict[str, dict[str, Any]]) -> str:
    for name in _EXECUTOR_PREFERENCE:
        if executors.get(name, {}).get("available"):
            return name
    return ""


def _config_state(config_path: Path) -> tuple[str, str]:
    if not config_path.exists():
        return "missing", "No voly.yaml in the selected repository"
    if not config_path.is_file():
        return "invalid", f"Config path is not a file: {config_path}"
    try:
        load_config(config_path)
    except Exception as exc:
        return "invalid", f"Existing voly.yaml cannot be loaded: {exc}"
    return "ready", str(config_path)


def _build_result(cwd: Path, config: Any, task: str | None) -> dict[str, Any]:
    exists = cwd.is_dir()
    resolved = cwd.resolve() if exists else cwd.absolute()
    is_git = exists and (resolved / ".git").exists()
    config_path = resolved / "voly.yaml"
    config_status, config_detail = _config_state(config_path) if exists else (
        "blocked",
        "Repository path does not exist",
    )

    report = collect_environment_report(config, cwd=str(resolved))
    executor = _recommended_executor(report.executors)
    blockers: list[str] = []
    warnings: list[str] = []
    if not exists:
        blockers.append(f"Repository path does not exist: {resolved}")
    elif not is_git:
        warnings.append("The selected directory is not a Git repository; rollback and diff checks are weaker.")
    if config_status == "invalid":
        blockers.append(config_detail)
    if not executor:
        blockers.append("No supported file-capable executor was detected.")

    command_parts = ["voly", "run"]
    if task:
        command_parts.append(task)
    else:
        command_parts.append("YOUR TASK")
    if executor:
        command_parts.extend(["--executor", executor])
    command_parts.extend(["--cwd", str(resolved), "--dry-run"])

    return {
        "ready": not blockers,
        "repository": {
            "path": str(resolved),
            "exists": exists,
            "git": is_git,
        },
        "config": {
            "path": str(config_path),
            "status": config_status,
            "detail": config_detail,
        },
        "executors": report.executors,
        "recommended_executor": executor,
        "warnings": warnings,
        "blockers": blockers,
        "next_command": _quote_command(command_parts),
        "task_placeholder": task is None,
    }


def _echo_result(result: dict[str, Any], *, check_only: bool) -> None:
    click.echo("VOLY quickstart")
    click.echo(f"  Repository  {result['repository']['path']}")
    click.echo(
        f"  Git         {'ready' if result['repository']['git'] else 'not detected (warning)'}"
    )
    click.echo(f"  Config      {result['config']['status']}: {result['config']['detail']}")

    available = [
        name
        for name, details in result["executors"].items()
        if name != "pipeline" and details.get("available")
    ]
    click.echo(f"  Executors   {', '.join(available) if available else 'none detected'}")
    if result["recommended_executor"]:
        click.echo(f"  Recommended {result['recommended_executor']} (first available preference)")

    for warning in result["warnings"]:
        click.echo(f"  WARNING     {warning}")
    for blocker in result["blockers"]:
        click.echo(f"  BLOCKED     {blocker}")

    if result["ready"]:
        click.echo("\nReady for a first safe task.")
        if result["task_placeholder"]:
            click.echo("Replace YOUR TASK with a real task; quickstart did not run an agent.")
        click.echo(f"\n  {result['next_command']}")
    elif check_only:
        click.echo("\nNot ready. Resolve the blocking items and run the check again.")


@click.command()
@click.option("--cwd", type=click.Path(path_type=Path), default=Path.cwd, help="Repository path")
@click.option("--check", "check_only", is_flag=True, help="Read-only readiness check")
@click.option("--json", "output_json", is_flag=True, help="Machine-readable result")
@click.option("--yes", is_flag=True, help="Create missing config without prompting")
@click.option("--task", default=None, help="Task to include in the suggested first command")
@click.pass_context
def quickstart(
    ctx: click.Context,
    cwd: Path,
    check_only: bool,
    output_json: bool,
    yes: bool,
    task: str | None,
) -> None:
    """Check readiness and prepare the shortest safe path to a first VOLY task."""
    result = _build_result(cwd, ctx.obj["config"], task)

    if not check_only and result["config"]["status"] == "missing" and not result["blockers"]:
        create = yes
        if not yes and click.get_text_stream("stdin").isatty():
            create = click.confirm(f"Create {result['config']['path']}?", default=True)
        if create:
            create_default_config(Path(result["config"]["path"]))
            result["config"] = {
                "path": result["config"]["path"],
                "status": "created",
                "detail": "Created without secrets",
            }

    if output_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _echo_result(result, check_only=check_only)

    if result["blockers"]:
        raise click.exceptions.Exit(1)

