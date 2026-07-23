"""CLI: voly catalog — agent/model catalog from OpenCode Zen + freellm sources."""

from __future__ import annotations

import json

import click

_VOLY_YAML = "voly.yaml"


@click.group()
def catalog() -> None:
    """Agent & model catalog (OpenCode Zen sync + routing)."""
    pass


@catalog.command("sync")
@click.option("--push", is_flag=True, help="Push to CF catalog worker if CF_WORKER_CATALOG_URL set")
@click.pass_context
def catalog_sync(ctx: click.Context, push: bool) -> None:
    """Sync models from OpenCode Zen API to .voly/catalog/models.json."""
    from pathlib import Path

    from voly.catalog.supervisor import CombatSupervisor

    cwd = Path.cwd()
    project = cwd
    voly_root = cwd if (cwd / "voly" / "voly").is_dir() else cwd.parent
    if (cwd / _VOLY_YAML).is_file() or (cwd / "voly" / _VOLY_YAML).is_file():
        voly_root = cwd / "voly" if (cwd / "voly" / _VOLY_YAML).is_file() else cwd

    sup = CombatSupervisor(str(project), voly_root=Path(voly_root))
    try:
        n = sup.sync_catalog(push_remote=push)
        click.echo(f"Synced {n} models → {Path(voly_root) / '.voly/catalog/models.json'}")
    except Exception as exc:
        click.echo(f"Sync failed: {exc}", err=True)
        raise SystemExit(1) from exc


@catalog.command("list")
@click.option("--tier", default=None, help="Filter: free | cheap | standard | premium")
@click.option("--json", "as_json", is_flag=True)
def catalog_list(tier: str | None, as_json: bool) -> None:
    """List cached catalog models."""
    from voly.catalog.store import load_models

    models = load_models()
    if tier:
        models = [m for m in models if m.tier == tier]
    if as_json:
        click.echo(json.dumps([m.to_dict() for m in models], ensure_ascii=False, indent=2))
        return
    if not models:
        click.echo("No models in cache. Run: voly catalog sync")
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
    from voly.catalog.routing import match_task

    executor, model = match_task(task)
    out = {"task": task, "executor": executor, "model": model}
    if as_json:
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        click.echo(f"executor: {executor}")
        click.echo(f"model:    {model}")


@catalog.command("import-freellm")
@click.argument("source", type=click.Path())
@click.option(
    "--dry-run",
    is_flag=True,
    help="Parse and show what would be imported without writing anything.",
)
@click.option("--json", "as_json", is_flag=True, help="Output imported models as JSON.")
@click.option(
    "--push",
    is_flag=True,
    help="After saving locally, push merged catalog to CF_WORKER_CATALOG_URL.",
)
def catalog_import_freellm(source: str, dry_run: bool, as_json: bool, push: bool) -> None:
    """Import free LLM models from awesome-freellm-apis README into the local catalog.

    SOURCE is the path to the README.md file or the root checkout directory of
    awesome-freellm-apis (https://github.com/open-free-llm-api/awesome-free-llm-apis).

    The external repository is read-only — nothing is written back to it.
    Imported models start with verified=False.  Use --push to sync the merged
    result to the remote CF Worker (requires CF_WORKER_CATALOG_URL env var).
    """
    from pathlib import Path

    from voly.catalog.freellm_importer import merge_with_catalog, parse_readme
    from voly.catalog.store import load_models, save_models

    try:
        imported = parse_readme(Path(source))
    except FileNotFoundError as exc:
        click.echo(f"Source not found: {exc}", err=True)
        raise SystemExit(1) from exc
    except ValueError as exc:
        click.echo(f"Parse error: {exc}", err=True)
        raise SystemExit(1) from exc

    if dry_run or as_json:
        click.echo(
            json.dumps([m.to_dict() for m in imported], ensure_ascii=False, indent=2)
        )
        if dry_run:
            click.echo(
                f"\n[dry-run] Would import {len(imported)} models. Nothing written.",
                err=True,
            )
        return

    existing = load_models()
    merged = merge_with_catalog(existing, imported)

    path = save_models(merged)
    new_count = len(merged) - len(existing)
    click.echo(
        f"Imported {len(imported)} models from freellm source "
        f"({new_count:+d} new, {len(existing)} existing preserved)."
    )
    click.echo(f"Saved → {path}")

    if push:
        try:
            from voly.catalog.client import CatalogClient

            client = CatalogClient.from_env()
            if not client:
                click.echo(
                    "CF_WORKER_CATALOG_URL not set — skipping remote push.", err=True
                )
            else:
                result = client.sync_models([m.to_dict() for m in merged])
                click.echo(f"Pushed {result.get('upserted', '?')} models to remote catalog.")
        except Exception as exc:
            click.echo(f"Remote push failed: {exc}", err=True)
            raise SystemExit(1) from exc


@catalog.command("plan")
@click.argument("mission_id")
def catalog_plan(mission_id: str) -> None:
    """Show supervised routing plan for a combat mission."""
    from voly.catalog.routing import get_mission_plan

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
