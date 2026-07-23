"""
Agent Router — health-aware routing to agents, models, and tools.

Routing strategy:
    1. Keyword match against task text
    2. Pick first *healthy* provider from task-type preference list
    3. Default fallback to config default agent
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from voly.config import VOLYConfig

_log = logging.getLogger("voly.router")

_LLAMA_SCOUT_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
_QWEN_CODER_MODEL = "@cf/qwen/qwen2.5-coder-32b-instruct"


@dataclass
class TaskAnalysis:
    intent: str
    complexity: str = "medium"
    requires_code_gen: bool = True
    requires_review: bool = False
    requires_deployment: bool = False
    requires_testing: bool = False
    domains: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class RouteDecision:
    agent: str
    model: str
    provider: str
    tools: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    routing_score: float = 0.0


# ── Provider → (model, provider_name) for use when the provider is chosen ──────

_PROVIDER_MODELS: dict[str, tuple[str, str]] = {
    "anthropic":           ("claude-sonnet-4-6", "anthropic"),
    "openai":              ("gpt-4o", "openai"),
    "google":              ("gemini-2.5-pro", "google"),
    "deepseek":            ("deepseek-chat", "deepseek"),
    "opencode-zen":        ("big-pickle", "opencode-zen"),   # free tier
    "mimo":                ("mimo-v2.5-free", "mimo"),
    "opencode":            ("deepseek-v4-flash", "opencode"),
    # Workers AI: default to fast Llama 4 Scout (131K ctx, tested 2026-06-30)
    "workers-ai":          (_LLAMA_SCOUT_MODEL, "workers-ai"),
    "cloudflare-dynamic":  ("dynamic/ai_route", "cloudflare-dynamic"),
    # OmniRoute: self-hosted OpenAI-compat gateway; "auto" = its auto-combo routing.
    # Opt-in only — not injected into _TASK_PROVIDERS default chains.
    "omniroute":           ("auto", "omniroute"),
}

# Workers AI models by task type (all tested working via CF API)
_WORKERS_AI_MODELS: dict[str, str] = {
    "architecture": "@cf/openai/gpt-oss-120b",              # 128K ctx, large reasoning
    "review":       _LLAMA_SCOUT_MODEL,  # 131K ctx, fast
    "bug":          _QWEN_CODER_MODEL,  # code specialist
    "test":         _QWEN_CODER_MODEL,  # code specialist
    "docs":         _LLAMA_SCOUT_MODEL,
    "database":     _QWEN_CODER_MODEL,
    "default":      "@cf/meta/llama-3.3-70b-instruct-fp8-fast",  # fastest
}

# OpenCode Go models by task type (subscription — opencode.ai/zen/go/v1).
# Overrides the provider-level default in _PROVIDER_MODELS for these task types.
# Defaults only — model ids rotate fast, so each is env-overridable (see below).
_OPENCODE_MODELS: dict[str, str] = {
    "architecture": "kimi-k3",   # main architect
}

# Env overrides for _OPENCODE_MODELS entries (task_type → env var name).
_OPENCODE_MODEL_ENVS: dict[str, str] = {
    "architecture": "VOLY_ARCHITECT_MODEL",
}


def _opencode_task_model(task_type: str) -> str:
    """OpenCode Go model for a task type; env var wins over the built-in default."""
    env_var = _OPENCODE_MODEL_ENVS.get(task_type, "")
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            return override
    return _OPENCODE_MODELS[task_type]

# ── Task-type → ordered list of preferred providers (best fit first) ────────────

_TASK_PROVIDERS: dict[str, list[str]] = {
    # cloudflare-dynamic uses the ai_route schema (anthropic primary → workers-ai fallback)
    # architecture: OpenCode Go kimi-k3 is the main architect; anthropic is fallback.
    "architecture": ["opencode", "anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek"],
    "review":       ["anthropic", "cloudflare-dynamic", "workers-ai", "deepseek", "opencode-zen", "google"],
    "bug":          ["anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek"],
    "test":         ["anthropic", "cloudflare-dynamic", "workers-ai", "deepseek", "opencode-zen"],
    "deploy":       ["anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek"],
    "docs":         ["anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek"],
    "database":     ["anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek"],
    "default":      ["anthropic", "cloudflare-dynamic", "workers-ai", "opencode-zen", "deepseek", "google", "mimo"],
}

# ── Keyword → (task_type, agent, tools) ─────────────────────────────────────────

_ROUTING_RULES: list[tuple[str, str, str, list[str]]] = [
    # pattern, task_type, agent, tools
    (r"архитектур|architecture|design.*system|проект", "architecture", "architect", ["github", "wiki"]),
    (r"ревью|review|code.*review|провер",              "review",       "reviewer",  ["github", "gitlab"]),
    (r"баг|bug|fix|исправ|ошибк|дебаг|debug",         "bug",          "bugfixer",  ["github", "temporal"]),
    (r"тест|test|unittest|pytest|spec",                "test",         "tester",    ["github"]),
    (r"деплой|deploy|релиз|release|publish",           "deploy",       "deployer",  ["github", "docker", "kubernetes"]),
    (r"документ|document|wiki|readme",                 "docs",         "documenter",["wiki", "confluence"]),
    (r"база.*данных|database|sql|postgres|migration",  "database",     "data-engineer", ["postgresql"]),
]


class AgentRouter:
    def __init__(self, config: VOLYConfig | None = None):
        self.config = config or VOLYConfig()

    def route(self, task: str, context: dict[str, Any] | None = None) -> RouteDecision:
        from voly.ai_gateway.health import get_checker
        context = context or {}
        analysis = self.analyze_task(task)
        checker = get_checker()

        for pattern, task_type, agent, tools in _ROUTING_RULES:
            if re.search(pattern, task.lower()):
                provider, model = self._pick_provider(task_type, checker)
                _log.info("route match=%r task_type=%s agent=%s provider=%s model=%s",
                          pattern, task_type, agent, provider, model)
                result = self._merge_with_config(
                    RouteDecision(agent=agent, model=model, provider=provider, tools=tools)
                )
                result.routing_score = max(analysis.confidence, 0.7)
                return result

        # Default: use config default, but still health-check the provider
        agent_cfg = self.config.get_agent_config()
        model_cfg = self.config.get_model_config()
        default_provider = model_cfg.provider

        if not checker.check(default_provider).healthy:
            provider, model = self._pick_provider("default", checker)
            _log.info("default provider %s unhealthy, using %s/%s", default_provider, provider, model)
        else:
            provider, model = default_provider, model_cfg.model

        return RouteDecision(
            agent=agent_cfg.name,
            model=model,
            provider=provider,
            tools=agent_cfg.tools,
            routing_score=analysis.confidence,
        )

    def _pick_provider(
        self, task_type: str, checker: Any
    ) -> tuple[str, str]:
        """Return (provider, model) — first healthy from preference list."""
        prefs = _TASK_PROVIDERS.get(task_type, _TASK_PROVIDERS["default"])
        for prov in prefs:
            if checker.check(prov).healthy:
                if prov == "workers-ai":
                    # Use task-specific Workers AI model
                    model = _WORKERS_AI_MODELS.get(task_type, _WORKERS_AI_MODELS["default"])
                    return "workers-ai", model
                if prov == "opencode" and task_type in _OPENCODE_MODELS:
                    # Task-specific OpenCode Go model, env-overridable
                    # (e.g. VOLY_ARCHITECT_MODEL=kimi-k3 for architecture).
                    return "opencode", _opencode_task_model(task_type)
                model, actual_prov = _PROVIDER_MODELS.get(prov, (prov, prov))
                return actual_prov, model
        # All unhealthy — use first anyway and let it fail / trigger fallback chain
        fallback_prov = prefs[0]
        if fallback_prov == "workers-ai":
            model = _WORKERS_AI_MODELS.get(task_type, _WORKERS_AI_MODELS["default"])
            _log.warning("All providers unhealthy for %s, using workers-ai as last resort", task_type)
            return "workers-ai", model
        if fallback_prov == "opencode" and task_type in _OPENCODE_MODELS:
            model = _opencode_task_model(task_type)
            _log.warning("All providers unhealthy for %s, using opencode/%s as last resort", task_type, model)
            return "opencode", model
        model, actual_prov = _PROVIDER_MODELS.get(fallback_prov, (fallback_prov, fallback_prov))
        _log.warning("All providers unhealthy for %s, using %s as last resort", task_type, actual_prov)
        return actual_prov, model

    def analyze_task(self, task: str) -> TaskAnalysis:
        analysis = TaskAnalysis(intent="general", confidence=0.3)
        t = task.lower()
        # Strip filename-like tokens ("test.md", "config.yaml") before keyword
        # matching: a capability keyword must describe the task, not just
        # happen to be part of a file name the task mentions — otherwise
        # "create test.md and write hello in it" flips requires_testing to
        # True purely because "test" is a substring of the filename, which
        # pushes a one-file task into the full multi-agent dispatch path.
        t = re.sub(r"\b[\w\-]+\.[a-z0-9]{1,5}\b", " ", t)

        complexity_signals = [
            (["архитектур", "architecture", "перепроектиров", "refactor.*architect"], "high"),
            (["рефактор", "refactor", "migrat", "оптимиз"], "medium"),
            (["исправ", "fix", "bug", "typo", "поправ"], "low"),
        ]
        for keywords, level in complexity_signals:
            if any(re.search(kw, t) for kw in keywords):
                analysis.complexity = level
                analysis.confidence = max(analysis.confidence, 0.6)
                break

        analysis.requires_code_gen = any(
            w in t for w in [
                # Russian imperatives and infinitives
                "напиши", "написать", "создай", "создать", "добавь", "добавить",
                "реализуй", "реализовать", "сделай", "сделать", "измени", "изменить",
                "исправь", "исправить", "мигрируй", "мигрировать", "рефактор",
                # English
                "implement", "create", "build", "add", "write", "generate", "fix", "refactor",
                "migrate", "update", "modify", "edit",
            ]
        )
        analysis.requires_review    = any(w in t for w in ["review", "провер", "check", "audit"])
        analysis.requires_deployment = any(w in t for w in ["deploy", "release", "деплой", "релиз"])
        analysis.requires_testing   = any(w in t for w in ["test", "тест", "pytest", "unittest"])

        # Multi-capability tasks always get a reviewer (developer+tester → 3 roles).
        flag_count = sum([
            analysis.requires_code_gen,
            analysis.requires_review,
            analysis.requires_testing,
            analysis.requires_deployment,
        ])
        if flag_count >= 2:
            analysis.requires_review = True

        domain_map = {
            "database": ["sql", "postgres", "база", "migration"],
            "frontend": ["react", "vue", "angular", "ui", "css", "html"],
            "backend":  ["api", "server", "endpoint", "graphql", "rest"],
            "infra":    ["docker", "k8s", "kubernetes", "deploy", "terraform"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in t for kw in keywords):
                analysis.domains.append(domain)
                analysis.confidence = max(analysis.confidence, 0.7)

        if analysis.confidence < 0.5:
            analysis.confidence = 0.5
            analysis.intent = "code_generation" if analysis.requires_code_gen else "general"

        return analysis

    def _merge_with_config(self, decision: RouteDecision) -> RouteDecision:
        agent_cfg = self.config.get_agent_config(decision.agent)
        # Don't override the health-chosen model/provider via config model lookup —
        # config model lookup is for named models in voly.yaml only
        tools = decision.tools if decision.tools else agent_cfg.tools
        return RouteDecision(
            agent=agent_cfg.name,
            model=decision.model,
            provider=decision.provider,
            tools=tools,
            config={
                "max_turns": agent_cfg.max_turns,
                "sandbox": agent_cfg.sandbox,
                "system_prompt": agent_cfg.system_prompt,
            },
            routing_score=decision.routing_score,
        )
