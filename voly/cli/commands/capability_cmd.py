"""CLI: voly capability — manage executor capability profiles."""

from __future__ import annotations

from pathlib import Path

import click

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


def _profile_to_yaml(data: dict) -> str:
    try:
        import yaml
    except ImportError:
        import json

        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
