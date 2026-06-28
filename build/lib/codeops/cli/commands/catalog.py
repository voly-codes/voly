"""CLI: codeops catalog — agent/model catalog from OpenCode Zen."""

from __future__ import annotations

import json

import click


@click.group()
def catalog() -> None:
    """Agent & model catalog (OpenCode Zen sync + routing)."""
    pass


@catalog.command("sync")
@click.option("--push", is_flag=True, help="Push to CF catalog worker if CF_WORKER_CATALOG_URL set")
@click.pass_context
def catalog_sync(ctx: click.Context, push: bool) -> None:
    """Sync models from OpenCode Zen API to .codeops/catalog/models.json."""
    from pathlib import Path

    from codeops.catalog.supervisor import CombatSupervisor

    cwd = Path.cwd()
    project = cwd
    codeops_root = cwd if (cwd / "codeops" / "codeops").is_dir() else cwd.parent
    if (cwd / "codeops.yaml").is_file() or (cwd / "codeops" / "codeops.yaml").is_file():
        codeops_root = cwd / "codeops" if (cwd / "codeops" / "codeops.yaml").is_file() else cwd

    sup = CombatSupervisor(str(project), codeops_root=Path(codeops_root))
    try:
        n = sup.sync_catalog(push_remote=push)
        click.echo(f"Synced {n} models → {Path(codeops_root) / '.codeops/catalog/models.json'}")
    except Exception as exc:
        click.echo(f"Sync failed: {exc}", err=True)
        raise SystemExit(1) from exc


@catalog.command("list")
@click.option("--tier", default=None, help="Filter: free | cheap | standard | premium")
@click.option("--json", "as_json", is_flag=True)
def catalog_list(tier: str | None, as_json: bool) -> None:
    """List cached catalog models."""
    from codeops.catalog.store import load_models

    models = load_models()
    if tier:
        models = [m for m in models if m.tier == tier]
    if as_json:
        click.echo(json.dumps([m.to_dict() for m in models], ensure_ascii=False, indent=2))
        return
    if not models:
        click.echo("No models in cache. Run: codeops catalog sync")
        return
    click.echo(f"{'ID':<28} {'Tier':<10} {'Provider':<12} Executors")
    click.echo("-" * 70)
    for m in models:
        ex = ",".join(m.executor_compat[:2])
        click.echo(f"{m.id:<28} {m.tier:<10} {m.provider:<12} {ex}")


@catalog.command("match")
@click.argument("task")
@click.option("--json", "as_json", is_flag=True)
def catalog_match(task: str, as_json: bool) -> None:
    """Match task text to executor + model."""
    from codeops.catalog.routing import match_task

    executor, model = match_task(task)
    out = {"task": task, "executor": executor, "model": model}
    if as_json:
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        click.echo(f"executor: {executor}")
        click.echo(f"model:    {model}")


@catalog.command("plan")
@click.argument("mission_id")
def catalog_plan(mission_id: str) -> None:
    """Show supervised routing plan for a combat mission."""
    from codeops.catalog.routing import get_mission_plan

    steps = get_mission_plan(mission_id)
    if not steps:
        click.echo(f"No supervised plan for '{mission_id}'")
        raise SystemExit(1)
    click.echo(f"Mission: {mission_id}\n")
    for i, s in enumerate(steps, 1):
        skills = ", ".join(s.skills) if s.skills else "—"
        ro = " [readonly]" if s.readonly else ""
        click.echo(f"  {i}. {s.executor} + {s.model} ({s.agent_role}){ro}")
        click.echo(f"     skills: {skills}")
