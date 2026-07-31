"""CLI: voly capability — manage executor capability profiles."""

from __future__ import annotations

import json
from pathlib import Path

import click

from voly.cli.commands.capability_evaluated_cmd import capability_evaluated
from voly.cli.commands.capability_pack_cmd import capability_pack

_DEFAULT_PROFILES_DIR = ".voly/capability/profiles"


def _profiles_dir(ctx: click.Context) -> Path:
    cfg = ctx.obj.get("config")
    cap = getattr(cfg, "capability", None)
    raw = getattr(cap, "profiles_dir", None) if cap is not None else None
    if not raw:
        raw = getattr(cfg, "capability_profiles_dir", None)
    path = Path(raw or _DEFAULT_PROFILES_DIR)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _worker_url(ctx: click.Context) -> str:
    cfg = ctx.obj.get("config")
    cap = getattr(cfg, "capability", None)
    return str(getattr(cap, "worker_url", "") or "").strip() if cap is not None else ""


def _registry(ctx: click.Context):
    from voly.capability.registry import CapabilityRegistry

    return CapabilityRegistry(str(_profiles_dir(ctx)))


@click.group("capability")
def capability_cmd() -> None:
    """Manage executor capability profiles."""
    pass


@capability_cmd.command("list")
@click.pass_context
def capability_list(ctx: click.Context) -> None:
    """List all executor IDs with profiles."""
    reg = _registry(ctx)
    ids = reg.list_ids()
    if not ids:
        click.echo("(no profiles)")
        return
    for executor_id in ids:
        click.echo(executor_id)


@capability_cmd.command("show")
@click.argument("executor_id")
@click.pass_context
def capability_show(ctx: click.Context, executor_id: str) -> None:
    """Print full profile as YAML."""
    profile = _registry(ctx).load(executor_id)
    click.echo(_profile_to_yaml(profile.to_dict()))


@capability_cmd.command("match")
@click.argument("task")
@click.option("--dimension", default="backend", show_default=True)
@click.option(
    "--kind",
    default="executor",
    show_default=True,
    help="Profile kind: executor or model_provider",
)
@click.option(
    "--policy",
    "routing_policy",
    default=None,
    help="Routing policy: balanced | quality_first | budget_first (default: config)",
)
@click.option("--features", multiple=True, help="Project features (e.g. react fastapi)")
@click.option("--executors", multiple=True, help="Limit to specific executors")
@click.pass_context
def capability_match(
    ctx: click.Context,
    task: str,
    dimension: str,
    kind: str,
    routing_policy: str | None,
    features: tuple[str, ...],
    executors: tuple[str, ...],
) -> None:
    """Score and rank executors for a task dimension."""
    from voly.capability import ExecutorMatcher, MatchRequest

    reg = _registry(ctx)
    matcher = ExecutorMatcher(reg, worker_url=_worker_url(ctx))
    cap = getattr(ctx.obj.get("config"), "capability", None)
    policy = (routing_policy or getattr(cap, "routing_policy", None) or "balanced")
    req = MatchRequest(
        dimension=dimension,
        kind=kind,
        available_executors=list(executors) if executors else None,
        project_features=list(features) if features else None,
        requires_file_tools=(kind == "executor"),
        routing_policy=str(policy),
    )
    result = matcher.find_executors(req)
    if result.recommended:
        click.echo(
            f"Recommended: {result.recommended.id}  score={result.score:.3f}"
        )
    for profile, score in result.fallbacks[:3]:
        click.echo(f"  Fallback: {profile.id}  score={score:.3f}")
    for executor_id, reason in result.excluded:
        click.echo(f"  Excluded: {executor_id}  ({reason})")


@capability_cmd.command("reset")
@click.argument("executor_id", required=False)
@click.option("--all", "reset_all", is_flag=True, help="Reset all materialized profiles.")
@click.pass_context
def capability_reset(
    ctx: click.Context,
    executor_id: str | None,
    reset_all: bool,
) -> None:
    """Reset profile to seed values."""
    reg = _registry(ctx)
    if reset_all:
        reg.reset_all()
        click.echo(f"reset all profiles under {_profiles_dir(ctx)}")
        return
    if not executor_id:
        raise click.UsageError("executor_id is required unless --all is set")
    reg.reset(executor_id)
    click.echo(f"reset {executor_id}")


@capability_cmd.command("import")
@click.argument("adapter", type=click.Choice(["ecc"], case_sensitive=False))
@click.option(
    "--source",
    type=click.Path(path_type=Path, file_okay=False),
    required=True,
    help="Path to an external capability-pack checkout.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Inspect only. Required while external-pack installation is disabled.",
)
@click.option("--json-output", is_flag=True, help="Print the report as JSON.")
def capability_import(
    adapter: str,
    source: Path,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Discover an external capability pack without installing or executing it."""
    if not dry_run:
        raise click.UsageError(
            "--dry-run is required; external capability installation is not enabled"
        )

    from voly.capability.pack_admission import admit_external_pack
    from voly.capability.packs import ExternalPackError, discover_ecc_pack

    try:
        report = discover_ecc_pack(source)
        admission = admit_external_pack(report)
    except ExternalPackError as exc:
        raise click.ClickException(str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"capability admission failed: {exc}") from exc

    if json_output:
        payload = report.to_dict()
        payload["admission"] = admission.to_dict()
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    click.echo(f"Pack: {report.pack_id}")
    click.echo(f"Adapter: {adapter.lower()}")
    click.echo(f"Source: {report.provenance.source_path}")
    if report.provenance.repository:
        click.echo(f"Repository: {report.provenance.repository}")
    if report.provenance.revision:
        click.echo(f"Revision: {report.provenance.revision}")
    if report.provenance.package_version:
        click.echo(f"Version: {report.provenance.package_version}")
    click.echo("Mode: dry-run (nothing installed or executed)")
    click.echo(
        f"Admission: {admission.decision}  risk={admission.risk_level}  "
        f"findings={len(admission.findings)}  "
        f"quarantined={len(admission.quarantined_components)}"
    )
    for kind, count in report.counts.items():
        click.echo(f"  {kind}: {count}")
    for finding in admission.findings[:10]:
        click.echo(
            f"  [{finding.severity}] {finding.path}:{finding.line} "
            f"{finding.finding_id}"
        )
    if len(admission.findings) > 10:
        click.echo(f"  ... {len(admission.findings) - 10} more findings")
    for warning in report.warnings:
        click.echo(f"Warning: {warning}", err=True)


def _profile_to_yaml(data: dict) -> str:
    try:
        import yaml
    except ImportError:
        import json

        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
capability_cmd.add_command(capability_pack)
capability_cmd.add_command(capability_evaluated)
