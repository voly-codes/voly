"""CLI for constrained lifecycle hook manifests."""

from __future__ import annotations

import json
from pathlib import Path

import click

from voly.hooks import HookAdapter, HookEvent, HookEventType, HookRegistry


@click.group("hooks")
def hooks_cmd() -> None:
    """Import, approve, inspect, and dispatch lifecycle hooks."""


def _path(cwd: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def _registry(ctx: click.Context, cwd: Path) -> HookRegistry:
    return HookRegistry(_path(cwd, ctx.obj["config"].hooks.registry_path))


@hooks_cmd.command("import")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def hooks_import(ctx: click.Context, manifest: Path, cwd: Path) -> None:
    """Import one manifest in disabled state."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    imported = _registry(ctx, cwd).import_manifest(data)
    click.echo(f"imported disabled: {imported.hook_id}")


@hooks_cmd.command("approve")
@click.argument("hook_id")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def hooks_approve(ctx: click.Context, hook_id: str, cwd: Path) -> None:
    """Explicitly enable one imported hook."""
    approved = _registry(ctx, cwd).approve(hook_id)
    click.echo(f"approved: {approved.hook_id}")


@hooks_cmd.command("list")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def hooks_list(ctx: click.Context, cwd: Path) -> None:
    """List manifests and approval state."""
    click.echo(json.dumps(
        [item.to_dict() for item in _registry(ctx, cwd).load()],
        ensure_ascii=False,
        indent=2,
    ))


@hooks_cmd.command("dispatch")
@click.argument("event_type", type=click.Choice([item.value for item in HookEventType]))
@click.argument("run_id")
@click.option("--project-id", required=True)
@click.option("--payload", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def hooks_dispatch(
    ctx: click.Context,
    event_type: str,
    run_id: str,
    project_id: str,
    payload: Path | None,
    cwd: Path,
) -> None:
    """Dispatch an event through enabled allowlisted hooks."""
    config = ctx.obj["config"].hooks
    if not config.enabled:
        raise click.ClickException("hooks are disabled in config")
    event_payload = (
        json.loads(payload.read_text(encoding="utf-8")) if payload else {}
    )
    adapter = HookAdapter(
        _registry(ctx, cwd),
        state_path=_path(cwd, config.state_path),
        evidence_log=_path(cwd, config.evidence_log),
        telemetry_log=_path(cwd, config.telemetry_log),
    )
    results = adapter.dispatch(HookEvent(
        HookEventType(event_type),
        run_id=run_id,
        project_id=project_id,
        cwd=str(cwd.resolve()),
        payload=event_payload,
    ))
    click.echo(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
    if any(not item.proceed for item in results):
        raise SystemExit(2)
