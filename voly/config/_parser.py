"""Parse raw YAML dict into a VOLYConfig instance."""

from __future__ import annotations

import os

from voly.config._types import (
    A2AConfig,
    AGUIConfig,
    AIGatewayConfig,
    AgentConfig,
    AuthConfig,
    VOLYConfig,
    CostPolicyConfig,
    DSPyConfig,
    HeadroomConfig,
    MCPConfig,
    MemoryConfig,
    ModelConfig,
    PlanConfig,
    RTKConfig,
    RegistryConfig,
    ScannerConfig,
    SpendConfig,
    TelemetryConfig,
    DEFAULT_PROXY_PORT,
)


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_users(raw_users: dict | str | None) -> dict[str, str]:
    """Accept YAML map or env-style ``user:pass,user2:pass2``."""
    if not raw_users:
        return {}
    if isinstance(raw_users, dict):
        return {str(k): str(v) for k, v in raw_users.items() if k}
    users: dict[str, str] = {}
    for part in str(raw_users).split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, _, password = part.partition(":")
        name, password = name.strip(), password.strip()
        if name:
            users[name] = password
    return users


def _parse_config(raw: dict) -> VOLYConfig:
    config = VOLYConfig()

    if "models" in raw:
        config.models = {
            name: ModelConfig(
                provider=m.get("provider", "anthropic"),
                model=m.get("model", name),
                api_key=os.path.expandvars(m.get("api_key", "")),
                base_url=m.get("base_url"),
                max_tokens=m.get("max_tokens", 8192),
                temperature=m.get("temperature", 0.0),
                extra=m.get("extra", {}),
            )
            for name, m in raw["models"].items()
        }

    if "agents" in raw:
        config.agents = {
            name: AgentConfig(
                name=name,
                description=a.get("description", ""),
                model=a.get("model"),
                executor=a.get("executor"),
                tools=a.get("tools", []),
                system_prompt=a.get("system_prompt"),
                max_turns=a.get("max_turns", 100),
                sandbox=a.get("sandbox", False),
            )
            for name, a in raw["agents"].items()
        }

    if "rtk" in raw:
        r = raw["rtk"]
        config.rtk = RTKConfig(
            enabled=r.get("enabled", True),
            binary_path=r.get("binary_path"),
            auto_install=r.get("auto_install", True),
        )

    if "headroom" in raw:
        h = raw["headroom"]
        config.headroom = HeadroomConfig(
            enabled=h.get("enabled", True),
            port=h.get("port", DEFAULT_PROXY_PORT),
            savings_profile=h.get("savings_profile", "agent-90"),
            memory_enabled=h.get("memory_enabled", False),
            code_graph=h.get("code_graph", False),
            lean_ctx=h.get("lean_ctx", False),
        )

    if "memory" in raw:
        m = raw["memory"]
        config.memory = MemoryConfig(
            enabled=m.get("enabled", False),
            backend=m.get("backend", "hybrid"),
            remote_url=os.path.expandvars(m.get("remote_url", "")),
            db_path=m.get("db_path", ".voly/memory.db"),
            embedding_model=m.get("embedding_model", "all-MiniLM-L6-v2"),
            max_memories=m.get("max_memories", 10000),
        )

    if not config.memory.remote_url:
        for key in ("CF_WORKER_MEMORY_URL", "MEMORY_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.memory.remote_url = env_url.rstrip("/")
                break

    if "mcp" in raw:
        c = raw["mcp"]
        config.mcp = MCPConfig(
            servers=c.get("servers", []),
            tools_allowlist=c.get("tools_allowlist", []),
        )

    if "a2a" in raw:
        a = raw["a2a"]
        config.a2a = A2AConfig(
            enabled=a.get("enabled", True),
            port=a.get("port", 9100),
            federation_url=os.path.expandvars(a.get("federation_url", "")),
            agent_discovery=a.get("agent_discovery", True),
            remote_agents=a.get("remote_agents", []),
            local_agents=a.get("local_agents", []),
            token=os.path.expandvars(a.get("token", "")),
            auto_dispatch=a.get("auto_dispatch", True),
            min_flags_for_dispatch=a.get("min_flags_for_dispatch", 2),
            task_timeout_seconds=float(a.get("task_timeout_seconds", 120.0)),
            execution_mode=a.get("execution_mode", "local"),
            lead_model=a.get("lead_model", ""),
            hybrid_code_gen=_parse_bool(a.get("hybrid_code_gen"), True),
            hybrid_require_cwd=_parse_bool(a.get("hybrid_require_cwd"), True),
            executor_default=a.get("executor_default", "claude-code"),
            executor_roles=list(a.get("executor_roles") or []),
        )

    if not config.a2a.federation_url:
        for key in ("CF_WORKER_A2A_URL", "A2A_FEDERATION_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.a2a.federation_url = env_url.rstrip("/")
                break

    if not config.a2a.token:
        config.a2a.token = os.environ.get("VOLY_A2A_TOKEN", "").strip()

    if "VOLY_A2A_HYBRID" in os.environ:
        config.a2a.hybrid_code_gen = _parse_bool(os.environ.get("VOLY_A2A_HYBRID"), True)

    if "agui" in raw:
        g = raw["agui"]
        config.agui = AGUIConfig(
            enabled=g.get("enabled", True),
            port=g.get("port", 9101),
            remote_url=os.path.expandvars(g.get("remote_url", "")),
            streaming=g.get("streaming", True),
            session_timeout_seconds=g.get("session_timeout_seconds", 3600),
            cors_origins=g.get("cors_origins", ["*"]),
        )

    if "spend" in raw:
        s = raw["spend"]
        config.spend = SpendConfig(
            enabled=s.get("enabled", True),
            remote_url=os.path.expandvars(s.get("remote_url", "")),
            daily_budget_usd=float(s.get("daily_budget_usd", 20.0)),
        )

    if not config.spend.remote_url:
        for key in ("CF_WORKER_SPEND_URL", "SPEND_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.spend.remote_url = env_url.rstrip("/")
                break

    if not config.agui.remote_url:
        for key in ("CF_WORKER_AGUI_URL", "AGUI_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.agui.remote_url = env_url.rstrip("/")
                break

    config.default_model = raw.get("default_model", "claude-sonnet")
    config.default_agent = raw.get("default_agent", "claude")
    config.default_cwd = os.path.expanduser(
        raw.get("default_cwd", "") or os.environ.get("VOLY_PROJECT_CWD", "")
    )

    if "registry" in raw:
        r = raw["registry"]
        marketplace_url = os.path.expandvars(r.get("marketplace_url", ""))
        config.registry = RegistryConfig(
            enabled=r.get("enabled", True),
            agents_path=r.get("agents_path", ".voly/agents"),
            skills_path=r.get("skills_path", ".voly/skills"),
            marketplace_url=marketplace_url,
        )

    if not config.registry.marketplace_url:
        for key in ("CF_WORKER_MARKETPLACE_URL", "MARKETPLACE_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.registry.marketplace_url = env_url
                break

    if "scanner" in raw:
        s = raw["scanner"]
        config.scanner = ScannerConfig(
            enabled=s.get("enabled", True),
            auto_scan=s.get("auto_scan", True),
            scan_depth=s.get("scan_depth", 3),
        )

    if "ai_gateway" in raw:
        g = raw["ai_gateway"]
        config.ai_gateway = AIGatewayConfig(
            enabled=g.get("enabled", True),
            provider=g.get("provider", "cloudflare"),
            account_id=os.path.expandvars(g.get("account_id", "")),
            gateway_id=os.path.expandvars(g.get("gateway_id", "default")),
            api_token=os.path.expandvars(g.get("api_token", "")),
            upstream=g.get("upstream", ""),
            upstream_model=g.get("upstream_model", ""),
            upstream_fallback_direct=g.get("upstream_fallback_direct", True),
            cache_enabled=g.get("caching", {}).get("enabled", True),
            cache_ttl_seconds=g.get("caching", {}).get("ttl_seconds", 3600),
            cache_max_entries=g.get("caching", {}).get("max_entries", 1000),
            rate_limits_enabled=g.get("rate_limits", {}).get("enabled", True),
            rate_requests_per_minute=g.get("rate_limits", {}).get("requests_per_minute", 60),
            spend_limits_enabled=g.get("spend_limits", {}).get("enabled", True),
            spend_daily_budget_usd=g.get("spend_limits", {}).get("daily_budget_usd", 20.0),
            spend_per_agent_budget=g.get("spend_limits", {}).get("per_agent_budget", {}),
            fallback_enabled=g.get("fallback", {}).get("enabled", True),
            fallback_chain=g.get("fallback", {}).get("chain", []),
            fallback_retries=g.get("fallback", {}).get("retries", 3),
            dlp_enabled=g.get("dlp", {}).get("enabled", False),
            dlp_block_secrets=g.get("dlp", {}).get("block_secrets", True),
            dlp_block_pii=g.get("dlp", {}).get("block_pii", True),
        )

    if "cost_policy" in raw:
        cp = raw["cost_policy"]
        config.cost_policy = CostPolicyConfig(
            enabled=cp.get("enabled", True),
            max_task_cost_usd=float(cp.get("max_task_cost_usd", 1.0)),
            stop_on_budget_exceeded=cp.get("stop_on_budget_exceeded", True),
            prefer_cheaper_model_for=cp.get(
                "prefer_cheaper_model_for", ["docs", "tests", "summarization"]
            ),
            cheaper_model=cp.get("cheaper_model", "deepseek-v4-flash"),
            cheaper_model_map=cp.get("cheaper_model_map", {}),
        )

    if "telemetry" in raw:
        t = raw["telemetry"]
        pipeline_url = os.path.expandvars(t.get("pipeline_url", ""))
        config.telemetry = TelemetryConfig(
            enabled=t.get("enabled", True),
            events_dir=t.get("events_dir", ".voly/events"),
            pipeline_url=pipeline_url,
            pipeline_enabled=t.get("pipeline_enabled", True),
            pipeline_timeout_seconds=float(t.get("pipeline_timeout_seconds", 5.0)),
            r2_enabled=t.get("r2_enabled", True),
            runs_dir=t.get("runs_dir", ".voly/runs"),
            watchdog_stale_factor=float(t.get("watchdog_stale_factor", 2.0)),
        )

    if not config.telemetry.pipeline_url:
        for key in ("CF_PIPELINE_TELEMETRY_ENDPOINT", "PIPELINE_TELEMETRY_ENDPOINT"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.telemetry.pipeline_url = env_url.rstrip("/")
                break

    if "dspy" in raw:
        d = raw["dspy"]
        config.dspy = DSPyConfig(
            enabled=d.get("enabled", False),
            mode=d.get("mode", "shadow"),
            model=d.get("model", ""),
            provider=d.get("provider", ""),
            programs_dir=d.get("programs_dir", ".voly/dspy/programs"),
            datasets_dir=d.get("datasets_dir", ".voly/dspy/datasets"),
            optimizer=d.get("optimizer", "bootstrap_fewshot"),
            min_examples=int(d.get("min_examples", 20)),
            compile_budget=d.get("compile_budget", "small"),
            agents=d.get("agents", []),
            routing_mode=d.get("routing_mode", "shadow"),
            active_tag=d.get("active_tag", "production"),
            shadow_tag=d.get("shadow_tag", "candidate"),
            program_overrides=d.get("program_overrides", {}),
        )

    # Env overrides for DSPy
    if os.environ.get("DSPY_ENABLED", "").lower() in ("1", "true", "yes"):
        config.dspy.enabled = True
    if os.environ.get("DSPY_MODE", ""):
        config.dspy.mode = os.environ["DSPY_MODE"]

    if "plan" in raw:
        p = raw["plan"]
        mode = str(p.get("mode", "shadow") or "shadow")
        on_fail = str(p.get("default_on_verify_fail", "stop") or "stop")
        if mode not in PlanConfig.VALID_MODES:
            mode = "shadow"
        if on_fail not in PlanConfig.VALID_ON_FAIL:
            on_fail = "stop"
        config.plan = PlanConfig(
            enabled=_parse_bool(p.get("enabled"), False),
            mode=mode,
            store_dir=str(p.get("store_dir", ".voly/plans") or ".voly/plans"),
            max_step_retries=int(p.get("max_step_retries", 1)),
            default_on_verify_fail=on_fail,
            command_timeout_seconds=float(p.get("command_timeout_seconds", 120.0)),
            allow_skip=_parse_bool(p.get("allow_skip"), False),
            executor_default=str(p.get("executor_default", "claude-code") or "claude-code"),
            step_timeout_seconds=int(p.get("step_timeout_seconds", 300)),
            max_turns=int(p.get("max_turns", 30)),
        )

    if os.environ.get("VOLY_PLAN_ENABLED", "").lower() in ("1", "true", "yes"):
        config.plan.enabled = True
    if os.environ.get("VOLY_PLAN_MODE", "").strip():
        m = os.environ["VOLY_PLAN_MODE"].strip().lower()
        if m in PlanConfig.VALID_MODES:
            config.plan.mode = m

    if "auth" in raw:
        a = raw["auth"]
        config.auth = AuthConfig(
            enabled=_parse_bool(a.get("enabled"), False),
            provider=str(a.get("provider", "local") or "local"),
            jwt_secret=os.path.expandvars(str(a.get("jwt_secret", "") or "")),
            jwt_algorithm=a.get("jwt_algorithm", "HS256"),
            access_token_expire_minutes=int(a.get("access_token_expire_minutes", 60)),
            users=_parse_users(a.get("users")),
            cors_origins=list(a.get("cors_origins", ["*"])),
            clerk_publishable_key=os.path.expandvars(
                str(a.get("clerk_publishable_key", "") or "")
            ),
            clerk_secret_key=os.path.expandvars(str(a.get("clerk_secret_key", "") or "")),
            clerk_jwks_url=os.path.expandvars(str(a.get("clerk_jwks_url", "") or "")),
            clerk_issuer=os.path.expandvars(str(a.get("clerk_issuer", "") or "")),
            clerk_audience=str(a.get("clerk_audience", "") or ""),
        )

    # Env overrides for auth (highest priority for secrets)
    if "VOLY_AUTH_ENABLED" in os.environ:
        config.auth.enabled = _parse_bool(os.environ.get("VOLY_AUTH_ENABLED"))
    if os.environ.get("VOLY_AUTH_PROVIDER", "").strip():
        config.auth.provider = os.environ["VOLY_AUTH_PROVIDER"].strip().lower()
    if os.environ.get("VOLY_JWT_SECRET", "").strip():
        config.auth.jwt_secret = os.environ["VOLY_JWT_SECRET"].strip()
    if os.environ.get("VOLY_AUTH_USERS", "").strip():
        config.auth.users = _parse_users(os.environ["VOLY_AUTH_USERS"])
    if os.environ.get("VOLY_AUTH_CORS", "").strip():
        config.auth.cors_origins = [
            o.strip() for o in os.environ["VOLY_AUTH_CORS"].split(",") if o.strip()
        ]
    # Clerk env (CLERK_* official names + VOLY_CLERK_* aliases)
    if os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip():
        config.auth.clerk_publishable_key = os.environ["CLERK_PUBLISHABLE_KEY"].strip()
    if os.environ.get("VOLY_CLERK_PUBLISHABLE_KEY", "").strip():
        config.auth.clerk_publishable_key = os.environ["VOLY_CLERK_PUBLISHABLE_KEY"].strip()
    if os.environ.get("CLERK_SECRET_KEY", "").strip():
        config.auth.clerk_secret_key = os.environ["CLERK_SECRET_KEY"].strip()
    if os.environ.get("VOLY_CLERK_SECRET_KEY", "").strip():
        config.auth.clerk_secret_key = os.environ["VOLY_CLERK_SECRET_KEY"].strip()
    if os.environ.get("CLERK_JWKS_URL", "").strip():
        config.auth.clerk_jwks_url = os.environ["CLERK_JWKS_URL"].strip()
    if os.environ.get("VOLY_CLERK_JWKS_URL", "").strip():
        config.auth.clerk_jwks_url = os.environ["VOLY_CLERK_JWKS_URL"].strip()
    if os.environ.get("CLERK_ISSUER", "").strip():
        config.auth.clerk_issuer = os.environ["CLERK_ISSUER"].strip()
    if os.environ.get("VOLY_CLERK_ISSUER", "").strip():
        config.auth.clerk_issuer = os.environ["VOLY_CLERK_ISSUER"].strip()
    if os.environ.get("CLERK_JWT_KEY", "").strip() and not config.auth.clerk_jwks_url:
        # PEM public key path is advanced; prefer JWKS URL. Ignore bare JWT key here.
        pass
    # Auto-enable clerk provider when publishable key present and provider still local
    if (
        config.auth.clerk_publishable_key
        and (config.auth.provider or "local").lower() == "local"
        and config.auth.enabled
        and not config.auth.jwt_secret
    ):
        config.auth.provider = "clerk"
    # Derive JWKS URL from issuer when missing
    if config.auth.clerk_issuer and not config.auth.clerk_jwks_url:
        iss = config.auth.clerk_issuer.rstrip("/")
        config.auth.clerk_jwks_url = f"{iss}/.well-known/jwks.json"

    return config
