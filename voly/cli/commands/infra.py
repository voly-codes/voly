"""Infrastructure CLI groups: memory, rtk, headroom, pxpipe, mcp."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

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
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
def memory_status(ctx: click.Context, cwd: Path | None) -> None:
    """Show remote memory backend status (Worker or Agent Memory)."""
    from voly.memory.client import create_remote_memory_client

    config = ctx.obj["config"]
    mem = config.memory
    click.echo(f"Backend: {mem.backend}")
    click.echo(f"Local SQLite: {mem.db_path}")

    if (mem.backend or "").lower() == "local":
        return

    if (mem.backend or "").lower() == "agent_memory":
        try:
            client = _configured_agent_memory_client(ctx, cwd=str(cwd or ""))
        except click.ClickException as exc:
            click.echo(str(exc), err=True)
            return
    else:
        client = create_remote_memory_client(
            backend=mem.backend,
            remote_url=mem.remote_url,
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


def _agent_memory_profile(config, cwd: str = "") -> str:  # type: ignore[no-untyped-def]
    from voly.memory.scope import resolve_memory_profile

    mem = config.memory
    project_cwd = cwd or str(getattr(config, "default_cwd", "") or "")
    return resolve_memory_profile(
        mem.agent_memory_profile,
        mode=getattr(mem, "agent_memory_profile_mode", "project"),
        cwd=project_cwd,
    )


def _configured_agent_memory_client(ctx: click.Context, *, cwd: str = ""):  # type: ignore[no-untyped-def]
    from voly.memory.client import create_remote_memory_client

    mem = ctx.obj["config"].memory
    if (mem.backend or "").lower() != "agent_memory":
        raise click.ClickException("memory.backend must be agent_memory")
    profile = _agent_memory_profile(ctx.obj["config"], cwd)
    if not profile:
        raise click.ClickException("project-scoped Agent Memory requires --cwd or default_cwd")
    client = create_remote_memory_client(
        backend=mem.backend,
        agent_memory_account_id=mem.agent_memory_account_id,
        agent_memory_namespace=mem.agent_memory_namespace,
        agent_memory_profile=profile,
    )
    if client is None:
        raise click.ClickException(
            "Agent Memory is not configured; set CF_ACCOUNT_ID and CLOUDFLARE_API_TOKEN"
        )
    return client


@memory.command("agent-memory-setup")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
def memory_agent_memory_setup(ctx: click.Context, cwd: Path | None) -> None:
    """Print the Wrangler command and VOLY scope selected for Agent Memory."""
    mem = ctx.obj["config"].memory
    namespace = mem.agent_memory_namespace or "voly"
    profile = _agent_memory_profile(ctx.obj["config"], str(cwd or ""))
    command = shlex.join(["npx", "wrangler", "agent-memory", "namespace", "create", namespace])
    click.echo(command)
    if not profile:
        click.echo("VOLY profile: unresolved (pass --cwd or configure default_cwd)")
        return
    click.echo(f"VOLY profile: {profile}")
    if profile == "default":
        click.echo(
            "Warning: profile 'default' is shared; configure a project/user/org-specific profile.",
            err=True,
        )


@memory.command("ingest")
@click.argument("conversation", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session-id", default="", help="Stable conversation/run identifier")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
def memory_ingest(
    ctx: click.Context, conversation: Path, session_id: str, cwd: Path | None
) -> None:
    """Ingest a bounded JSON conversation into the configured profile."""
    if conversation.stat().st_size > 1_000_000:
        raise click.ClickException("conversation file exceeds 1 MB")
    try:
        payload = json.loads(conversation.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"invalid conversation JSON: {exc}") from exc
    messages = payload.get("messages") if isinstance(payload, dict) else payload
    if not isinstance(messages, list):
        raise click.ClickException("conversation must be a JSON list or an object with messages")
    if len(messages) > 500:
        raise click.ClickException("conversation exceeds 500 messages")
    effective_session = session_id
    if not effective_session and isinstance(payload, dict):
        effective_session = str(payload.get("sessionId") or payload.get("session_id") or "")
    try:
        _configured_agent_memory_client(ctx, cwd=str(cwd or "")).ingest(
            messages, session_id=effective_session
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"ingested: {len(messages)} messages")


@memory.command("summary")
@click.option("--session-id", default="", help="Scope the Last Session summary")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
def memory_summary(ctx: click.Context, session_id: str, cwd: Path | None) -> None:
    """Print Cloudflare's Markdown summary for the configured profile."""
    summary = _configured_agent_memory_client(ctx, cwd=str(cwd or "")).get_summary(
        session_id=session_id
    )
    click.echo(summary or "(empty profile summary)")


@memory.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10)
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
def memory_search(ctx: click.Context, query: str, limit: int, cwd: Path | None) -> None:
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
    if (mem.backend or "").lower() == "agent_memory":
        profile = _agent_memory_profile(config, str(cwd or ""))
        if not profile:
            store.close()
            raise click.ClickException("project-scoped Agent Memory requires --cwd or default_cwd")
        results = store.scoped(profile).search_semantic(query, limit)
    else:
        results = store.search_semantic(query, limit)
    for entry in results:
        click.echo(f"[{entry.category}] {entry.title}")
        click.echo(f"  {entry.content[:120]}...")
    store.close()


@memory.command("compact")
@click.argument("handoff", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def memory_compact(ctx: click.Context, handoff: Path, cwd: Path) -> None:
    """Import a typed session handoff into scoped strategic memory."""
    from voly.memory.strategic import SessionHandoff, StrategicMemoryStore

    config = ctx.obj["config"].memory
    data = json.loads(handoff.read_text(encoding="utf-8"))
    contract = SessionHandoff.from_dict(data)
    path = Path(config.strategic_path)
    if not path.is_absolute():
        path = cwd / path
    added = StrategicMemoryStore(path).compact(contract)
    click.echo(f"compacted: {len(added)} new items → {path}")


@memory.command("context")
@click.argument("query")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.option("--project-id", default="")
@click.option("--organization-id", default="")
@click.pass_context
def memory_context(
    ctx: click.Context,
    query: str,
    cwd: Path,
    project_id: str,
    organization_id: str,
) -> None:
    """Preview budgeted strategic context for one scope."""
    from voly.memory.strategic import StrategicMemoryStore, project_scope_id

    config = ctx.obj["config"].memory
    path = Path(config.strategic_path)
    if not path.is_absolute():
        path = cwd / path
    memories = StrategicMemoryStore(path).retrieve(
        query,
        project_id=project_id or project_scope_id(cwd),
        organization_id=organization_id,
        token_budget=config.retrieval_token_budget,
        per_class_limit=config.retrieval_per_class_limit,
    )
    for item in memories:
        marker = " contradiction" if item.contradicts else ""
        click.echo(
            f"[{item.memory_class.value}/{item.kind.value}{marker}] {item.title}: {item.content}"
        )


@memory.command("export")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.option("--project-id", default="")
@click.pass_context
def memory_export(ctx: click.Context, cwd: Path, project_id: str) -> None:
    """Export non-private strategic memories as JSON."""
    from voly.memory.strategic import StrategicMemoryStore, project_scope_id

    config = ctx.obj["config"].memory
    path = Path(config.strategic_path)
    if not path.is_absolute():
        path = cwd / path
    payload = StrategicMemoryStore(path).export(project_id=project_id or project_scope_id(cwd))
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


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


@mcp.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind address (0.0.0.0 to expose)")
@click.option("--port", "-p", default=7799, type=int, help="Port (default 7799)")
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["streamable-http", "sse", "stdio"]),
    help="MCP transport (default streamable-http)",
)
@click.pass_context
def mcp_serve(ctx: click.Context, host: str, port: int, transport: str) -> None:
    """Serve VOLY itself as an MCP server (the other direction from `list`/`config`).

    Lets Cloudflare OS, Claude Desktop, or any MCP host start and follow VOLY
    runs. Requires the `mcp` extra: pip install -e ".[mcp]"
    """
    try:
        from voly.mcp.server import build_server, serve
    except ImportError as exc:
        raise click.ClickException(
            f'MCP SDK not installed ({exc}). Install it with: pip install -e ".[mcp]"'
        ) from exc

    if transport != "stdio":
        click.echo(f"VOLY MCP server → http://{host}:{port}/mcp")
    serve(build_server(), transport=transport, host=host, port=port)
