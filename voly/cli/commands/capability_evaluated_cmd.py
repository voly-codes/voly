"""CLI for evaluated agent and skill capability packs."""

from __future__ import annotations

import json
import tempfile
from importlib.resources import files
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


@capability_evaluated.command("benchmark")
@click.pass_context
def evaluated_benchmark(ctx: click.Context) -> None:
    """Run the bundled 20-task offline routing probe (never activates packs)."""
    from voly.capability import CapabilityRegistry, EvaluatedPackRouter, ExecutorMatcher
    from voly.capability.validation import load_suite, probe_routing

    suite_path = files("voly.capability").joinpath("benchmark_suite_v1.json")
    tasks = load_suite(str(suite_path))
    with tempfile.TemporaryDirectory(prefix="voly-capability-probe-") as temp_dir:
        probe_store = type(_store(ctx))(temp_dir)
        packs = probe_store.initialize()
        for pack in packs:
            pack.state = type(pack.state).ACTIVE
            pack.evidence_count = 1
        probe_store.save_packs(packs)
        matcher = ExecutorMatcher(
            CapabilityRegistry(str(Path(temp_dir) / "profiles")),
            worker_url="",
        )
        report = probe_routing(tasks, EvaluatedPackRouter(probe_store, matcher))
    click.echo(json.dumps(report.to_dict(), indent=2))


def _decisions(ctx: click.Context, executor_id: str):
    from voly.capability.validation import decide_capability

    store = _store(ctx)
    return [
        decide_capability(store, pack.capability_id, executor_id, required_samples=6)
        for pack in store.load_packs()
    ]


@capability_evaluated.command("activation-plan")
@click.option("--executor", "executor_id", default="claude-code", show_default=True)
@click.pass_context
def evaluated_activation_plan(ctx: click.Context, executor_id: str) -> None:
    """Build decisions from real stored outcomes and report CF readiness."""
    from voly.capability.validation import build_activation_plan

    plan = build_activation_plan(_decisions(ctx, executor_id))
    click.echo(json.dumps(plan.to_dict(), indent=2))


@capability_evaluated.command("activate-ready")
@click.option("--executor", "executor_id", default="claude-code", show_default=True)
@click.option("--yes", is_flag=True, help="Apply locally recomputed activate decisions.")
@click.pass_context
def evaluated_activate_ready(
    ctx: click.Context, executor_id: str, yes: bool
) -> None:
    """Activate only locally validated packs; never deploy Cloudflare."""
    from voly.capability.validation import ActivationDecision, build_activation_plan

    if not yes:
        raise click.UsageError("--yes is required")
    decisions = _decisions(ctx, executor_id)
    plan = build_activation_plan(decisions)
    store = _store(ctx)
    activated = []
    for decision in decisions:
        if decision.decision is ActivationDecision.ACTIVATE:
            store.activate(decision.capability_id)
            activated.append(decision.capability_id)
    click.echo(json.dumps({
        "activated": activated,
        "cloudflare_deployed": False,
        "cloudflare_deploy_ready": plan.cloudflare_deploy_ready,
        "blockers": plan.blockers,
    }, indent=2))


@capability_evaluated.command("render-variant")
@click.argument("capability_id")
@click.argument("task")
@click.option(
    "--packs-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(".voly/capability/packs"),
)
@click.option("--max-instruction-chars", default=16000, type=int)
@click.pass_context
def evaluated_render_variant(
    ctx: click.Context,
    capability_id: str,
    task: str,
    packs_root: Path,
    max_instruction_chars: int,
) -> None:
    """Render a checksum-verified ECC variant prompt with provenance."""
    from voly.capability import CapabilityInput, render_variant_task

    pack = next(
        (
            item for item in _store(ctx).initialize()
            if item.capability_id == capability_id
        ),
        None,
    )
    if pack is None:
        raise click.ClickException(f"capability not found: {capability_id}")
    variant = render_variant_task(
        pack,
        CapabilityInput(task, pack.role),
        packs_root=packs_root,
        max_instruction_chars=max_instruction_chars,
    )
    click.echo(json.dumps({
        "capability_id": variant.capability_id,
        "source_pack_id": variant.source_pack_id,
        "instruction_hashes": variant.instruction_hashes,
        "task": variant.task,
    }, ensure_ascii=False, indent=2))
