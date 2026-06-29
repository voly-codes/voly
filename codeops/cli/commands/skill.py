"""Skill marketplace CLI — search, install, publish, list."""
from __future__ import annotations

from pathlib import Path

import click
import yaml

from codeops.registry.loader import skill_from_dict, skill_to_yaml_dict
from codeops.registry.marketplace import MarketplaceClient, MarketplaceError
from codeops.registry.skills import create_skill_registry, resolve_marketplace_url


def _registry(ctx: click.Context):
    config = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    config_dir = Path(config_path).parent if config_path else Path.cwd()
    return create_skill_registry(
        skills_path=config.registry.skills_path,
        marketplace_url=config.registry.marketplace_url,
        config_dir=config_dir,
    )


def _marketplace_client(ctx: click.Context) -> MarketplaceClient:
    config = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    config_dir = Path(config_path).parent if config_path else Path.cwd()
    url = resolve_marketplace_url(config.registry.marketplace_url)
    if not url:
        raise click.ClickException(
            "Marketplace URL not configured. Set registry.marketplace_url in codeops.yaml "
            "or CF_WORKER_MARKETPLACE_URL in .env"
        )
    return MarketplaceClient(url)


@click.group()
def skill() -> None:
    """Manage skills — local registry and marketplace."""
    pass


@skill.command("list")
@click.option("--local", "local_only", is_flag=True, help="List local registry only")
@click.option("--agent", "-a", default=None)
@click.option("--tag", "-t", default=None)
@click.option("--limit", "-n", default=20, show_default=True)
@click.pass_context
def skill_list(
    ctx: click.Context,
    local_only: bool,
    agent: str | None,
    tag: str | None,
    limit: int,
) -> None:
    """List skills from marketplace or local registry."""
    if local_only:
        reg = _registry(ctx)
        kwargs: dict = {}
        if agent:
            kwargs["agent"] = agent
        if tag:
            kwargs["tags"] = [tag]
        skills = reg.search(**kwargs) if kwargs else reg.index.list_all()
        for s in skills:
            click.echo(f"[{s.source.value}] {s.id} — {s.name}")
            if s.tags:
                click.echo(f"  tags: {', '.join(s.tags)}")
        return

    mp = _marketplace_client(ctx)
    data = mp.list_skills(limit=limit, agent=agent)
    for s in data.get("skills", []):
        click.echo(f"[{s.get('source', '?')}] {s['id']} — {s['name']}")
        tags = s.get("tags") or []
        if tags:
            click.echo(f"  tags: {', '.join(tags)}")
    click.echo(f"\nTotal: {data.get('total', 0)}")


@skill.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10, show_default=True)
@click.pass_context
def skill_search(ctx: click.Context, query: str, limit: int) -> None:
    """Semantic search in marketplace."""
    mp = _marketplace_client(ctx)
    try:
        data = mp.search(query, limit=limit)
    except MarketplaceError as exc:
        raise click.ClickException(str(exc)) from exc

    source = data.get("source", "unknown")
    skills = data.get("skills", [])
    click.echo(f"Search: {query!r} ({source}, {len(skills)} results)\n")
    for s in skills:
        click.echo(f"  {s['id']} — {s['name']}")
        if s.get("description"):
            click.echo(f"    {s['description'][:120]}")


@skill.command("install")
@click.argument("skill_id")
@click.pass_context
def skill_install(ctx: click.Context, skill_id: str) -> None:
    """Download skill from marketplace into .codeops/skills/."""
    reg = _registry(ctx)
    try:
        skill_obj = reg.install_from_marketplace(skill_id)
    except MarketplaceError as exc:
        raise click.ClickException(str(exc)) from exc

    path = reg.skills_path / f"{skill_obj.id}.yaml" if reg.skills_path else None
    click.echo(f"Installed: {skill_obj.id} — {skill_obj.name}")
    if path:
        click.echo(f"Saved: {path}")


@skill.command("publish")
@click.argument("yaml_path", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def skill_publish(ctx: click.Context, yaml_path: str) -> None:
    """Publish skill YAML to marketplace."""
    reg = _registry(ctx)
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise click.ClickException("Invalid skill YAML: expected mapping")

    skill_obj = skill_from_dict(data)
    payload = skill_to_yaml_dict(skill_obj)
    payload["source"] = payload.get("source") or "marketplace"

    try:
        result = reg.publish_to_marketplace(payload)
    except MarketplaceError as exc:
        raise click.ClickException(str(exc)) from exc

    skill_id = result.get("id", skill_obj.id)
    click.echo(f"Published: {skill_id}")


@skill.command("generate")
@click.option("--cwd", "project_root", default=".", show_default=True, help="Project root to scan")
@click.option("--dry-run", is_flag=True, help="Print skills without saving")
@click.pass_context
def skill_generate(ctx: click.Context, project_root: str, dry_run: bool) -> None:
    """Generate PROJECT skills from CLAUDE.md, README, ARCHITECTURE docs."""
    from pathlib import Path

    from codeops.registry.loader import save_skill_yaml, skill_from_dict
    from codeops.registry.project_skill_extractor import generate_project_skills
    from codeops.scanner import ProjectScanner

    root = Path(project_root).resolve()
    scanner = ProjectScanner(root)
    profile = scanner.scan()
    skills = generate_project_skills(root, profile)

    if not skills:
        click.echo("No project skills generated — no CLAUDE.md, README.md or other docs found.")
        return

    for s in skills:
        src = s.get("metadata", {}).get("source_file", "profile")
        preview = s.get("content", "")[:80].replace("\n", " ")
        click.echo(f"\n{s['id']} — {s['name']}")
        click.echo(f"  source: {src}")
        click.echo(f"  preview: {preview}…")

    if dry_run:
        click.echo(f"\n(dry run — {len(skills)} skill(s) not saved)")
        return

    reg = _registry(ctx)
    saved = 0
    if reg.skills_path:
        for skill_dict in skills:
            skill_obj = skill_from_dict(skill_dict)
            save_skill_yaml(skill_obj, reg.skills_path / f"{skill_obj.id}.yaml")
            saved += 1
    click.echo(f"\nSaved {saved} skill(s) → {reg.skills_path}")


@skill.command("show")
@click.argument("skill_id")
@click.option("--local", "local_only", is_flag=True, help="Show from local registry")
@click.pass_context
def skill_show(ctx: click.Context, skill_id: str, local_only: bool) -> None:
    """Show skill details."""
    if local_only:
        reg = _registry(ctx)
        skill_obj = reg.get(skill_id)
        if not skill_obj:
            raise click.ClickException(f"Skill not found locally: {skill_id}")
        click.echo(yaml.safe_dump(skill_to_yaml_dict(skill_obj), allow_unicode=True, sort_keys=False))
        return

    mp = _marketplace_client(ctx)
    try:
        data = mp.download_skill(skill_id)
    except MarketplaceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
