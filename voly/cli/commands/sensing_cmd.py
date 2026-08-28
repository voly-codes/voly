"""CLI for opt-in business Signal polling and local inspection."""

from __future__ import annotations

import json

import click


@click.group("sensing")
def sensing_cmd() -> None:
    """Poll and inspect external business Signals."""


def _store(ctx: click.Context):
    from voly.sensing.store import SignalStore

    return SignalStore(ctx.obj["config"].sensing.store_dir)


@sensing_cmd.command("poll")
@click.option("--connector", "connector_name", default="rss", show_default=True)
@click.option("--json-out", is_flag=True, help="Print stored Signals as JSON")
@click.pass_context
def sensing_poll(ctx: click.Context, connector_name: str, json_out: bool) -> None:
    """Poll one configured connector once and store unseen Signals."""
    from voly.sensing.connectors import RSSConnector

    config = ctx.obj["config"].sensing
    if not config.enabled or config.mode == "off":
        raise click.ClickException(
            "sensing is disabled; set sensing.enabled=true and mode=shadow|active"
        )
    connector_config = next(
        (item for item in config.connectors if item.name == connector_name), None
    )
    if connector_config is None:
        raise click.ClickException(f"connector is not configured: {connector_name}")
    if connector_name != "rss":
        raise click.ClickException(f"unsupported connector: {connector_name}")
    connector = RSSConnector(connector_config.feeds)
    try:
        observed = connector.poll()
        stored = _store(ctx).save_many(observed)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    if json_out:
        click.echo(json.dumps([item.to_dict() for item in stored], ensure_ascii=False, indent=2))
        return
    click.echo(f"observed={len(observed)} stored={len(stored)} duplicates={len(observed) - len(stored)}")


@sensing_cmd.command("list")
@click.option("--json-out", is_flag=True)
@click.pass_context
def sensing_list(ctx: click.Context, json_out: bool) -> None:
    """List locally stored Signals, newest first."""
    signals = _store(ctx).list()
    if json_out:
        click.echo(json.dumps([item.to_dict() for item in signals], ensure_ascii=False, indent=2))
        return
    if not signals:
        click.echo("No signals in store.")
        return
    click.echo(f"{'SIGNAL_ID':<22} {'SOURCE':<10} {'CAPTURED_AT':<21} TITLE")
    for signal in signals:
        title = str(signal.payload.get("title") or "")[:60]
        click.echo(f"{signal.signal_id:<22} {signal.source:<10} {signal.captured_at:<21} {title}")
