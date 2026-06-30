"""GET /api/gateway/status — AI Gateway status and metrics."""

from __future__ import annotations

import fastapi

router = fastapi.APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.get("/status")
def gateway_status(request: fastapi.Request) -> dict:
    state = request.app.state.app
    config = state.config

    from codeops.ai_gateway import AIGateway

    gw = AIGateway(
        account_id=config.ai_gateway.account_id if config else "",
        gateway_id=config.ai_gateway.gateway_id if config else "default",
        api_token=config.ai_gateway.api_token if config else "",
    )
    if config:
        gw._enabled = config.ai_gateway.enabled
        gw.cache.enabled = config.ai_gateway.cache_enabled
        gw.cache.ttl_seconds = config.ai_gateway.cache_ttl_seconds
        gw.cache.max_entries = config.ai_gateway.cache_max_entries
        gw.rate_limit.enabled = config.ai_gateway.rate_limits_enabled
        gw.rate_limit.requests_per_minute = config.ai_gateway.rate_requests_per_minute
        gw.spend_limit.enabled = config.ai_gateway.spend_limits_enabled
        gw.spend_limit.daily_budget_usd = config.ai_gateway.spend_daily_budget_usd
        gw.spend_limit.per_agent_budget = config.ai_gateway.spend_per_agent_budget
        gw.fallback.enabled = config.ai_gateway.fallback_enabled
        gw.fallback.chain = config.ai_gateway.fallback_chain
        gw.fallback.retries = config.ai_gateway.fallback_retries
        gw.dlp.enabled = config.ai_gateway.dlp_enabled
        gw.dlp.block_secrets = config.ai_gateway.dlp_block_secrets
        gw.dlp.block_pii = config.ai_gateway.dlp_block_pii

    return gw.to_dict()
