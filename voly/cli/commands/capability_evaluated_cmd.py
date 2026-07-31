"""CLI for evaluated agent and skill capability packs."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.group("evaluated")
def capability_evaluated() -> None:
    """Manage measured capability pilots and routing."""


def _store(ctx: click.Context):
    from voly.capability import EvaluatedPackStore

    root = Path(ctx.obj["config"].capability.evaluated_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    return EvaluatedPackStore(root)


@capability_evaluated.command("init")
@click.pass_context
def evaluated_init(ctx: click.Context) -> None:
    """Initialize the three built-in pilot packs."""
    packs = _store(ctx).initialize()
    click.echo(json.dumps([pack.to_dict() for pack in packs], indent=2))


@capability_evaluated.command("list")
@click.pass_context
def evaluated_list(ctx: click.Context) -> None:
    """List evaluated pack state and evidence counts."""
    click.echo(json.dumps(
        [pack.to_dict() for pack in _store(ctx).load_packs()], indent=2
    ))


@capability_evaluated.command("record")
@click.argument("record", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def evaluated_record(ctx: click.Context, record: Path) -> None:
    """Record one paired baseline/variant outcome."""
    from voly.capability import CapabilityRunEvidence

    evidence = CapabilityRunEvidence(**json.loads(record.read_text(encoding="utf-8")))
    _store(ctx).record(evidence)
    click.echo(f"recorded: {evidence.capability_id}/{evidence.executor_id}")


@capability_evaluated.command("metrics")
@click.argument("capability_id")
@click.argument("executor_id")
@click.pass_context
def evaluated_metrics(
    ctx: click.Context, capability_id: str, executor_id: str
) -> None:
    """Show outcome metrics for one capability/executor pair."""
    metrics = _store(ctx).metrics(capability_id, executor_id)
    click.echo(json.dumps(metrics.__dict__, indent=2))


@capability_evaluated.command("activate")
@click.argument("capability_id")
@click.pass_context
def evaluated_activate(ctx: click.Context, capability_id: str) -> None:
    """Activate only after measured evidence exists."""
    pack = _store(ctx).activate(capability_id)
    click.echo(f"active: {pack.capability_id}")


@capability_evaluated.command("evaluate-retirement")
@click.argument("capability_id")
@click.argument("executor_id")
@click.pass_context
def evaluated_retire(
    ctx: click.Context, capability_id: str, executor_id: str
) -> None:
    """Retire a pack whose measured value misses its contract."""
    retired, reasons = _store(ctx).evaluate_retirement(
        capability_id, executor_id
    )
    click.echo(json.dumps({"retired": retired, "reasons": reasons}, indent=2))


@capability_evaluated.command("route")
@click.argument("task")
@click.option("--role", default="auto")
@click.option("--features", multiple=True)
@click.option("--executors", multiple=True)
@click.pass_context
def evaluated_route(
    ctx: click.Context,
    task: str,
    role: str,
    features: tuple[str, ...],
    executors: tuple[str, ...],
) -> None:
    """Resolve task → role → capability → executor → model."""
    from voly.capability import (
        CapabilityInput,
        CapabilityRegistry,
        EvaluatedPackRouter,
        ExecutorMatcher,
    )

    config = ctx.obj["config"].capability
    if not config.evaluated_enabled:
        click.echo(json.dumps({
            "role": role,
            "capability_id": "",
            "executor": "",
            "model": "",
            "native_fallback": True,
            "reason": "evaluated_capabilities_disabled",
        }, indent=2))
        return
    registry = CapabilityRegistry(config.profiles_dir)
    matcher = ExecutorMatcher(registry, worker_url=config.worker_url)
    route = EvaluatedPackRouter(_store(ctx), matcher).route(
        CapabilityInput(task, role, list(features)),
        available_executors=list(executors) or None,
    )
    click.echo(json.dumps(route.__dict__, indent=2))
