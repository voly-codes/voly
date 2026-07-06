"""Platform CLI groups: registry, model, ai_gateway, scan, match."""
from __future__ import annotations

import json
from pathlib import Path

import click


# ── Scan ──────────────────────────────────────────────────────────────────────

@click.command("scan")
@click.option("--save/--no-save", default=True, show_default=True, help="Save generated skills to .voly/skills/")
@click.pass_context
def scan_project(ctx: click.Context, save: bool) -> None:
    """Scan project and generate PROJECT skills from docs + stack."""
    from pathlib import Path

    from voly.registry.loader import save_skill_yaml, skill_from_dict
    from voly.registry.project_skill_extractor import generate_project_skills
    from voly.registry.skills import create_skill_registry
    from voly.scanner import ProjectScanner

    scanner = ProjectScanner()
    profile = scanner.scan()

    click.echo(f"Project: {profile.name}")
    click.echo(f"Architecture: {profile.architecture}")
    if profile.languages:
        click.echo("Languages: " + ", ".join(
            f"{l.name}" + (f" {l.version}" if l.version else "") for l in profile.languages
        ))
    if profile.frameworks:
        click.echo("Frameworks: " + ", ".join(f.name for f in profile.frameworks))
    if profile.infrastructure.databases:
        click.echo("Databases: " + ", ".join(profile.infrastructure.databases))
    if profile.test_frameworks:
        click.echo("Tests: " + ", ".join(profile.test_frameworks))
    if profile.linter_tools:
        click.echo("Linters: " + ", ".join(profile.linter_tools))

    skills = generate_project_skills(Path.cwd(), profile)
    click.echo(f"\nGenerated {len(skills)} project skill(s):")
    for s in skills:
        src = s.get("metadata", {}).get("source_file", "profile")
        click.echo(f"  {s['id']} — {s['name']}  [{src}]")

    if not save:
        return

    config = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    config_dir = Path(config_path).parent if config_path else Path.cwd()
    reg = create_skill_registry(
        skills_path=config.registry.skills_path,
        marketplace_url=config.registry.marketplace_url,
        config_dir=config_dir,
    )
    saved = 0
    if reg.skills_path:
        for skill_dict in skills:
            skill_obj = skill_from_dict(skill_dict)
            save_skill_yaml(skill_obj, reg.skills_path / f"{skill_obj.id}.yaml")
            saved += 1
    click.echo(f"\nSaved {saved} skill(s) → {reg.skills_path}")


# ── Match ─────────────────────────────────────────────────────────────────────

@click.command("match")
@click.argument("task")
@click.pass_context
def match_task(ctx: click.Context, task: str) -> None:
    """Match task to agent, model, skills and tools."""
    from voly.pipeline import Pipeline

    config = ctx.obj["config"]
    pipeline = Pipeline(config)

    result = pipeline.match_agent_for_task(task)
    click.echo(f"Task: {task}")
    click.echo(f"Agent: {result['agent']}")
    click.echo(f"Model: {result['model']} ({result['provider']})")
    click.echo(f"Tools: {result['tools']}")
    click.echo(f"Skills matched: {len(result['skills'])}")
    for skill in result["skills"]:
        click.echo(f"  - [{skill.source.value}] {skill.name}")


# ── Registry ──────────────────────────────────────────────────────────────────

@click.group()
def registry() -> None:
    """Manage Agent Registry and Skill Registry."""
    pass


@registry.command("agents")
@click.pass_context
def registry_agents(ctx: click.Context) -> None:
    """List all registered agents."""
    from voly.registry.agents import AgentRegistry

    reg = AgentRegistry()
    for agent in reg.list_all():
        click.echo(f"\n{agent.name} — {agent.description}")
        click.echo(f"  capabilities: {', '.join(agent.capabilities)}")
        click.echo(f"  skills: {', '.join(agent.required_skills)}")
        click.echo(f"  tools: {', '.join(agent.supported_tools)}")
        click.echo(f"  model: {agent.preferred_model}")


@registry.command("skills")
@click.option("--agent", "-a", default=None)
@click.option("--tag", "-t", default=None)
@click.option("--lang", "-l", default=None)
@click.pass_context
def registry_skills(ctx: click.Context, agent: str | None, tag: str | None, lang: str | None) -> None:
    """List all registered skills."""
    from pathlib import Path

    from voly.registry.skills import create_skill_registry

    config = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    config_dir = Path(config_path).parent if config_path else Path.cwd()
    reg = create_skill_registry(
        skills_path=config.registry.skills_path,
        marketplace_url=config.registry.marketplace_url,
        config_dir=config_dir,
    )
    kwargs: dict = {}
    if agent:
        kwargs["agent"] = agent
    if tag:
        kwargs["tags"] = [tag]
    if lang:
        kwargs["language"] = lang

    skills = reg.search(**kwargs) if kwargs else reg.index.list_all()
    for skill in skills:
        click.echo(f"[{skill.source.value}] {skill.name}")
        click.echo(f"  tags: {', '.join(skill.tags)} | agents: {', '.join(skill.compatible_agents)}")


@registry.command("import-external")
@click.option(
    "--claude-skills-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, exists=True),
    default=None,
    help="Path to the claude-skills repo root",
)
@click.option(
    "--agency-agents-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, exists=True),
    default=None,
    help="Path to the agency-agents repo root",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False, exists=False),
    default=None,
    help="Output catalog file (default: .voly/catalog/external-registry.yaml)",
)
@click.option("--publish-skills/--no-publish-skills", default=False, help="Publish imported skills to marketplace if configured")
@click.option("--publish-plugins/--no-publish-plugins", default=False, help="Publish imported plugins to marketplace if configured")
@click.pass_context
def registry_import_external(
    ctx: click.Context,
    claude_skills_root: Path | None,
    agency_agents_root: Path | None,
    output: Path | None,
    publish_skills: bool,
    publish_plugins: bool,
) -> None:
    """Build a local registry snapshot from claude-skills and agency-agents."""
    from voly.registry.external_catalog import (
        build_external_catalog,
        catalog_path_for,
        load_external_catalog,
        write_external_catalog,
    )
    from voly.registry.marketplace import MarketplaceClient

    config_path = ctx.obj.get("config_path")
    base_dir = Path(config_path).parent if config_path else Path.cwd()
    claude_root = claude_skills_root or base_dir.parent / "claude-skills"
    agency_root = agency_agents_root or base_dir.parent / "agency-agents"
    out_path = output or catalog_path_for(base_dir)

    if not claude_root.exists():
        raise click.ClickException(f"claude-skills root not found: {claude_root}")
    if not agency_root.exists():
        raise click.ClickException(f"agency-agents root not found: {agency_root}")

    catalog = build_external_catalog(claude_root, agency_root)
    write_external_catalog(catalog, out_path)
    click.echo(
        f"Wrote catalog → {out_path} (skills={catalog['counts']['skills']}, agents={catalog['counts']['agents']}, plugins={catalog['counts']['plugins']})"
    )

    if publish_skills or publish_plugins:
        url = ctx.obj["config"].registry.marketplace_url
        if not url:
            click.echo("Marketplace URL not configured; skipping publish.")
            return
        client = MarketplaceClient(url)
        loaded = load_external_catalog(out_path)
        published_skills = 0
        published_plugins = 0
        if publish_skills:
            for skill in loaded.get("skills", []):
                try:
                    client.publish_skill(skill)
                    published_skills += 1
                except Exception as exc:
                    click.echo(f"Publish failed for skill {skill.get('id', '?')}: {exc}", err=True)
        if publish_plugins:
            for plugin in loaded.get("plugins", []):
                if plugin.get("kind") != "claude-plugin":
                    continue
                try:
                    client.publish_plugin(plugin)
                    published_plugins += 1
                except Exception as exc:
                    click.echo(f"Publish failed for plugin {plugin.get('name', '?')}: {exc}", err=True)
        if publish_skills:
            click.echo(f"Published {published_skills} skill(s) to marketplace.")
        if publish_plugins:
            click.echo(f"Published {published_plugins} plugin(s) to marketplace.")


# ── Model ─────────────────────────────────────────────────────────────────────

@click.group()
def model() -> None:
    """Manage model routing."""
    pass


@model.command("list")
@click.pass_context
def model_list(ctx: click.Context) -> None:
    """List available models with pricing."""
    from voly.model_router import ModelRouter

    router = ModelRouter()
    for m in router.list_models():
        click.echo(f"{m.name} ({m.provider})")
        click.echo(f"  input:  ${m.input_cost_per_1m}/1M tokens")
        click.echo(f"  output: ${m.output_cost_per_1m}/1M tokens")
        click.echo(f"  latency: {m.avg_latency_ms}ms | window: {m.context_window}")
        click.echo()


@model.command("route")
@click.argument("task")
@click.option("--prefer-cost", is_flag=True, help="Prefer cheaper models")
@click.option("--prefer-speed", is_flag=True, help="Prefer faster models")
@click.pass_context
def model_route(ctx: click.Context, task: str, prefer_cost: bool, prefer_speed: bool) -> None:
    """Route task to optimal model."""
    from voly.model_router import ModelRouter

    router = ModelRouter()
    m = router.route(task=task, prefer_cost=prefer_cost, prefer_speed=prefer_speed)
    click.echo(f"Task: {task[:80]}...")
    click.echo(f"Model: {m.name} ({m.provider})")
    click.echo(f"Cost: ${m.input_cost_per_1m}/1M in | ${m.output_cost_per_1m}/1M out")
    click.echo(f"Latency: ~{m.avg_latency_ms}ms")


# ── AI Gateway ────────────────────────────────────────────────────────────────

@click.group()
def ai_gateway() -> None:
    """Manage AI Gateway (Cloudflare AI Gateway)."""
    pass


def _make_gateway(ctx: click.Context):
    """Build AIGateway from config."""
    from voly.ai_gateway import AIGateway

    config = ctx.obj["config"]
    gw = AIGateway(
        account_id=config.ai_gateway.account_id,
        gateway_id=config.ai_gateway.gateway_id,
        api_token=config.ai_gateway.api_token,
    )
    gw._enabled = config.ai_gateway.enabled
    return gw, config


@ai_gateway.command("status")
@click.pass_context
def ai_gateway_status(ctx: click.Context) -> None:
    """Show AI Gateway status and metrics."""
    gw, _ = _make_gateway(ctx)
    d = gw.to_dict()
    click.echo(f"AI Gateway: {d['provider']}")
    click.echo(f"Enabled: {d['enabled']}")
    click.echo(f"Gateway: {d['gateway_id']}")
    click.echo()
    click.echo(f"Cache: {d['cache']}")
    click.echo(f"Rate limits: {d['rate_limit']}")
    click.echo(f"Spend limits: {d['spend_limit']}")
    click.echo(f"Fallback chain: {len(d['fallback']['chain'])} models")
    click.echo(f"DLP: {d['dlp']}")
    click.echo()
    click.echo(f"Metrics: {json.dumps(d['metrics'], indent=2)}")


@ai_gateway.command("metrics")
@click.option("--hours", "-H", default=24, help="Look-back window in hours (default: 24)")
@click.option("--provider", "-p", default=None, help="Filter by provider")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def ai_gateway_metrics(ctx: click.Context, hours: int, provider: str | None, as_json: bool) -> None:
    """Fetch real-time metrics from Cloudflare AI Gateway API."""
    gw, config = _make_gateway(ctx)

    if not gw.cloudflare_enabled:
        click.echo("CF AI Gateway not configured — set account_id + api_token in voly.yaml")
        click.echo("Tip: export CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_API_TOKEN=...")
        return

    click.echo(f"Fetching CF AI Gateway metrics (last {hours}h)...")
    m = gw.fetch_cf_metrics(since_hours=hours)

    if as_json:
        click.echo(json.dumps(m, indent=2))
        return

    if not m.get("available"):
        click.echo(f"No data: {m.get('reason', 'unknown')}")
        return

    req = m["requests"]
    tok = m["tokens"]
    lat = m["latency_ms"]

    click.echo()
    click.echo(f"  Gateway:  {config.ai_gateway.gateway_id}")
    click.echo(f"  Period:   last {hours}h  ({req['total']} requests)")
    click.echo()
    click.echo("  ── Requests ─────────────────────────────────")
    click.echo(f"  Total:        {req['total']:>8,}")
    click.echo(f"  Success:      {req['success']:>8,}")
    click.echo(f"  Errors:       {req['errors']:>8,}  ({req['error_rate']*100:.1f}%)")
    click.echo(f"  Cache hits:   {req['cached']:>8,}  ({req['cache_hit_rate']*100:.1f}%)")
    click.echo(f"  Cache misses: {req['cache_miss']:>8,}")
    click.echo()
    click.echo("  ── Latency (ms) ─────────────────────────────")
    click.echo(f"  avg={lat['avg']}  p50={lat['p50']}  p95={lat['p95']}  p99={lat['p99']}")
    click.echo()
    click.echo("  ── Tokens & Cost ────────────────────────────")
    click.echo(f"  Input:   {tok['input']:>12,} tokens")
    click.echo(f"  Output:  {tok['output']:>12,} tokens")
    click.echo(f"  Cost:    ${m['cost_usd']:>11.4f}")
    click.echo()

    if m.get("by_provider"):
        by_pt = m.get("by_provider_tokens", {})
        click.echo("  ── By Provider ──────────────────────────────")
        click.echo(f"  {'Provider':<22} {'Reqs':>6}  {'In':>10}  {'Out':>10}  {'Cost':>9}")
        click.echo(f"  {'─'*22}  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*9}")
        for prov, cnt in sorted(m["by_provider"].items(), key=lambda x: -x[1]):
            pt = by_pt.get(prov, {})
            click.echo(
                f"  {prov:<22} {cnt:>6,}  {pt.get('in', 0):>10,}  "
                f"{pt.get('out', 0):>10,}  ${pt.get('cost_usd', 0):>8.4f}"
            )

    if m.get("by_model"):
        click.echo("  ── Top Models ───────────────────────────────")
        max_cnt = max(m["by_model"].values())
        for mdl, cnt in list(m["by_model"].items())[:10]:
            bar = "■" * min(int(cnt / max_cnt * 16), 16)
            click.echo(f"  {mdl:<32} {cnt:>5,}  {bar}")


@ai_gateway.command("flush-cache")
@click.pass_context
def ai_gateway_flush(ctx: click.Context) -> None:
    """Flush AI Gateway response cache."""
    gw, _ = _make_gateway(ctx)
    gw.cache.flush()
    click.echo("Cache flushed")


@ai_gateway.command("test")
@click.option("--message", "-m", default="Hello, what is VOLY?")
@click.option("--provider", "-p", default="anthropic")
@click.option("--model", "-M", default="claude-sonnet-4-5-20250929")
@click.pass_context
def ai_gateway_test(ctx: click.Context, message: str, provider: str, model: str) -> None:
    """Test AI Gateway with a single request."""
    import time
    from voly.ai_gateway import AIGateway

    config = ctx.obj["config"]
    if not config.ai_gateway.enabled or not config.ai_gateway.account_id:
        click.echo("AI Gateway is not enabled. Set account_id in voly.yaml")
        return

    gw = AIGateway(
        account_id=config.ai_gateway.account_id,
        gateway_id=config.ai_gateway.gateway_id,
        api_token=config.ai_gateway.api_token,
    )
    gw._enabled = True
    gw.cache.enabled = config.ai_gateway.cache_enabled
    gw.rate_limit.enabled = config.ai_gateway.rate_limits_enabled

    click.echo(f"Sending test request via AI Gateway...")
    click.echo(f"  Provider: {provider}  Model: {model}")
    click.echo(f"  Message: {message}")

    start = time.time()
    result = gw.chat(
        messages=[{"role": "user", "content": message}],
        model=model,
        provider_name=provider,
        max_tokens=256,
    )
    elapsed = (time.time() - start) * 1000

    if result.get("error"):
        click.echo(f"Error: {result['error']}")
    else:
        click.echo(f"\nResponse ({elapsed:.0f}ms):")
        click.echo(result.get("content", "")[:500])
        usage = result.get("usage", {})
        click.echo(f"\nTokens: {usage.get('total_tokens', '?')}")
