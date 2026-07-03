"""Tests for AI Gateway."""

import json
import time

from voly.ai_gateway import (
    AIGateway,
    CacheConfig,
    RateLimit,
    SpendLimit,
    FallbackChain,
    DLPConfig,
    GatewayMetrics,
    GatewayProvider,
    FallbackStrategy,
)


def test_cache_config_get_set() -> None:
    cache = CacheConfig(ttl_seconds=10)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"

    cache.set("key2", "value2")
    assert cache.stats()["active"] == 2


def test_cache_config_expiry() -> None:
    cache = CacheConfig(ttl_seconds=0)
    cache.set("key1", "value1")
    time.sleep(0.01)
    assert cache.get("key1") is None


def test_cache_config_max_entries() -> None:
    cache = CacheConfig(max_entries=3, ttl_seconds=3600)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")
    cache.set("d", "4")
    assert len(cache._store) <= 3


def test_cache_config_flush() -> None:
    cache = CacheConfig(ttl_seconds=3600)
    cache.set("a", "1")
    cache.set("b", "2")
    assert cache.stats()["active"] == 2
    cache.flush()
    assert cache.stats()["active"] == 0


def test_spend_limit_check() -> None:
    limit = SpendLimit(daily_budget_usd=10.0)
    assert limit.check(5.0) is True
    limit.record(5.0)
    assert limit.check(6.0) is False


def test_spend_limit_per_agent() -> None:
    limit = SpendLimit(daily_budget_usd=100.0, per_agent_budget={"architect": 5.0, "developer": 10.0})
    assert limit.check(3.0, "architect") is True

    limit.record(3.0, "architect")
    assert limit.check(3.0, "architect") is False


def test_spend_limit_record() -> None:
    limit = SpendLimit(daily_budget_usd=10.0)
    limit.record(3.0, "developer")
    limit.record(2.0, "architect")
    assert limit.spent_today == 5.0


def test_dlp_secrets_detection() -> None:
    dlp = DLPConfig(enabled=True, block_secrets=True)
    violations = dlp.scan("Here is my API key: sk-1234567890abcdef")
    assert len(violations) > 0

    violations = dlp.scan("Hello world, no secrets here")
    assert len(violations) == 0


def test_dlp_pii_detection() -> None:
    dlp = DLPConfig(enabled=True, block_pii=True)
    violations = dlp.scan("Email: test@example.com, SSN: 123-45-6789")
    assert len(violations) > 0


def test_fallback_chain() -> None:
    chain = FallbackChain(
        strategy=FallbackStrategy.SEQUENTIAL,
        chain=[
            {"provider": "anthropic", "model": "claude-sonnet"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ],
        retries=2,
    )
    assert len(chain.chain) == 2
    assert chain.retries == 2


def test_gateway_metrics() -> None:
    m = GatewayMetrics()
    m.record_request("anthropic", "claude-sonnet", 1000, 0.003)
    m.record_request("openai", "gpt-4o", 500, 0.001)
    m.record_cache_hit()
    m.record_cache_miss()
    m.record_fallback()
    m.record_dlp_block()
    m.record_error()

    d = m.to_dict()
    assert d["total_requests"] == 2
    assert d["cache_hits"] == 1
    assert d["cache_misses"] == 1
    assert d["fallbacks_used"] == 1
    assert d["dlp_blocks"] == 1
    assert d["errors"] == 1
    assert d["by_provider"]["anthropic"] == 1
    assert d["by_provider"]["openai"] == 1


def test_gateway_creation() -> None:
    gw = AIGateway(
        account_id="test-account",
        gateway_id="test-gateway",
        api_token="test-token",
    )
    assert gw.provider == GatewayProvider.CLOUDFLARE
    assert gw.base_url == "https://gateway.ai.cloudflare.com/v1/test-account/test-gateway"
    assert gw.cache.enabled is True
    assert gw.rate_limit.enabled is True


def test_gateway_cache_key() -> None:
    gw = AIGateway()
    key1 = gw._cache_key([{"role": "user", "content": "hello"}], "gpt-4o", "openai", "", "")
    key2 = gw._cache_key([{"role": "user", "content": "hello"}], "gpt-4o", "openai", "", "")
    key3 = gw._cache_key([{"role": "user", "content": "world"}], "gpt-4o", "openai", "", "")
    assert key1 == key2
    assert key1 != key3


def test_gateway_cost_estimation() -> None:
    gw = AIGateway()
    cost = gw._estimate_cost("claude-sonnet-4-5-20250929", "anthropic", 4000)
    assert cost > 0

    cost = gw._calculate_cost("claude-sonnet", "anthropic", {"input_tokens": 10000, "output_tokens": 1000})
    assert cost > 0


def test_rate_limit_config() -> None:
    rl = RateLimit(requests_per_minute=30)
    assert rl.requests_per_minute == 30


def test_gateway_to_dict() -> None:
    gw = AIGateway(account_id="acct123", gateway_id="gw1")
    d = gw.to_dict()
    assert "provider" in d
    assert "cache" in d
    assert "rate_limit" in d
    assert "spend_limit" in d
    assert "fallback" in d
    assert "dlp" in d
    assert "metrics" in d


def test_gateway_from_config() -> None:
    gw = AIGateway()
    gw.from_config({
        "enabled": True,
        "account_id": "acct-123",
        "gateway_id": "my-gateway",
        "caching": {"enabled": False, "ttl_seconds": 1800},
        "rate_limits": {"requests_per_minute": 30},
        "spend_limits": {"daily_budget_usd": 50},
        "fallback": {"chain": [{"provider": "openai", "model": "gpt-4o"}]},
        "dlp": {"enabled": True, "block_secrets": True},
    })
    assert gw._enabled is True
    assert gw.account_id == "acct-123"
    assert gw.cache.enabled is False
    assert gw.cache.ttl_seconds == 1800
    assert gw.rate_limit.requests_per_minute == 30
    assert gw.spend_limit.daily_budget_usd == 50
    assert len(gw.fallback.chain) == 1
    assert gw.dlp.enabled is True


def test_gateway_enabled_by_default() -> None:
    gw = AIGateway()
    assert gw.enabled is True
    assert gw.cloudflare_enabled is False  # no account_id — middleware on, CF routing off


def test_gateway_cloudflare_enabled_with_account() -> None:
    gw = AIGateway(account_id="acct-123", gateway_id="gw-1")
    assert gw.enabled is True
    assert gw.cloudflare_enabled is True


def test_gateway_middleware_runs_without_cloudflare() -> None:
    """DLP and rate-limit run even when Cloudflare is not configured."""
    gw = AIGateway()
    gw.dlp.enabled = True

    result = gw.chat(
        messages=[{"role": "user", "content": "my api key: sk-1234567890abcdef"}],
        model="claude-sonnet",
        provider_name="anthropic",
    )
    assert result.get("dlp_blocked") is True


def test_gateway_disabled_bypasses_middleware() -> None:
    """When _enabled=False, DLP and other middleware are fully skipped."""
    gw = AIGateway()
    gw._enabled = False
    gw.dlp.enabled = True
    # With gateway disabled, _direct_call is called — network will fail, but DLP is NOT checked
    result = gw.chat(
        messages=[{"role": "user", "content": "api_key: sk-1234567890abcdef"}],
        model="claude-sonnet",
        provider_name="anthropic",
    )
    # No dlp_blocked — middleware was bypassed (error from direct call instead)
    assert result.get("dlp_blocked") is not True
