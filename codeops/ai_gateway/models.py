"""AI Gateway data models: enums, rate limits, cache, DLP, metrics."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GatewayProvider(Enum):
    CLOUDFLARE = "cloudflare"
    CUSTOM = "custom"


class FallbackStrategy(Enum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    COST_AWARE = "cost_aware"


@dataclass
class RateLimit:
    requests_per_minute: int = 60
    tokens_per_minute: int = 200_000
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "tokens_per_minute": self.tokens_per_minute,
            "enabled": self.enabled,
        }


@dataclass
class SpendLimit:
    daily_budget_usd: float = 20.0
    per_agent_budget: dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    spent_today: float = 0.0
    spent_per_agent: dict[str, float] = field(default_factory=dict)
    reset_at: float = 0.0

    def check(self, estimated_cost: float, agent: str | None = None) -> bool:
        if not self.enabled:
            return True

        if time.time() - self.reset_at > 86400:
            self.spent_today = 0.0
            self.spent_per_agent.clear()
            self.reset_at = time.time()

        if self.spent_today + estimated_cost > self.daily_budget_usd:
            return False

        if agent and agent in self.per_agent_budget:
            per_agent = self.per_agent_budget[agent]
            current = self.spent_per_agent.get(agent, 0.0)
            if current + estimated_cost > per_agent:
                return False

        return True

    def record(self, cost: float, agent: str | None = None) -> None:
        self.spent_today += cost
        if agent:
            self.spent_per_agent[agent] = self.spent_per_agent.get(agent, 0.0) + cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_budget_usd": self.daily_budget_usd,
            "per_agent_budget": self.per_agent_budget,
            "enabled": self.enabled,
            "spent_today": round(self.spent_today, 4),
        }


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    # When set, cache entries are also written to this directory as
    # <key>.json so they survive across gateway instances and process
    # restarts (the web path builds a fresh Pipeline/gateway per request,
    # so an in-memory-only cache never hits on a repeat task).
    persist_dir: str = ""
    _store: dict[str, tuple[float, str]] = field(default_factory=dict, repr=False)

    def _path(self, key: str):
        import pathlib
        return pathlib.Path(self.persist_dir) / f"{key}.json"

    def get(self, key: str) -> str | None:
        if key in self._store:
            expires_at, value = self._store[key]
            if time.time() < expires_at:
                return value
            del self._store[key]
        if self.persist_dir:
            p = self._path(key)
            try:
                if p.exists():
                    import json
                    expires_at, value = json.loads(p.read_text())
                    if time.time() < expires_at:
                        self._store[key] = (expires_at, value)  # warm in-memory
                        return value
                    p.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        return None

    def set(self, key: str, value: str) -> None:
        if len(self._store) >= self.max_entries:
            oldest = min(self._store.keys(), key=lambda k: self._store[k][0])
            del self._store[oldest]
        expires_at = time.time() + self.ttl_seconds
        self._store[key] = (expires_at, value)
        if self.persist_dir:
            try:
                import json
                import pathlib
                pathlib.Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
                self._path(key).write_text(json.dumps([expires_at, value]))
            except OSError:
                pass

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)
        if self.persist_dir:
            try:
                self._path(key).unlink(missing_ok=True)
            except OSError:
                pass

    def flush(self) -> None:
        self._store.clear()

    def stats(self) -> dict[str, Any]:
        active = sum(1 for _, (exp, _) in self._store.items() if time.time() < exp)
        return {"entries": len(self._store), "active": active, "max": self.max_entries}

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
        }


@dataclass
class FallbackChain:
    strategy: FallbackStrategy = FallbackStrategy.SEQUENTIAL
    chain: list[dict[str, str]] = field(default_factory=list)
    enabled: bool = True
    retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "chain": self.chain,
            "enabled": self.enabled,
            "retries": self.retries,
        }


@dataclass
class DLPConfig:
    enabled: bool = False
    block_secrets: bool = True
    block_pii: bool = True
    block_patterns: list[str] = field(default_factory=list)
    _secret_patterns: list[str] = field(default_factory=lambda: [
        r"(?i)(api[_-]?key|secret[_-]?key|token|password|auth[_-]?token)\s*[:=]\s*[\"'`]?\S+[\"'`]?",
        r"(?i)(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*)",
        r"(?i)(sk-[A-Za-z0-9]{12,})",
        r"(?i)(ghp_[A-Za-z0-9]{12,})",
        r"(?i)(xox[baprs]-[A-Za-z0-9-]{10,})",
        r"(?i)(-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE KEY-----)",
    ])
    _pii_patterns: list[str] = field(default_factory=lambda: [
        r"\b\d{3}-\d{2}-\d{4}\b",
        r"\b\d{16}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ])

    def scan(self, content: str) -> list[str]:
        if not self.enabled:
            return []
        import re
        violations: list[str] = []
        if self.block_secrets:
            for pat in self._secret_patterns:
                if re.search(pat, content):
                    violations.append(f"Secret pattern matched: {pat[:60]}...")
        if self.block_pii:
            for pat in self._pii_patterns:
                if re.search(pat, content):
                    violations.append(f"PII pattern matched: {pat[:60]}...")
        for pat in self.block_patterns:
            if re.search(pat, content):
                violations.append(f"Custom pattern matched: {pat}")
        return violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "block_secrets": self.block_secrets,
            "block_pii": self.block_pii,
            "block_patterns": self.block_patterns,
        }


@dataclass
class GatewayMetrics:
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    rate_limited: int = 0
    fallbacks_used: int = 0
    dlp_blocks: int = 0
    errors: int = 0
    by_provider: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_model: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    requests_last_minute: list[float] = field(default_factory=list)

    def record_request(self, provider: str, model: str, tokens: int, cost: float) -> None:
        self.total_requests += 1
        self.total_tokens += tokens
        self.total_cost_usd += cost
        self.by_provider[provider] += 1
        self.by_model[model] += 1
        now = time.time()
        self.requests_last_minute.append(now)
        self.requests_last_minute = [t for t in self.requests_last_minute if now - t < 60]

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        self.cache_misses += 1

    def record_rate_limited(self) -> None:
        self.rate_limited += 1

    def record_fallback(self) -> None:
        self.fallbacks_used += 1

    def record_dlp_block(self) -> None:
        self.dlp_blocks += 1

    def record_error(self) -> None:
        self.errors += 1

    def requests_in_last_minute(self) -> int:
        now = time.time()
        return sum(1 for t in self.requests_last_minute if now - t < 60)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "rate_limited": self.rate_limited,
            "fallbacks_used": self.fallbacks_used,
            "dlp_blocks": self.dlp_blocks,
            "errors": self.errors,
            "by_provider": dict(self.by_provider),
            "by_model": dict(self.by_model),
            "rpm": self.requests_in_last_minute(),
        }
