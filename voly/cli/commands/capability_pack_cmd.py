"""CLI commands for inert, staged external capability packs."""

from __future__ import annotations

import json
from pathlib import Path

import click


def _default_packs_dir(ctx: click.Context) -> Path:
    cfg = ctx.find_root().obj.get("config") if ctx.find_root().obj else None
    cap = getattr(cfg, "capability", None)
    raw = getattr(cap, "profiles_dir", None) if cap is not None else None
    profiles = Path(raw or ".voly/capability/profiles")
    if not profiles.is_absolute():
        profiles = Path.cwd() / profiles
    return profiles.parent / "packs"


@click.group("pack")
@click.option(
    "--store",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Staged pack root (default: .voly/capability/packs).",
)
@click.pass_context
def capability_pack(ctx: click.Context, store: Path | None) -> None:
    """Manage inert, versioned external capability packs."""
    ctx.ensure_object(dict)
    root = store if store is not None else _default_packs_dir(ctx)
    if not root.is_absolute():
        root = Path.cwd() / root
    ctx.obj["pack_store_root"] = root


def _pack_store(ctx: click.Context):
    from voly.capability.pack_store import PackStore

    return PackStore(ctx.obj["pack_store_root"])


@capability_pack.command("install")
@click.argument("adapter", type=click.Choice(["ecc"], case_sensitive=False))
@click.option(
    "--source",
    type=click.Path(path_type=Path, file_okay=False),
    required=True,
)
@click.pass_context
def capability_pack_install(
    ctx: click.Context,
    adapter: str,
    source: Path,
) -> None:
    """Atomically stage admitted components from an external checkout."""
    from voly.capability.pack_store import PackStoreError

    try:
        manifest = _pack_store(ctx).install_ecc(source)
    except (OSError, ValueError, PackStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    staged = sum(item.status == "staged" for item in manifest.components)
    quarantined = sum(item.status == "quarantined" for item in manifest.components)
    click.echo(
        f"staged {manifest.pack_id} via {adapter.lower()}: "
        f"components={staged} quarantined={quarantined}"
    )


@capability_pack.command("list")
@click.pass_context
def capability_pack_list(ctx: click.Context) -> None:
    """List installed staged capability packs."""
    from voly.capability.pack_store import PackStoreError

    try:
        manifests = _pack_store(ctx).list()
    except PackStoreError as exc:
        raise click.ClickException(str(exc)) from exc
    if not manifests:
        click.echo("(no staged packs)")
        return
    for manifest in manifests:
        click.echo(f"{manifest.pack_id}\t{manifest.version}\t{manifest.state}")


@capability_pack.command("show")
@click.argument("pack_id")
@click.pass_context
def capability_pack_show(ctx: click.Context, pack_id: str) -> None:
    """Print a staged capability-pack manifest as JSON."""
    from voly.capability.pack_store import PackStoreError

    try:
        manifest = _pack_store(ctx).load(pack_id)
    except (ValueError, PackStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))


@capability_pack.command("verify")
@click.argument("pack_id")
@click.pass_context
def capability_pack_verify(ctx: click.Context, pack_id: str) -> None:
    """Verify manifest and staged component hashes."""
    from voly.capability.pack_store import PackStoreError

    try:
        result = _pack_store(ctx).verify(pack_id)
    except (OSError, ValueError, PackStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    if result.valid:
        click.echo(f"verified {result.pack_id}: {result.checked_components} components")
        return
    for error in result.errors:
        click.echo(f"ERROR: {error}", err=True)
    raise click.ClickException(f"verification failed for {result.pack_id}")


@capability_pack.command("remove")
@click.argument("pack_id")
@click.option("--yes", is_flag=True, help="Confirm removal without prompting.")
@click.pass_context
def capability_pack_remove(
    ctx: click.Context,
    pack_id: str,
    yes: bool,
) -> None:
    """Remove exactly one staged capability pack."""
    from voly.capability.pack_store import PackStoreError

    if not yes:
        click.confirm(f"Remove staged capability pack {pack_id}?", abort=True)
    try:
        _pack_store(ctx).remove(pack_id)
    except (ValueError, PackStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"removed {pack_id}")
