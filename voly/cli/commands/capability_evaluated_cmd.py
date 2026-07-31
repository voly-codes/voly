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


def _sync_receipt_path(ctx: click.Context) -> Path:
    return _store(ctx).root / "remote-sync-receipt.json"


def _remote_sync_verified(ctx: click.Context, executor_id: str) -> bool:
    from voly.capability import has_current_verified_receipt

    store = _store(ctx)
    return has_current_verified_receipt(
        store,
        executor_id,
        _sync_receipt_path(ctx),
    )


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

    plan = build_activation_plan(
        _decisions(ctx, executor_id),
        remote_sync_verified=_remote_sync_verified(ctx, executor_id),
    )
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
    plan = build_activation_plan(
        decisions,
        remote_sync_verified=_remote_sync_verified(ctx, executor_id),
    )
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


def _parse_provenance_hashes(
    values: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    parsed: dict[str, dict[str, str]] = {}
    for value in values:
        try:
            capability_id, assignment = value.split(":", 1)
            name, digest = assignment.rsplit("=", 1)
        except ValueError as exc:
            raise click.BadParameter(
                "expected CAPABILITY:NAME=SHA256",
                param_hint="--provenance-hash",
            ) from exc
        parsed.setdefault(capability_id, {})[name] = digest
    return parsed


@capability_evaluated.command("sync")
@click.option("--executor", "executor_id", default="claude-code", show_default=True)
@click.option("--worker-url", default="", help="Override capability Worker URL.")
@click.option(
    "--packs-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(".voly/capability/packs"),
)
@click.option(
    "--provenance-hash",
    multiple=True,
    help="Additional CAPABILITY:NAME=SHA256 provenance.",
)
@click.option("--timeout", default=15.0, type=float, show_default=True)
@click.pass_context
def evaluated_sync(
    ctx: click.Context,
    executor_id: str,
    worker_url: str,
    packs_root: Path,
    provenance_hash: tuple[str, ...],
    timeout: float,
) -> None:
    """Upload and read back one authenticated evaluated-pack snapshot."""
    from voly.capability import build_remote_snapshot, sync_remote_snapshot
    from voly.capability.remote_sync import sync_token_from_env
    from voly.capability.validation import ActivationDecision

    decisions = _decisions(ctx, executor_id)
    if any(item.decision is ActivationDecision.KEEP_PILOT for item in decisions):
        raise click.ClickException("cannot sync while a pilot is incomplete")
    if not any(item.decision is ActivationDecision.ACTIVATE for item in decisions):
        raise click.ClickException("cannot sync without an activated capability")
    store = _store(ctx)
    snapshot = build_remote_snapshot(
        store,
        executor_id,
        packs_root=packs_root,
        additional_hashes=_parse_provenance_hashes(provenance_hash),
    )
    url = worker_url or ctx.obj["config"].capability.worker_url
    try:
        receipt = sync_remote_snapshot(
            store,
            snapshot,
            worker_url=url,
            token=sync_token_from_env(),
            receipt_path=_sync_receipt_path(ctx),
            timeout=timeout,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({
        "synced": True,
        "verified": receipt.verified,
        "snapshot_id": receipt.snapshot_id,
        "packs": len(snapshot["packs"]),
        "cloudflare_deploy_ready": True,
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


@capability_evaluated.command("render-instinct-variant")
@click.argument("capability_id")
@click.argument("instinct_id")
@click.argument("task")
@click.option(
    "--instincts-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path(".voly/learning/instincts.json"),
)
@click.option("--max-action-chars", default=1200, type=int)
@click.pass_context
def evaluated_render_instinct_variant(
    ctx: click.Context,
    capability_id: str,
    instinct_id: str,
    task: str,
    instincts_path: Path,
    max_action_chars: int,
) -> None:
    """Render one approved compact instinct for an evaluated run."""
    from voly.capability import (
        CapabilityInput,
        render_instinct_variant_task,
    )
    from voly.learning import InstinctStore

    pack = next(
        (
            item for item in _store(ctx).initialize()
            if item.capability_id == capability_id
        ),
        None,
    )
    if pack is None:
        raise click.ClickException(f"capability not found: {capability_id}")
    instinct = next(
        (
            item for item in InstinctStore(instincts_path).list()
            if item.id == instinct_id
        ),
        None,
    )
    if instinct is None:
        raise click.ClickException(f"instinct not found: {instinct_id}")
    try:
        variant = render_instinct_variant_task(
            pack,
            CapabilityInput(task, pack.role),
            instinct,
            max_action_chars=max_action_chars,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({
        "capability_id": variant.capability_id,
        "source_pack_id": variant.source_pack_id,
        "instruction_hashes": variant.instruction_hashes,
        "task": variant.task,
    }, ensure_ascii=False, indent=2))
