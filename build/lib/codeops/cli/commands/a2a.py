"""A2A and AG-UI CLI command groups."""
from __future__ import annotations

import click


@click.group()
def a2a() -> None:
    """Manage A2A agents (agent-to-agent communication)."""
    pass


@a2a.command("status")
@click.pass_context
def a2a_status(ctx: click.Context) -> None:
    """Show A2A federation hub status."""
    from codeops.a2a.federation import create_federation_client, resolve_federation_url

    config = ctx.obj["config"]
    url = resolve_federation_url(config.a2a.federation_url)
    if not url:
        click.echo("Federation URL not configured.")
        click.echo("Set a2a.federation_url in codeops.yaml or CF_WORKER_A2A_URL in .env")
        raise SystemExit(1)

    client = create_federation_client(url)
    if not client:
        click.echo("Failed to create federation client.")
        raise SystemExit(1)

    try:
        health = client.health()
        agents = client.list_agents()
        tasks = client.list_tasks(limit=5)
    except Exception as exc:
        click.echo(f"Federation unreachable: {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(f"Federation: {url}")
    click.echo(f"Status: {health.get('status', 'unknown')}")
    click.echo(f"Queue: {health.get('queue', 'n/a')}")
    click.echo(f"Agents: {len(agents)}")
    click.echo(f"Recent tasks: {len(tasks)}")


@a2a.command("list")
@click.option("--remote", is_flag=True, help="List agents from federation hub")
@click.pass_context
def a2a_list(ctx: click.Context, remote: bool) -> None:
    """List discovered A2A agents."""
    from codeops.a2a import create_a2a_orchestrator

    config = ctx.obj["config"]
    orch = create_a2a_orchestrator(config.a2a.federation_url)

    if remote or config.a2a.federation_url:
        orch.refresh_federation()

    for url in config.a2a.remote_agents:
        orch.register_remote_agent(url)

    agents = orch.list_agents()
    if not agents:
        click.echo("No agents discovered.")
        return

    for card in agents:
        click.echo(f"\n{card.name} ({card.version})")
        click.echo(f"  URL: {card.url}")
        click.echo(f"  Skills: {len(card.skills)}")
        for skill in card.skills:
            desc = skill.description[:60] + ("..." if len(skill.description) > 60 else "")
            click.echo(f"    - {skill.name}: {desc}")


@a2a.command("call")
@click.argument("agent_name")
@click.argument("task")
@click.option("--remote", is_flag=True, help="Execute via CF agent worker (needs `codeops serve` + tunnel)")
@click.option("--cwd", default=None, help="Working directory")
@click.pass_context
def a2a_call(ctx: click.Context, agent_name: str, task: str, remote: bool, cwd: str | None) -> None:
    """Call an agent — locally or via CF agent worker."""
    config = ctx.obj["config"]

    if remote:
        import json
        import os
        import urllib.request

        agent_url = os.environ.get("CF_WORKER_AGENT_URL", "").strip()
        if not agent_url:
            click.echo("CF_WORKER_AGENT_URL not set", err=True)
            raise SystemExit(1)

        body = json.dumps({"task": task, "cwd": cwd}).encode()
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        req = urllib.request.Request(
            f"{agent_url.rstrip('/')}/agents/{agent_name}/run",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode())
        click.echo(f"Agent: {agent_name}")
        click.echo(f"Success: {data.get('success')}")
        if data.get("response"):
            click.echo(f"\n{data['response']}")
        if not data.get("success"):
            click.echo(f"Error: {data.get('error')}", err=True)
            raise SystemExit(1)
        return

    from codeops.pipeline import Pipeline

    pipeline = Pipeline(config)
    pipeline.setup_environment()

    orch = pipeline.a2a
    task_obj = orch.create_task(title=task[:100], description=task, agent_name=agent_name)

    click.echo(f"Task: {task_obj.id}")
    click.echo(f"Agent: {agent_name}")
    click.echo(f"State: {task_obj.state.value}")

    try:
        result = pipeline.run(task, agent=agent_name)
        if result.success:
            content = result.response.content if result.response else ""
            backend = getattr(orch, "_federation", None)
            if backend:
                backend.complete_task(task_obj.id, content)
            click.echo(f"\n{content}")
        else:
            backend = getattr(orch, "_federation", None)
            if backend:
                backend.fail_task(task_obj.id, result.error or "failed")
            click.echo(f"Failed: {result.error}", err=True)
            raise SystemExit(1)
    finally:
        pipeline.shutdown()


@a2a.command("deploy")
@click.option("--agent", "-a", default=None, help="Register a single agent by name from builtins")
@click.pass_context
def a2a_deploy(ctx: click.Context, agent: str | None) -> None:
    """Seed builtin agents into the federation hub."""
    from codeops.a2a import AgentCard, AgentSkill, create_a2a_orchestrator

    config = ctx.obj["config"]
    orch = create_a2a_orchestrator(config.a2a.federation_url)
    backend = getattr(orch, "_federation", None)
    if not backend:
        click.echo("Federation URL not configured.", err=True)
        raise SystemExit(1)

    # Builtin agents mirror codeops.yaml roles
    builtins = {
        "developer": ("Реализация кода", ["implement", "code", "feature"]),
        "architect": ("Архитектурное планирование", ["architecture", "design"]),
        "reviewer": ("Код-ревью", ["review", "code"]),
        "tester": ("Тестирование", ["test", "qa"]),
        "bugfixer": ("Исправление багов", ["bug", "fix"]),
        "devops": ("Деплой", ["deploy", "ci"]),
        "security": ("Безопасность", ["security", "audit"]),
    }

    base_url = config.a2a.federation_url.rstrip("/")
    names = [agent] if agent else list(builtins.keys())
    registered = 0

    for name in names:
        if name not in builtins:
            click.echo(f"Unknown builtin agent: {name}", err=True)
            continue
        desc, tags = builtins[name]
        card = AgentCard(
            name=name,
            description=desc,
            url=f"{base_url}/agents/{name}",
            skills=[
                AgentSkill(
                    id=f"{name}-skill",
                    name=name.title(),
                    description=desc,
                    tags=tags,
                )
            ],
        )
        backend.register_agent_card(card)
        registered += 1
        click.echo(f"Registered: {name}")

    click.echo(f"\n{registered} agent(s) registered at {base_url}")


@a2a.command("delegate")
@click.argument("task")
@click.option("--agent-url", "-u", default=None, help="Target agent URL")
@click.option("--agent", "-a", default=None, help="Target agent name (federation)")
@click.pass_context
def a2a_delegate(ctx: click.Context, task: str, agent_url: str | None, agent: str | None) -> None:
    """Delegate a task to an A2A agent."""
    from codeops.a2a import create_a2a_orchestrator

    config = ctx.obj["config"]
    orch = create_a2a_orchestrator(config.a2a.federation_url)

    for url in config.a2a.remote_agents:
        orch.register_remote_agent(url)

    if agent_url:
        orch.register_remote_agent(agent_url)

    if agent:
        task_obj = orch.create_task(title=task[:100], description=task, agent_name=agent)
        result = task_obj
    else:
        task_obj = orch.create_task(title=task[:100], description=task)
        result = orch.route_and_delegate(task_obj)

    click.echo(f"Task: {result.id}")
    click.echo(f"Routed to: {result.metadata.get('routed_to', agent or 'unknown')}")
    click.echo(f"State: {result.state.value}")
    if result.result:
        click.echo(f"\n{result.result}")


# ── AG-UI ─────────────────────────────────────────────────────────────────────

@click.group()
def agui() -> None:
    """Manage AG-UI gateway (agent↔UI communication)."""
    pass


@agui.command("status")
@click.pass_context
def agui_status(ctx: click.Context) -> None:
    """Show remote AG-UI worker status."""
    from codeops.agui.remote import create_remote_agui_client, resolve_agui_remote_url
    from codeops.spend.client import create_spend_client, resolve_spend_url

    config = ctx.obj["config"]
    url = resolve_agui_remote_url(config.agui.remote_url) or resolve_spend_url(config.spend.remote_url)
    if not url:
        click.echo("Remote AG-UI URL not configured.")
        return

    spend = create_spend_client(url)
    if spend:
        try:
            health = spend.health()
            click.echo(f"AG-UI/Spend worker: {url}")
            click.echo(f"Status: {health.get('status')}")
            click.echo(f"Features: {', '.join(health.get('features', []))}")
        except Exception as exc:
            click.echo(f"Worker unreachable: {exc}", err=True)


@agui.command("session")
@click.option("--session-id", default=None, help="Optional session id")
@click.pass_context
def agui_session(ctx: click.Context, session_id: str | None) -> None:
    """Create a remote AG-UI WebSocket session."""
    from codeops.agui.remote import create_remote_agui_client, resolve_agui_remote_url

    config = ctx.obj["config"]
    client = create_remote_agui_client(resolve_agui_remote_url(config.agui.remote_url))
    if not client:
        click.echo("Remote AG-UI not configured.", err=True)
        raise SystemExit(1)

    data = client.create_session(session_id or "")
    click.echo(f"Session: {data.get('session_id')}")
    click.echo(f"WebSocket: {data.get('ws_url')}")
    click.echo(f"Events API: {data.get('events_url')}")


@agui.command("start")
@click.option("--port", "-p", default=9101, help="Gateway port")
@click.pass_context
def agui_start(ctx: click.Context, port: int) -> None:
    """Start AG-UI gateway server."""
    from codeops.agui import AGUIGateway, AGUIContext

    gateway = AGUIGateway()
    ctx_obj = ctx.find_object(dict) or {}
    ctx_obj["agui_gateway"] = gateway

    ctx_obj2 = AGUIContext(conversation_id="default")
    session_id = gateway.create_session(ctx_obj2)
    click.echo(f"AG-UI Gateway running")
    click.echo(f"  Session: {session_id}")
    click.echo(f"  SSE endpoint: http://localhost:{port}/agui/{session_id}/events")
