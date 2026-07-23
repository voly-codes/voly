"""Analytics commands: compare, savings, balance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

_NO_API_KEY = "No API key"


# ── compare ───────────────────────────────────────────────────────────────────

@click.command()
@click.argument("task")
@click.option("--model", "-m", default=None, help="Model alias (e.g. deepseek-v4-flash)")
@click.option("--runs", "-n", default=1, help="Number of runs to average")
@click.pass_context
def compare(ctx: click.Context, task: str, model: str | None, runs: int) -> None:
    """Compare token usage: direct API call vs VOLY pipeline."""
    import time
    from voly.pipeline import Pipeline
    from voly.telemetry import _estimate_cost

    config = ctx.obj["config"]
    pipeline = Pipeline(config)

    route = pipeline.router.route(task)
    if model:
        model_cfg = config.get_model_config(model)
        route.model = model
        route.provider = model_cfg.provider

    resolved_model = config.get_model_config(route.model).model
    provider = route.provider

    click.echo(f"\nComparing: {resolved_model} ({provider})")
    click.echo(f"Task: {task[:80]}{'...' if len(task) > 80 else ''}")
    click.echo(f"Runs: {runs}\n")

    click.echo("Running direct API call...")
    direct_msgs = [{"role": "user", "content": task}]
    direct_results = []
    for _ in range(runs):
        t0 = time.monotonic()
        res = pipeline.gateway._direct_call(
            messages=direct_msgs,
            model=resolved_model,
            provider_name=provider,
            max_tokens=config.get_model_config(route.model).max_tokens,
            temperature=0.0,
            system=None,
        )
        elapsed = (time.monotonic() - t0) * 1000
        usage = res.get("usage", {})
        direct_results.append({
            "in": usage.get("input_tokens", 0),
            "out": usage.get("output_tokens", 0),
            "ms": elapsed,
        })

    d_in  = sum(r["in"]  for r in direct_results) // runs
    d_out = sum(r["out"] for r in direct_results) // runs
    d_ms  = sum(r["ms"]  for r in direct_results) / runs
    d_cost = _estimate_cost(resolved_model, d_in, d_out)

    click.echo("Running via VOLY pipeline...")
    pipeline_results = []
    for _ in range(runs):
        t0 = time.monotonic()
        pres = pipeline.run(task, force_model=model)
        elapsed = (time.monotonic() - t0) * 1000
        pipeline_results.append({
            "in":  pres.response.usage.input_tokens if pres.response else 0,
            "out": pres.response.usage.output_tokens if pres.response else 0,
            "ms":  elapsed,
            "saved_rtk":      pres.tokens_saved_by_rtk,
            "saved_headroom": pres.tokens_saved_by_headroom,
            "memory_hits":    len(pres.memory_hits),
            "cache_hit":      pres.event.gateway.cache_hit if pres.event else False,
            "routing_score":  pres.route.routing_score if pres.route else 0.0,
            "agent":          pres.route.agent if pres.route else "?",
            "skill_ids":      pres.event.skill_ids if pres.event else [],
        })

    p_in   = sum(r["in"]  for r in pipeline_results) // runs
    p_out  = sum(r["out"] for r in pipeline_results) // runs
    p_ms   = sum(r["ms"]  for r in pipeline_results) / runs
    p_cost = _estimate_cost(resolved_model, p_in, p_out)
    saved_rtk      = sum(r["saved_rtk"]      for r in pipeline_results) // runs
    saved_headroom = sum(r["saved_headroom"] for r in pipeline_results) // runs
    cache_hit      = any(r["cache_hit"]      for r in pipeline_results)
    memory_hits    = sum(r["memory_hits"]    for r in pipeline_results) // runs
    last = pipeline_results[-1]

    overhead_in = p_in - d_in
    net_saved   = saved_rtk + saved_headroom
    net_delta   = overhead_in - net_saved
    cost_delta  = p_cost - d_cost

    click.echo()
    click.echo("=" * 62)
    click.echo(f"  {'Metric':<28}  {'Direct':>10}  {'VOLY':>10}  {'Delta':>8}")
    click.echo("  " + "─" * 58)
    click.echo(f"  {'Tokens IN':<28}  {d_in:>10,}  {p_in:>10,}  {overhead_in:>+8,}")
    click.echo(f"  {'Tokens OUT':<28}  {d_out:>10,}  {p_out:>10,}  {p_out - d_out:>+8,}")
    click.echo(f"  {'Total tokens':<28}  {d_in+d_out:>10,}  {p_in+p_out:>10,}  {(p_in+p_out)-(d_in+d_out):>+8,}")
    click.echo(f"  {'Cost USD':<28}  ${d_cost:>9.5f}  ${p_cost:>9.5f}  {cost_delta:>+8.5f}")
    click.echo(f"  {'Duration ms':<28}  {d_ms:>10.0f}  {p_ms:>10.0f}  {p_ms - d_ms:>+8.0f}")
    click.echo("  " + "─" * 58)
    click.echo(f"  {'Saved by RTK':<28}  {'':>10}  {saved_rtk:>10,}")
    click.echo(f"  {'Saved by Headroom':<28}  {'':>10}  {saved_headroom:>10,}")
    click.echo(f"  {'Context overhead (net)':<28}  {'':>10}  {net_delta:>+10,}")
    click.echo(f"  {'Memory hits injected':<28}  {'':>10}  {memory_hits:>10,}")
    click.echo(f"  {'Cache hit':<28}  {'':>10}  {'yes' if cache_hit else 'no':>10}")
    click.echo("  " + "─" * 58)
    click.echo(f"  {'Agent selected':<28}  {'':>10}  {last['agent']:>10}")
    click.echo(f"  {'Routing score':<28}  {'':>10}  {last['routing_score']:>10.2f}")
    if last["skill_ids"]:
        click.echo(f"  {'Skills':<28}  {'':>10}  {', '.join(last['skill_ids'][:3])}")
    click.echo("=" * 62)

    if net_delta > 0:
        click.echo(f"\n  VOLY adds +{net_delta:,} net tokens vs direct call.")
    elif net_delta < 0:
        click.echo(f"\n  VOLY SAVES {-net_delta:,} net tokens vs direct (RTK/cache working).")
    else:
        click.echo("\n  No net token difference.")


# ── savings ───────────────────────────────────────────────────────────────────

@click.command()
@click.option("--days", "-d", default=0, help="Filter events by last N days (0 = all time)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def savings(ctx: click.Context, days: int, as_json: bool) -> None:
    """Show savings report based on measured telemetry data."""
    import time
    from voly.telemetry import _estimate_cost

    # Executor types that never go through AIGateway — no token/cost data in telemetry
    _EXECUTOR_MODELS = frozenset({"claude-code", "cursor", "opencode", "zen", "wrangler", "mimo", "deepseek"})
    # Baseline for routing comparison
    _BASELINE_MODEL = "claude-sonnet-4-6"
    _SONNET_IN_PER_TOKEN = 0.003 / 1000

    events_dir = Path(".voly/events")
    events: list[dict] = []

    if events_dir.exists():
        cutoff = (time.time() - days * 86400) if days > 0 else 0.0
        for f in sorted(events_dir.glob("*.json")):
            if days > 0 and f.stat().st_mtime < cutoff:
                continue
            try:
                events.append(json.loads(f.read_text()))
            except Exception:
                pass

    completed = [e for e in events if e.get("status") == "completed"]
    errors     = [e for e in events if e.get("status") not in ("completed", None)]

    total_cost        = sum(e.get("cost_usd", 0.0) for e in completed)
    total_in          = sum(e.get("tokens", {}).get("input", 0) for e in completed)
    total_out         = sum(e.get("tokens", {}).get("output", 0) for e in completed)
    total_duration_ms = sum(e.get("duration_ms", 0) for e in completed)

    # ── Cache savings: cache_hit events saved a full API call ────────────
    # When cache_hit=True, the event has tokens from the cached response.
    # Actual cost was $0; saved cost = what the model would have charged.
    cache_hits = 0
    saved_by_cache = 0.0
    for e in completed:
        if not e.get("gateway", {}).get("cache_hit"):
            continue
        cache_hits += 1
        mdl = e.get("model") or ""
        tok = e.get("tokens", {})
        saved_by_cache += _estimate_cost(mdl, tok.get("input", 0), tok.get("output", 0))

    # ── Routing savings: cheaper model vs claude-sonnet-4-6 baseline ─────
    # Only pipeline events with known model and real token counts.
    saved_by_routing = 0.0
    routing_tasks    = 0
    for e in completed:
        mdl = e.get("model") or ""
        if not mdl or mdl in _EXECUTOR_MODELS or mdl == _BASELINE_MODEL:
            continue
        tok = e.get("tokens", {})
        inp, out = tok.get("input", 0), tok.get("output", 0)
        if inp == 0 and out == 0:
            continue
        delta = _estimate_cost(_BASELINE_MODEL, inp, out) - e.get("cost_usd", 0.0)
        if delta > 0:
            saved_by_routing += delta
            routing_tasks += 1

    # ── RTK / Headroom savings: tokens.saved_* from pipeline telemetry ───
    # These fields are set only when RTK/Headroom actually compressed context
    # before sending to the gateway. Converted to cost at Sonnet input price.
    rtk_tokens    = sum(e.get("tokens", {}).get("saved_rtk", 0) for e in completed)
    hdroom_tokens = sum(e.get("tokens", {}).get("saved_headroom", 0) for e in completed)
    saved_by_rtk     = rtk_tokens    * _SONNET_IN_PER_TOKEN
    saved_by_headroom = hdroom_tokens * _SONNET_IN_PER_TOKEN

    # ── Billing fallback chain ────────────────────────────────────────────
    fallback_used = sum(1 for e in completed if e.get("gateway", {}).get("fallback_used"))
    # Free executors: zen and wrangler have $0 API cost
    free_exec_tasks = sum(1 for e in completed if e.get("executor") in ("zen", "wrangler"))

    # ── Productivity ─────────────────────────────────────────────────────
    scored = [e for e in completed if e.get("automation_score") is not None]
    avg_automation    = sum(e.get("automation_score", 0) for e in scored) / len(scored) if scored else 0.0
    manual_removed    = sum(e.get("manual_steps_removed", 0) for e in completed)

    # ── By agent / by model ───────────────────────────────────────────────
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for e in completed:
        ag  = e.get("agent") or "unknown"
        mdl = e.get("model") or "unknown"
        cost = e.get("cost_usd", 0.0)
        tok  = e.get("tokens", {})
        by_agent.setdefault(ag,  {"tasks": 0, "cost": 0.0, "tokens": 0})
        by_model.setdefault(mdl, {"tasks": 0, "cost": 0.0})
        by_agent[ag]["tasks"]  += 1
        by_agent[ag]["cost"]   += cost
        by_agent[ag]["tokens"] += tok.get("input", 0) + tok.get("output", 0)
        by_model[mdl]["tasks"] += 1
        by_model[mdl]["cost"]  += cost

    period_label = f"last {days}d" if days else "all time"

    if as_json:
        click.echo(json.dumps({
            "period_days": days or "all",
            "tasks": {"completed": len(completed), "errors": len(errors)},
            "tokens": {"input": total_in, "output": total_out},
            "cost": {
                "actual_usd":              round(total_cost, 4),
                "saved_by_cache_usd":      round(saved_by_cache, 4),
                "saved_by_routing_usd":    round(saved_by_routing, 4),
                "saved_by_rtk_usd":        round(saved_by_rtk, 4),
                "saved_by_headroom_usd":   round(saved_by_headroom, 4),
                "routing_baseline_model":  _BASELINE_MODEL,
                "routing_tasks":           routing_tasks,
            },
            "cache_hits": cache_hits,
            "fallback_triggered": fallback_used,
            "free_executor_tasks": free_exec_tasks,
            "automation": {
                "avg_score": round(avg_automation, 3),
                "manual_steps_removed": manual_removed,
            },
            "rtk_tokens_saved": rtk_tokens,
            "headroom_tokens_saved": hdroom_tokens,
            "by_agent": by_agent,
            "by_model": by_model,
        }, indent=2))
        return

    W = 60
    click.echo(f"\n{'═' * W}")
    click.echo(f"  VOLY Savings Report  ({period_label})")
    click.echo(f"{'═' * W}")
    click.echo(f"\n  Tasks       {len(completed):>5} completed   {len(errors):>4} errors")
    if scored:
        click.echo(f"  Automation  {avg_automation*100:>5.0f}% avg · {manual_removed} manual steps removed")
    click.echo(f"  Tokens      {total_in+total_out:>8,}  ({total_in:,} in / {total_out:,} out)")
    click.echo(f"  Duration    {total_duration_ms/1000:>8.1f}s total")

    click.echo(f"\n  ── Actual spend {'─'*42}")
    click.echo(f"  {'Actual cost (telemetry)':<38}  ${total_cost:>8.4f}")

    click.echo(f"\n  ── Measurable savings (from telemetry) {'─'*20}")
    click.echo(f"  {'Cheaper model routing':<38}  ${saved_by_routing:>8.4f}  ({routing_tasks} tasks vs {_BASELINE_MODEL})")
    click.echo(f"  {'Cache hits':<38}  ${saved_by_cache:>8.4f}  ({cache_hits} hits)")
    if rtk_tokens > 0:
        click.echo(f"  {'RTK token compression':<38}  {rtk_tokens:>9,} tok  (≈${saved_by_rtk:.4f})")
    if hdroom_tokens > 0:
        click.echo(f"  {'Headroom compression':<38}  {hdroom_tokens:>9,} tok  (≈${saved_by_headroom:.4f})")
    if fallback_used > 0:
        click.echo(f"  {'Billing fallback triggered':<38}  {fallback_used:>9} times")
    if free_exec_tasks > 0:
        click.echo(f"  {'Free executor tasks (zen/wrangler)':<38}  {free_exec_tasks:>9} tasks  ($0 API cost)")

    if by_agent:
        click.echo(f"\n  By agent")
        click.echo(f"  {'─' * 44}")
        for ag, stats in sorted(by_agent.items(), key=lambda x: -x[1]["cost"]):
            click.echo(f"  {'  ' + ag:<30}  ${stats['cost']:>8.4f}  ({stats['tasks']} tasks)")

    if by_model:
        click.echo(f"\n  By model")
        click.echo(f"  {'─' * 44}")
        for mdl, stats in sorted(by_model.items(), key=lambda x: -x[1]["cost"]):
            short = mdl[-28:] if len(mdl) > 28 else mdl
            click.echo(f"  {'  ' + short:<30}  ${stats['cost']:>8.4f}  ({stats['tasks']} tasks)")

    click.echo(f"\n{'═' * W}\n")


# ── balance ───────────────────────────────────────────────────────────────────

@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def balance(as_json: bool) -> None:
    """Check API balance for all configured providers."""
    import urllib.request

    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    results: list[dict] = []

    def _http_get(url: str, headers: dict) -> dict | None:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read())
        except Exception:
            return None

    ds_key = os.getenv("DEEPSEEK_API_KEY", "")
    if ds_key:
        data = _http_get(
            "https://api.deepseek.com/user/balance",
            {"Authorization": f"Bearer {ds_key}", "Accept": "application/json"},
        )
        if data and data.get("balance_infos"):
            info = data["balance_infos"][0]
            total = float(info.get("total_balance", 0))
            results.append({
                "provider": "DeepSeek",
                "balance": total,
                "currency": info.get("currency", "USD"),
                "available": data.get("is_available", True),
                "url": "https://platform.deepseek.com/usage",
            })
        else:
            results.append({"provider": "DeepSeek", "balance": None, "error": "API unavailable"})
    else:
        results.append({"provider": "DeepSeek", "balance": None, "error": _NO_API_KEY})

    mimo_key = os.getenv("MIMO_API_KEY", "")
    results.append({
        "provider": "MiMo",
        "balance": None,
        "note": "No public balance API" if mimo_key else _NO_API_KEY,
        "url": "https://xiaomimimo.com/console",
    })

    oc_key = os.getenv("OPENCODE_API_KEY", "")
    results.append({
        "provider": "OpenCode (Zen/Go)",
        "balance": None,
        "note": "No public balance API" if oc_key else _NO_API_KEY,
        "url": "https://opencode.ai/settings",
    })

    anth_key = os.getenv("ANTHROPIC_API_KEY", "")
    results.append({
        "provider": "Anthropic (Claude)",
        "balance": None,
        "note": "Check console" if anth_key else _NO_API_KEY,
        "url": "https://console.anthropic.com/settings/billing",
    })

    # BYOK: keys for these providers live in CF Secrets Store — a missing local
    # env key does not mean "not configured" (balance stays provider-side).
    try:
        from voly.ai_gateway.credentials import BYOK_PROVIDER_SLUGS
        from voly.config import load_config

        cfg = load_config()
        if getattr(cfg.ai_gateway, "byok_enabled", False):
            restricted = list(getattr(cfg.ai_gateway, "byok_providers", None) or [])
            covered = sorted({
                slug for name, slug in BYOK_PROVIDER_SLUGS.items()
                if not restricted or name in restricted or slug in restricted
            })
            for r in results:
                r_provider = str(r.get("provider", "")).lower()
                if r.get("balance") is None and any(s.split("-")[0] in r_provider for s in covered):
                    r["note"] = "via cf-byok (key stored in CF gateway)"
    except Exception:  # noqa: BLE001 — balance must not fail on config problems
        pass

    if as_json:
        click.echo(json.dumps(results, indent=2))
        return

    click.echo("\nProvider Balances")
    click.echo("=" * 50)
    for r in results:
        name = r["provider"]
        if r.get("balance") is not None:
            bal   = r["balance"]
            cur   = r.get("currency", "USD")
            avail = "" if r.get("available", True) else " (unavailable)"
            warn  = " LOW" if bal < 1.0 else (" <5$" if bal < 5.0 else " OK")
            click.echo(f"\n  {name}")
            click.echo(f"    Balance: {cur} {bal:.2f}{warn}{avail}")
        else:
            note = r.get("note") or r.get("error", "")
            url  = r.get("url", "")
            click.echo(f"\n  {name}")
            click.echo(f"    Balance: — ({note})")
            if url:
                click.echo(f"    Dashboard: {url}")
    click.echo()
