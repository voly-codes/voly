"""Infrastructure CLI groups: memory, rtk, headroom, mcp."""
from __future__ import annotations

import click


# ── Memory ────────────────────────────────────────────────────────────────────

@click.group()
def memory() -> None:
    """Manage agent memory."""
    pass


@memory.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--limit", "-n", default=20, help="Max entries")
@click.pass_context
def memory_list(ctx: click.Context, category: str | None, limit: int) -> None:
    """List memory entries."""
    from codeops.memory.store import MemoryStore

    config = ctx.obj["config"]
    store = MemoryStore(config.memory.db_path)

    if category:
        entries = store.list_by_category(category, limit)
    else:
        entries = []
        for cat in ["decision", "convention", "context", "history"]:
            entries.extend(store.list_by_category(cat, limit // 4))

    for entry in entries:
        click.echo(f"[{entry.category}] {entry.title}")
        click.echo(f"  {entry.content[:120]}...")
        click.echo(f"  tags: {', '.join(entry.tags)} | importance: {entry.importance}")
        click.echo()

    store.close()


@memory.command("status")
@click.pass_context
def memory_status(ctx: click.Context) -> None:
    """Show semantic memory worker status."""
    from codeops.memory.client import create_memory_client, resolve_memory_url

    config = ctx.obj["config"]
    url = resolve_memory_url(config.memory.remote_url)
    if not url:
        click.echo("Memory worker URL not configured (CF_WORKER_MEMORY_URL).")
        click.echo("Local SQLite: " + config.memory.db_path)
        return

    client = create_memory_client(url)
    if not client:
        raise SystemExit(1)
    try:
        health = client.health()
        entries = client.list_entries(limit=1)
    except Exception as exc:
        click.echo(f"Memory worker unreachable: {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(f"Memory worker: {url}")
    click.echo(f"Status: {health.get('status', 'unknown')}")
    click.echo(f"Local fallback: {config.memory.db_path}")


@memory.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10)
@click.pass_context
def memory_search(ctx: click.Context, query: str, limit: int) -> None:
    """Search memory entries."""
    from codeops.memory.store import MemoryStore

    config = ctx.obj["config"]
    store = MemoryStore(config.memory.db_path, remote_url=config.memory.remote_url)
    results = store.search_semantic(query, limit)
    for entry in results:
        click.echo(f"[{entry.category}] {entry.title}")
        click.echo(f"  {entry.content[:120]}...")
    store.close()


# ── RTK ───────────────────────────────────────────────────────────────────────

@click.group()
def rtk() -> None:
    """Manage RTK (Rust Token Killer)."""
    pass


@rtk.command("install")
@click.pass_context
def rtk_install(ctx: click.Context) -> None:
    """Install RTK binary."""
    from codeops.rtk.installer import RTKManager

    config = ctx.obj["config"]
    mgr = RTKManager(config.rtk.binary_path)
    path = mgr.install()
    click.echo(f"RTK installed: {path}")


@rtk.command("stats")
@click.pass_context
def rtk_stats(ctx: click.Context) -> None:
    """Show RTK token savings."""
    import json
    from codeops.rtk.installer import RTKManager

    config = ctx.obj["config"]
    mgr = RTKManager(config.rtk.binary_path)
    stats = mgr.get_stats()
    if stats:
        click.echo(json.dumps(stats, indent=2))
    else:
        click.echo("No stats available")


# ── Headroom ──────────────────────────────────────────────────────────────────

@click.group()
def headroom() -> None:
    """Manage Headroom proxy."""
    pass


@headroom.command("start")
@click.option("--port", "-p", default=8787, help="Proxy port")
@click.pass_context
def headroom_start(ctx: click.Context, port: int) -> None:
    """Start Headroom compression proxy."""
    import time
    from codeops.headroom.proxy import HeadroomManager

    config = ctx.obj["config"]
    hm = HeadroomManager(port=port, savings_profile=config.headroom.savings_profile)
    if hm.start(wait=True):
        click.echo(f"Headroom proxy running on http://localhost:{port}")
        click.echo("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            hm.stop()
            click.echo("\nProxy stopped")
    else:
        click.echo("Failed to start proxy")


@headroom.command("status")
@click.pass_context
def headroom_status(ctx: click.Context) -> None:
    """Show Headroom proxy status."""
    from codeops.headroom.proxy import HeadroomManager

    config = ctx.obj["config"]
    hm = HeadroomManager(port=config.headroom.port)
    status = hm.status()
    if status.running:
        click.echo(f"Running on port {status.port}")
        click.echo(f"Version: {status.version}")
        click.echo(f"Tokens saved: {status.tokens_saved}")
        click.echo(f"Connections: {status.active_connections}")
    else:
        click.echo("Not running")


# ── MCP ───────────────────────────────────────────────────────────────────────

@click.group()
def mcp() -> None:
    """Manage MCP servers."""
    pass


@mcp.command("list")
@click.pass_context
def mcp_list(ctx: click.Context) -> None:
    """List available MCP servers."""
    from codeops.tools.mcp import MCPManager

    mgr = MCPManager()
    click.echo("Built-in MCP servers:")
    for name, spec in mgr.BUILTIN_SERVERS.items():
        click.echo(f"  {name}: {spec['command']} {' '.join(spec['args'])}")


@mcp.command("config")
@click.option("--format", "-f", "fmt", default="claude", help="Output format (claude/opencode)")
@click.pass_context
def mcp_config(ctx: click.Context, fmt: str) -> None:
    """Generate MCP config for AI agents."""
    import json
    from codeops.tools.mcp import MCPManager

    mgr = MCPManager()
    for name in ["github", "gitlab", "filesystem", "postgres"]:
        try:
            mgr.register_builtin(name)
        except ValueError:
            pass

    config = mgr.generate_claude_config() if fmt == "claude" else mgr.generate_opencode_config()
    click.echo(json.dumps(config, indent=2))
