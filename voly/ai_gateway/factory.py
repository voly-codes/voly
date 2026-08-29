"""Build a fully-configured AIGateway from a VOLYConfig.

``AIGateway.__init__`` takes bare constructor args (``account_id``,
``gateway_id``, ``api_token``) — it does not accept a ``VOLYConfig`` object.
Every governed policy (DLP, spend limits, cache, rate limits, fallback chain,
BYOK, request timeouts, project-scoped cache) lives on instance attributes
set *after* construction. This is that wiring, factored out so new callers
(the SDK, PlanRunner) get the same governed gateway ``Pipeline.gateway``
already builds instead of a bare, unconfigured instance.
"""

from __future__ import annotations

from typing import Any


def gateway_from_config(config: Any) -> Any:
    from voly.ai_gateway import AIGateway

    cfg = config.ai_gateway
    gw = AIGateway(
        account_id=cfg.account_id,
        gateway_id=cfg.gateway_id,
        api_token=cfg.api_token,
    )
    gw.cache.enabled = cfg.cache_enabled
    gw.cache.ttl_seconds = cfg.cache_ttl_seconds
    gw.cache.max_entries = cfg.cache_max_entries
    gw.cache.persist_dir = getattr(cfg, "cache_persist_dir", "")
    gw.rate_limit.enabled = cfg.rate_limits_enabled
    gw.rate_limit.requests_per_minute = cfg.rate_requests_per_minute
    gw.spend_limit.enabled = cfg.spend_limits_enabled
    gw.spend_limit.daily_budget_usd = cfg.spend_daily_budget_usd
    gw.spend_limit.per_agent_budget = cfg.spend_per_agent_budget
    gw.fallback.enabled = cfg.fallback_enabled
    gw.fallback.chain = cfg.fallback_chain
    gw.fallback.retries = cfg.fallback_retries
    gw.request_timeout_seconds = float(
        getattr(cfg, "request_timeout_seconds", 15.0) or 15.0
    )
    total_to = getattr(cfg, "request_total_timeout_seconds", 60.0)
    gw.request_total_timeout_seconds = float(total_to) if total_to else None
    gw.dlp.enabled = cfg.dlp_enabled
    gw.dlp.block_secrets = cfg.dlp_block_secrets
    gw.dlp.block_pii = cfg.dlp_block_pii
    gw.upstream = cfg.upstream
    gw.upstream_model = cfg.upstream_model
    gw.upstream_fallback_direct = cfg.upstream_fallback_direct
    gw.byok_enabled = getattr(cfg, "byok_enabled", False)
    gw.byok_providers = list(getattr(cfg, "byok_providers", None) or [])
    # Health checker must see BYOK providers as configured even without env
    # keys — otherwise tier resolution demotes premium roles.
    from voly.ai_gateway.health import get_checker

    get_checker().configure_byok(gw.byok_enabled, gw.byok_providers)
    gw._enabled = cfg.enabled
    # Scope the persistent cache to the project's repo state: the same task
    # text on a changed repo — or a different project — must miss.
    project_cwd = getattr(config, "default_cwd", "")
    if project_cwd:
        from voly.ai_gateway.project_state import project_fingerprint

        gw.cache_scope = project_fingerprint(project_cwd)
    return gw
