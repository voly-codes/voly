"""AIGateway — centralised LLM routing layer with CF AI Gateway support."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import urllib.request
import urllib.error
from typing import Any, Callable

from .models import (
    GatewayProvider, FallbackStrategy,
    RateLimit, SpendLimit, CacheConfig, FallbackChain, DLPConfig, GatewayMetrics,
)
from codeops.telemetry import _estimate_cost as _telemetry_estimate_cost

# Providers natively supported by Cloudflare AI Gateway
_CF_PROVIDERS = frozenset({"anthropic", "openai", "google-ai-studio", "deepseek"})


class AIGateway:
    def __init__(
        self,
        provider: GatewayProvider = GatewayProvider.CLOUDFLARE,
        account_id: str = "",
        gateway_id: str = "default",
        api_token: str = "",
    ):
        self.provider = provider
        self.account_id = account_id
        self.gateway_id = gateway_id
        self.api_token = api_token

        self.cache = CacheConfig()
        self.rate_limit = RateLimit()
        self.spend_limit = SpendLimit()
        self.fallback = FallbackChain()
        self.dlp = DLPConfig()
        self.metrics = GatewayMetrics()
        self._enabled = True
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

        self.spend_limit.record(estimated_cost, agent)
        cost = self._calculate_cost(model, provider_name, result.get("usage", {}))
        self.metrics.record_request(provider_name, model, result.get("usage", {}).get("total_tokens", 0), cost)

        if self.cache.enabled and not result.get("error"):
            self.cache.set(cache_key, json.dumps(result))

        return result

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
            if attempt > 0:
                self.metrics.record_fallback()

            prov = spec.get("provider", provider_name)
            mdl  = spec.get("model", model)

            try:
                result = self._single_call(messages, mdl, prov, max_tokens, temperature, system, tools=tools, **kwargs)
                if not result.get("error"):
                    return result
                last_error = result.get("error")
            except Exception as e:
                last_error = str(e)

            if attempt >= self.fallback.retries:
                break

        self.metrics.record_error()
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

    def _call_anthropic(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        req = urllib.request.Request(
            f"{url}/v1/messages",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"Anthropic {e.code}: {msg}") from e

        return {
            "content": "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ),
            "model": data.get("model", model),
            "usage": {
                "input_tokens":  data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens":  (data.get("usage", {}).get("input_tokens", 0)
                                  + data.get("usage", {}).get("output_tokens", 0)),
            },
        }

    def _call_openai(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        body: dict[str, Any] = {
            "model": model, "messages": msgs,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if tools:
            body["tools"] = tools

        req = urllib.request.Request(
            f"{url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"OpenAI {e.code}: {msg}") from e

        choice = data["choices"][0]
        return {
            "content": choice["message"].get("content", ""),
            "model": data.get("model", model),
            "usage": {
                "input_tokens":  data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "total_tokens":  data.get("usage", {}).get("total_tokens", 0),
            },
        }

    def _call_google(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = [{"text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"]
            contents.append({"role": role, "parts": parts})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]

        req = urllib.request.Request(
            f"{url}/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"Google {e.code}: {msg}") from e

        candidates = data.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", [{"text": ""}])
        text = "".join(p.get("text", "") for p in parts)
        meta = data.get("usageMetadata", {})

        return {
            "content": text,
            "model": model,
            "usage": {
                "input_tokens":  meta.get("promptTokenCount", 0),
                "output_tokens": meta.get("candidatesTokenCount", 0),
                "total_tokens":  meta.get("promptTokenCount", 0) + meta.get("candidatesTokenCount", 0),
            },
        }

    def _direct_call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider_name: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            if provider_name == "anthropic":
                key = os.environ.get("ANTHROPIC_API_KEY", "")
                base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
                hdrs = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                return self._call_anthropic(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "openai":
                key  = os.environ.get("OPENAI_API_KEY", "")
                base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name in ("google", "google-ai-studio"):
                base = os.environ.get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com")
                hdrs = {"Content-Type": "application/json"}
                return self._call_google(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "deepseek":
                key  = os.environ.get("DEEPSEEK_API_KEY", "")
                base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "mimo":
                key  = os.environ.get("MIMO_API_KEY", "")
                base = os.environ.get("MIMO_BASE_URL_OPENAI", "https://token-plan-sgp.xiaomimimo.com")
                if base.endswith("/v1"):
                    base = base[:-3]
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "mimo-anthropic":
                key  = os.environ.get("MIMO_API_KEY", "")
                base = os.environ.get("MIMO_BASE_URL_ANTHROPIC", "https://token-plan-sgp.xiaomimimo.com/anthropic")
                hdrs = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
                return self._call_anthropic(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "opencode":
                key  = os.environ.get("OPENCODE_API_KEY", "")
                base = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/zen/go")
                if base.endswith("/v1"):
                    base = base[:-3]
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "codeops/0.1.0"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            elif provider_name == "opencode-zen":
                key  = os.environ.get("OPENCODE_API_KEY", "")
                base = os.environ.get("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen")
                if base.endswith("/v1"):
                    base = base[:-3]
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "codeops/0.1.0"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            return {"error": f"Unsupported provider: {provider_name}", "content": ""}

        except Exception as e:
            self.metrics.record_error()
            return {"error": str(e), "content": ""}

    def _cache_key(self, messages: list, model: str, provider: str, system: str, extra: str) -> str:
        raw = json.dumps(
            {"messages": messages, "model": model, "provider": provider, "system": system, "extra": extra},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _estimate_cost(self, model: str, provider: str, input_chars: int) -> float:
        input_tokens = input_chars // 4
        return _telemetry_estimate_cost(model, input_tokens, 0)

    def _calculate_cost(self, model: str, provider: str, usage: dict[str, int]) -> float:
        return _telemetry_estimate_cost(
            model,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

    def fetch_cf_logs(
        self,
        since_hours: int = 24,
        limit: int = 100,
        provider: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch logs from Cloudflare AI Gateway REST API."""
        if not self.cloudflare_enabled or not self.api_token:
            return []

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)
        params: dict[str, str] = {
            "per_page": str(min(limit, 100)),
            "page": "1",
            "order_by": "created_at",
            "direction": "desc",
            "filter[start_date]": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if provider:
            params["filter[provider]"] = provider

        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/ai-gateway/gateways/{self.gateway_id}/logs"
        )
        qs = "&".join(f"{k}={v}" for k, v in params.items())
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
        """Aggregate CF AI Gateway logs into a metrics summary."""
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
            if not data:
                return 0
            return data[max(0, int(len(data) * p / 100) - 1)]

        by_provider: dict[str, int] = {}
        by_model: dict[str, int] = {}
        by_provider_tokens: dict[str, dict[str, Any]] = {}
        for e in logs:
            prov = e.get("provider", "unknown")
            mdl  = e.get("model", "unknown")
            by_provider[prov] = by_provider.get(prov, 0) + 1
            by_model[mdl]     = by_model.get(mdl, 0) + 1
            pt = by_provider_tokens.setdefault(prov, {"in": 0, "out": 0, "cost": 0.0})
            pt["in"]   += e.get("prompt_tokens") or 0
            pt["out"]  += e.get("response_tokens") or 0
            pt["cost"] += float(e.get("cost") or 0)

        return {
            "available": True,
            "since_hours": since_hours,
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
                "p50": _pct(durations, 50), "p95": _pct(durations, 95),
                "p99": _pct(durations, 99),
                "min": durations[0] if durations else 0,
                "max": durations[-1] if durations else 0,
            },
            "by_provider": by_provider,
            "by_provider_tokens": {
                p: {"in": v["in"], "out": v["out"], "cost_usd": round(v["cost"], 6)}
                for p, v in by_provider_tokens.items()
            },
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])[:10]),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider":   self.provider.value,
            "account_id": self.account_id[:8] + "..." if self.account_id else "",
            "gateway_id": self.gateway_id,
            "enabled":    self.enabled,
            "cache":       self.cache.to_dict(),
            "rate_limit":  self.rate_limit.to_dict(),
            "spend_limit": self.spend_limit.to_dict(),
            "fallback":    self.fallback.to_dict(),
            "dlp":         self.dlp.to_dict(),
            "metrics":     self.metrics.to_dict(),
        }

    def from_config(self, config: dict[str, Any]) -> None:
        self._enabled    = config.get("enabled", True)
        self.account_id  = config.get("account_id", self.account_id)
        self.gateway_id  = config.get("gateway_id", self.gateway_id)
        self.api_token   = config.get("api_token", self.api_token)

        if c := config.get("caching"):
            self.cache.enabled     = c.get("enabled", True)
            self.cache.ttl_seconds = c.get("ttl_seconds", 3600)
            self.cache.max_entries = c.get("max_entries", 1000)

        if r := config.get("rate_limits"):
            self.rate_limit.enabled              = r.get("enabled", True)
            self.rate_limit.requests_per_minute  = r.get("requests_per_minute", 60)

        if s := config.get("spend_limits"):
            self.spend_limit.enabled           = s.get("enabled", True)
            self.spend_limit.daily_budget_usd  = s.get("daily_budget_usd", 20.0)
            self.spend_limit.per_agent_budget  = s.get("per_agent_budget", {})

        if f := config.get("fallback"):
            self.fallback.enabled  = f.get("enabled", True)
            self.fallback.chain    = f.get("chain", [])
            self.fallback.retries  = f.get("retries", 3)

        if d := config.get("dlp"):
            self.dlp.enabled        = d.get("enabled", False)
            self.dlp.block_secrets  = d.get("block_secrets", True)
            self.dlp.block_pii      = d.get("block_pii", True)
            self.dlp.block_patterns = d.get("block_patterns", [])
