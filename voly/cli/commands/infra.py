"""Infrastructure CLI groups: memory, rtk, headroom, pxpipe, mcp."""
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
    from voly.memory.store import MemoryStore

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
    """Show remote memory backend status (Worker or Agent Memory)."""
    from voly.memory.client import create_remote_memory_client

    config = ctx.obj["config"]
    mem = config.memory
    click.echo(f"Backend: {mem.backend}")
    click.echo(f"Local SQLite: {mem.db_path}")

    if (mem.backend or "").lower() == "local":
        return

    client = create_remote_memory_client(
        backend=mem.backend,
        remote_url=mem.remote_url,
        agent_memory_account_id=mem.agent_memory_account_id,
        agent_memory_namespace=mem.agent_memory_namespace,
        agent_memory_profile=mem.agent_memory_profile,
    )
    if not client:
        if (mem.backend or "").lower() == "agent_memory":
            click.echo("Agent Memory not configured (set CF_ACCOUNT_ID + API token).")
        else:
            click.echo("Memory worker URL not configured (CF_WORKER_MEMORY_URL).")
        return

    try:
        health = client.health()
    except Exception as exc:
        click.echo(f"Remote memory unreachable: {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(f"Status: {health.get('status', 'unknown')}")
    if health.get("service"):
        click.echo(f"Service: {health['service']}")
    if health.get("namespace"):
        click.echo(f"Namespace: {health['namespace']} / profile: {health.get('profile')}")


@memory.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10)
@click.pass_context
def memory_search(ctx: click.Context, query: str, limit: int) -> None:
    """Search memory entries."""
    from voly.memory.store import MemoryStore

    config = ctx.obj["config"]
    mem = config.memory
    store = MemoryStore(
        mem.db_path,
        remote_url=mem.remote_url,
        backend=mem.backend,
        agent_memory_account_id=mem.agent_memory_account_id,
        agent_memory_namespace=mem.agent_memory_namespace,
        agent_memory_profile=mem.agent_memory_profile,
    )
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
    from voly.rtk.installer import RTKManager

    config = ctx.obj["config"]
    mgr = RTKManager(config.rtk.binary_path)
    path = mgr.install()
    click.echo(f"RTK installed: {path}")


@rtk.command("stats")
@click.pass_context
def rtk_stats(ctx: click.Context) -> None:
    """Show RTK token savings."""
    import json
    from voly.rtk.installer import RTKManager

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
    from voly.headroom.proxy import HeadroomManager

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
    from voly.headroom.proxy import HeadroomManager

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


# ── pxpipe ────────────────────────────────────────────────────────────────────

@click.group()
def pxpipe() -> None:
    """Manage pxpipe token-saving proxy."""
    pass


@pxpipe.command("start")
@click.option("--port", "-p", default=None, type=int, help="Proxy port")
@click.pass_context
def pxpipe_start(ctx: click.Context, port: int | None) -> None:
    """Start pxpipe for Claude Code compression."""
    import time
    from voly.pxpipe.artifacts import inbox_dir
    from voly.pxpipe.proxy import PxpipeManager

    config = ctx.obj["config"]
    proxy_port = port or config.pxpipe.port
    dump_dir = inbox_dir(config)
    mgr = PxpipeManager(port=proxy_port, models=config.pxpipe.models, dump_dir=dump_dir)
    if mgr.start(wait=True):
        click.echo(f"pxpipe proxy running on http://127.0.0.1:{proxy_port}")
        click.echo(f"PNG dump dir: {dump_dir}")
        click.echo("Use VOLY_PXPIPE_ENABLED=true to route claude-code through it.")
        click.echo("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mgr.stop()
            click.echo("\nProxy stopped")
    else:
        click.echo("Failed to start pxpipe (install pxpipe or ensure npx is available)", err=True)
        raise SystemExit(1)


@pxpipe.command("status")
@click.pass_context
def pxpipe_status(ctx: click.Context) -> None:
    """Show pxpipe proxy status."""
    from voly.pxpipe.proxy import PxpipeManager

    config = ctx.obj["config"]
    mgr = PxpipeManager(port=config.pxpipe.port, models=config.pxpipe.models)
    status = mgr.status()
    if status.running:
        click.echo(f"Running on port {status.port}")
        click.echo(f"URL: {status.proxy_url}")
        click.echo(f"Models: {status.models or 'pxpipe default'}")
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
    from voly.tools.mcp import MCPManager

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
    from voly.tools.mcp import MCPManager

    mgr = MCPManager()
    for name in ["github", "gitlab", "filesystem", "postgres"]:
        try:
            mgr.register_builtin(name)
        except ValueError:
            pass

    config = mgr.generate_claude_config() if fmt == "claude" else mgr.generate_opencode_config()
    click.echo(json.dumps(config, indent=2))
