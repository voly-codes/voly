"""AIGateway — centralised LLM routing layer with CF AI Gateway support."""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import urllib.request
from typing import Any, Callable

from .models import (
    GatewayProvider, FallbackStrategy,
    RateLimit, SpendLimit, CacheConfig, FallbackChain, DLPConfig, GatewayMetrics,
)
from .providers import _GatewayProvidersMixin
from codeops.telemetry import _estimate_cost as _telemetry_estimate_cost

_log = logging.getLogger("codeops.ai_gateway")

# Providers natively supported by Cloudflare AI Gateway
_CF_PROVIDERS = frozenset({"anthropic", "openai", "google-ai-studio", "deepseek"})


class AIGateway(_GatewayProvidersMixin):
    def __init__(
        self,
        provider: GatewayProvider = GatewayProvider.CLOUDFLARE,
        account_id: str = "",
        gateway_id: str = "default",
        api_token: str = "",
    ):
        self.provider    = provider
        self.account_id  = account_id
        self.gateway_id  = gateway_id
        self.api_token   = api_token

        self.cache       = CacheConfig()
        self.rate_limit  = RateLimit()
        self.spend_limit = SpendLimit()
        self.fallback    = FallbackChain()
        self.dlp         = DLPConfig()
        self.metrics     = GatewayMetrics()
        self._enabled    = True
        self._transports: dict[str, Callable] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def cloudflare_enabled(self) -> bool:
        return self._enabled and bool(self.account_id)

    @property
    def base_url(self) -> str:
        if self.provider == GatewayProvider.CLOUDFLARE:
            return f"https://gateway.ai.cloudflare.com/v1/{self.account_id}/{self.gateway_id}"
        return ""

    def provider_url(self, provider_name: str) -> str:
        return f"{self.base_url}/{provider_name}"

    # ── Main entry point ─────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider_name: str = "anthropic",
        max_tokens: int = 8192,
        temperature: float = 0.0,
        system: str | None = None,
        agent: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self._enabled:
            return self._direct_call(messages, model, provider_name, max_tokens, temperature, system, tools=tools)

        violations = self.dlp.scan(json.dumps(messages))
        if violations:
            self.metrics.record_dlp_block()
            return {"error": f"DLP blocked: {violations}", "content": "", "dlp_blocked": True}

        cache_key = self._cache_key(messages, model, provider_name, system or "", str(kwargs))
        if self.cache.enabled:
            cached = self.cache.get(cache_key)
            if cached:
                self.metrics.record_cache_hit()
                return json.loads(cached)
        self.metrics.record_cache_miss()

        if self.rate_limit.enabled and self.metrics.requests_in_last_minute() >= self.rate_limit.requests_per_minute:
            self.metrics.record_rate_limited()
            return {"error": "Rate limit exceeded", "content": "", "rate_limited": True}

        estimated_cost = self._estimate_cost(model, provider_name, len(json.dumps(messages)))
        if not self.spend_limit.check(estimated_cost, agent):
            return {"error": "Spend limit exceeded", "content": "", "spend_limited": True}

        if self.cloudflare_enabled and provider_name in _CF_PROVIDERS:
            result = self._gateway_call(messages, model, provider_name, max_tokens, temperature, system, tools=tools, **kwargs)
        else:
            result = self._direct_call(messages, model, provider_name, max_tokens, temperature, system, tools=tools)
            if result.get("error") and self.fallback.enabled and self.fallback.chain:
                result = self._direct_fallback(result, messages, max_tokens, temperature, system, tools, **kwargs)

        self.spend_limit.record(estimated_cost, agent)
        cost = self._calculate_cost(model, provider_name, result.get("usage", {}))
        self.metrics.record_request(provider_name, model, result.get("usage", {}).get("total_tokens", 0), cost)

        if self.cache.enabled and not result.get("error"):
            self.cache.set(cache_key, json.dumps(result))

        return result

    # ── Gateway call with fallback chain (CF-routed providers) ───────────────────

    def _gateway_call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider_name: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        all_models = [{"provider": provider_name, "model": model}] + self.fallback.chain
        last_error = None

        for attempt, spec in enumerate(all_models):
            prov = spec.get("provider", provider_name)
            mdl  = spec.get("model", model)

            if attempt > 0:
                self.metrics.record_fallback()
                _log.info("Fallback attempt %d: provider=%s model=%s (reason: %s)", attempt, prov, mdl, last_error)

            try:
                result = self._single_call(messages, mdl, prov, max_tokens, temperature, system, tools=tools, **kwargs)
                if not result.get("error"):
                    if attempt > 0:
                        result["fallback_used"]     = True
                        result["fallback_provider"] = prov
                        result["fallback_model"]    = mdl
                        _log.info("Fallback succeeded: provider=%s model=%s", prov, mdl)
                    return result
                last_error = result.get("error")
                _log.warning("provider=%s model=%s returned error: %s", prov, mdl, last_error)
            except Exception as e:
                last_error = str(e)
                _log.warning("provider=%s model=%s raised exception: %s", prov, mdl, last_error)

            if attempt >= self.fallback.retries:
                break

        self.metrics.record_error()
        _log.error("All models failed. Last error: %s", last_error)
        return {"error": f"All models failed. Last: {last_error}", "content": ""}

    def _single_call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider_name: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = self.provider_url(provider_name)
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "codeops/0.1.0",
        }
        if self.api_token:
            headers["cf-aig-authorization"] = f"Bearer {self.api_token}"

        if provider_name == "anthropic":
            headers["x-api-key"] = os.environ.get("ANTHROPIC_API_KEY", "")
            headers["anthropic-version"] = "2023-06-01"
            return self._call_anthropic(url, messages, model, max_tokens, temperature, system, headers, tools=tools)
        elif provider_name == "openai":
            headers["Authorization"] = f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"
            return self._call_openai(url, messages, model, max_tokens, temperature, system, headers, tools=tools)
        elif provider_name in ("google-ai-studio", "google"):
            headers["x-goog-api-key"] = os.environ.get("GOOGLE_API_KEY", "")
            return self._call_google(url, messages, model, max_tokens, temperature, system, headers, tools=tools)
        elif provider_name == "deepseek":
            headers["Authorization"] = f"Bearer {os.environ.get('DEEPSEEK_API_KEY', '')}"
            return self._call_openai(url, messages, model, max_tokens, temperature, system, headers, tools=tools)
        else:
            headers["x-api-key"] = os.environ.get("ANTHROPIC_API_KEY", "")
            headers["anthropic-version"] = "2023-06-01"
            try:
                return self._call_anthropic(url, messages, model, max_tokens, temperature, system, headers, tools=tools)
            except Exception:
                headers["Authorization"] = f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"
                return self._call_openai(url, messages, model, max_tokens, temperature, system, headers, tools=tools)

    # ── Fallback for non-CF providers ────────────────────────────────────────────

    def _direct_fallback(
        self,
        primary_result: dict[str, Any],
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        primary_error = primary_result.get("error", "unknown error")
        last_error    = primary_error
        _log.warning("Primary call failed (%s) — trying %d fallback(s)", last_error, len(self.fallback.chain))

        for i, spec in enumerate(self.fallback.chain[: self.fallback.retries]):
            self.metrics.record_fallback()
            fb_prov  = spec.get("provider", "")
            fb_model = spec.get("model", "")
            if not fb_prov or not fb_model:
                continue
            _log.info("Fallback attempt %d: provider=%s model=%s", i + 1, fb_prov, fb_model)
            try:
                if self.cloudflare_enabled and fb_prov in _CF_PROVIDERS:
                    fb = self._single_call(messages, fb_model, fb_prov, max_tokens, temperature, system, tools=tools, **kwargs)
                else:
                    fb = self._direct_call(messages, fb_model, fb_prov, max_tokens, temperature, system, tools=tools)
                if not fb.get("error"):
                    _log.info("Fallback succeeded: provider=%s model=%s", fb_prov, fb_model)
                    fb["fallback_used"]     = True
                    fb["fallback_provider"] = fb_prov
                    fb["fallback_model"]    = fb_model
                    fb["fallback_reason"]   = primary_error
                    return fb
                last_error = fb.get("error", last_error)
                _log.warning("Fallback %d failed: %s", i + 1, last_error)
            except Exception as exc:
                last_error = str(exc)
                _log.warning("Fallback %d raised exception: %s", i + 1, last_error)

        self.metrics.record_error()
        _log.error("All fallbacks exhausted. Last error: %s", last_error)
        return {"error": f"All fallbacks failed. Last: {last_error}", "content": ""}

    # ── Cost helpers ─────────────────────────────────────────────────────────────

    def _cache_key(self, messages: list, model: str, provider: str, system: str, extra: str) -> str:
        raw = json.dumps(
            {"messages": messages, "model": model, "provider": provider, "system": system, "extra": extra},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _estimate_cost(self, model: str, provider: str, input_chars: int) -> float:
        return _telemetry_estimate_cost(model, input_chars // 4, 0)

    def _calculate_cost(self, model: str, provider: str, usage: dict[str, int]) -> float:
        return _telemetry_estimate_cost(
            model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        )

    # ── CF Gateway log fetching ───────────────────────────────────────────────────

    def fetch_cf_logs(
        self, since_hours: int = 24, limit: int = 100, provider: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.cloudflare_enabled or not self.api_token:
            return []
        since  = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)
        params: dict[str, str] = {
            "per_page": str(min(limit, 100)), "page": "1",
            "order_by": "created_at", "direction": "desc",
            "filter[start_date]": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if provider:
            params["filter[provider]"] = provider
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/ai-gateway/gateways/{self.gateway_id}/logs"
        )
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(
            f"{url}?{qs}",
            headers={"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode()).get("result", [])
        except Exception:
            return []

    def fetch_cf_metrics(self, since_hours: int = 24) -> dict[str, Any]:
        logs = self.fetch_cf_logs(since_hours=since_hours, limit=100)
        if not logs:
            return {"available": False, "reason": "No CF credentials or no logs found"}

        total      = len(logs)
        tokens_in  = sum(e.get("prompt_tokens") or 0 for e in logs)
        tokens_out = sum(e.get("response_tokens") or 0 for e in logs)
        cost       = sum(float(e.get("cost") or 0) for e in logs)
        cached_count  = sum(1 for e in logs if e.get("cached"))
        success_count = sum(1 for e in logs if not (e.get("errors_count") or e.get("status_code", 200) >= 400))
        error_count   = total - success_count
        durations     = sorted(e["duration"] for e in logs if e.get("duration"))

        def _pct(data: list[int], p: float) -> int:
            return data[max(0, int(len(data) * p / 100) - 1)] if data else 0

        by_provider: dict[str, int] = {}
        by_model:    dict[str, int] = {}
        by_provider_tokens: dict[str, dict[str, Any]] = {}
        for e in logs:
            prov = e.get("provider", "unknown")
            mdl  = e.get("model",    "unknown")
            by_provider[prov] = by_provider.get(prov, 0) + 1
            by_model[mdl]     = by_model.get(mdl, 0) + 1
            pt = by_provider_tokens.setdefault(prov, {"in": 0, "out": 0, "cost": 0.0})
            pt["in"]   += e.get("prompt_tokens")   or 0
            pt["out"]  += e.get("response_tokens")  or 0
            pt["cost"] += float(e.get("cost") or 0)

        return {
            "available": True, "since_hours": since_hours,
            "requests": {
                "total": total, "success": success_count, "errors": error_count,
                "error_rate": round(error_count / total, 3) if total else 0.0,
                "cached": cached_count, "cache_miss": total - cached_count,
                "cache_hit_rate": round(cached_count / total, 3) if total else 0.0,
            },
            "tokens": {"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out},
            "cost_usd": round(cost, 6),
            "latency_ms": {
                "avg": round(sum(durations) / len(durations)) if durations else 0,
                "p50": _pct(durations, 50), "p95": _pct(durations, 95), "p99": _pct(durations, 99),
                "min": durations[0] if durations else 0, "max": durations[-1] if durations else 0,
            },
            "by_provider": by_provider,
            "by_provider_tokens": {
                p: {"in": v["in"], "out": v["out"], "cost_usd": round(v["cost"], 6)}
                for p, v in by_provider_tokens.items()
            },
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])[:10]),
        }

    # ── Serialisation ─────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider":   self.provider.value,
            "account_id": self.account_id[:8] + "..." if self.account_id else "",
            "gateway_id": self.gateway_id,
            "enabled":    self.enabled,
            "cache":      self.cache.to_dict(),
            "rate_limit": self.rate_limit.to_dict(),
            "spend_limit":self.spend_limit.to_dict(),
            "fallback":   self.fallback.to_dict(),
            "dlp":        self.dlp.to_dict(),
            "metrics":    self.metrics.to_dict(),
        }

    def from_config(self, config: dict[str, Any]) -> None:
        self._enabled   = config.get("enabled",    True)
        self.account_id = config.get("account_id", self.account_id)
        self.gateway_id = config.get("gateway_id", self.gateway_id)
        self.api_token  = config.get("api_token",  self.api_token)

        if c := config.get("caching"):
            self.cache.enabled     = c.get("enabled",     True)
            self.cache.ttl_seconds = c.get("ttl_seconds", 3600)
            self.cache.max_entries = c.get("max_entries", 1000)
        if r := config.get("rate_limits"):
            self.rate_limit.enabled             = r.get("enabled",             True)
            self.rate_limit.requests_per_minute = r.get("requests_per_minute", 60)
        if s := config.get("spend_limits"):
            self.spend_limit.enabled          = s.get("enabled",          True)
            self.spend_limit.daily_budget_usd = s.get("daily_budget_usd", 20.0)
            self.spend_limit.per_agent_budget = s.get("per_agent_budget", {})
        if f := config.get("fallback"):
            self.fallback.enabled = f.get("enabled", True)
            self.fallback.chain   = f.get("chain",   [])
            self.fallback.retries = f.get("retries", 3)
        if d := config.get("dlp"):
            self.dlp.enabled        = d.get("enabled",        False)
            self.dlp.block_secrets  = d.get("block_secrets",  True)
            self.dlp.block_pii      = d.get("block_pii",      True)
            self.dlp.block_patterns = d.get("block_patterns", [])
