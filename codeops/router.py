"""
Agent Router — определяет какого агента, модель и инструменты использовать.

Анализирует задачу и выбирает:
    - Тип агента (разработка / ревью / архитектура / багфикс)
    - Модель (Claude / GPT / Gemini)
    - Инструменты (GitHub, GitLab, Docker, K8s, ...)
    - Ограничения (sandbox, max_turns)

Стратегия маршрутизации:
    1. Точное совпадение keywords в тексте задачи
    2. Wildcard-паттерны (например, "fix * bug")
    3. Default fallback на базового агента
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from codeops.config import CodeOpsConfig


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


class AgentRouter:
    _routing_rules: dict[str, RouteDecision] = {
        "архитектур*|architecture|design.*system|проект*": RouteDecision(
            agent="architect",
            model="claude-opus",
            provider="anthropic",
            tools=["github", "wiki"],
        ),
        "ревью|review|code.*review|провер*": RouteDecision(
            agent="reviewer",
            model="gpt-4o",
            provider="openai",
            tools=["github", "gitlab"],
        ),
        "баг|bug|fix|исправ*|ошибк*|error|дебаг|debug": RouteDecision(
            agent="bugfixer",
            model="claude-sonnet",
            provider="anthropic",
            tools=["github", "temporal"],
        ),
        "тест*|test|unittest|pytest|spec": RouteDecision(
            agent="tester",
            model="gpt-4o-mini",
            provider="openai",
            tools=["github"],
        ),
        "деплой|deploy|релиз|release|publish": RouteDecision(
            agent="deployer",
            model="claude-sonnet",
            provider="anthropic",
            tools=["github", "docker", "kubernetes"],
        ),
        "документ*|document*|wiki|readme": RouteDecision(
            agent="documenter",
            model="gpt-4o-mini",
            provider="openai",
            tools=["wiki", "confluence"],
        ),
        "база.*данных|database|sql|postgres|migration": RouteDecision(
            agent="data-engineer",
            model="claude-sonnet",
            provider="anthropic",
            tools=["postgresql"],
        ),
    }

    def __init__(self, config: CodeOpsConfig | None = None):
        self.config = config or CodeOpsConfig()

    def route(self, task: str, context: dict[str, Any] | None = None) -> RouteDecision:
        context = context or {}
        analysis = self.analyze_task(task)

        for pattern, decision in self._routing_rules.items():
            for sub_pattern in pattern.split("|"):
                if re.search(sub_pattern.lower(), task.lower()):
                    result = self._merge_with_config(decision)
                    result.routing_score = max(analysis.confidence, 0.7)
                    return result

        agent_cfg = self.config.get_agent_config()
        model_cfg = self.config.get_model_config()
        return RouteDecision(
            agent=agent_cfg.name,
            model=model_cfg.model,
            provider=model_cfg.provider,
            tools=agent_cfg.tools,
            routing_score=analysis.confidence,
        )

    def analyze_task(self, task: str) -> TaskAnalysis:
        analysis = TaskAnalysis(intent="general", confidence=0.3)
        t = task.lower()

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
            w in t for w in ["напиши", "создай", "добавь", "реализуй", "implement", "create", "build", "add"]
        )
        analysis.requires_review = any(
            w in t for w in ["review", "провер", "check", "audit"]
        )
        analysis.requires_deployment = any(
            w in t for w in ["deploy", "release", "деплой", "релиз"]
        )
        analysis.requires_testing = any(
            w in t for w in ["test", "тест", "pytest", "unittest"]
        )

        domain_map = {
            "database": ["sql", "postgres", "база", "migration"],
            "frontend": ["react", "vue", "angular", "ui", "css", "html"],
            "backend": ["api", "server", "endpoint", "graphql", "rest"],
            "infra": ["docker", "k8s", "kubernetes", "deploy", "terraform"],
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
        model_cfg = self.config.get_model_config(agent_cfg.model or decision.model)

        tools = decision.tools if decision.tools else agent_cfg.tools

        return RouteDecision(
            agent=agent_cfg.name,
            model=model_cfg.model,
            provider=model_cfg.provider,
            tools=tools,
            config={
                "max_turns": agent_cfg.max_turns,
                "sandbox": agent_cfg.sandbox,
                "system_prompt": agent_cfg.system_prompt,
            },
        )
