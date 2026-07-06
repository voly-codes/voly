"""
Agent Registry — реестр специализированных AI-агентов.

Каждый агент содержит:
    - metadata (имя, версия, описание)
    - capabilities (что умеет)
    - supported_tools (MCP инструменты)
    - required_skills (необходимые навыки)
    - supported_models (предпочитаемые модели)
    - system_prompt (базовый промпт)

Структура реестра:
    agents/
      architect/
      developer/
      reviewer/
      tester/
      security/
      devops/
      documenter/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentDefinition:
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    supported_tools: list[str] = field(default_factory=list)
    supported_models: list[str] = field(default_factory=list)
    system_prompt: str = ""
    preferred_model: str = "claude-sonnet"
    max_turns: int = 100
    requires_approval: bool = False
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "required_skills": self.required_skills,
            "supported_tools": self.supported_tools,
            "supported_models": self.supported_models,
            "preferred_model": self.preferred_model,
            "requires_approval": self.requires_approval,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentDefinition:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            capabilities=data.get("capabilities", []),
            required_skills=data.get("required_skills", []),
            supported_tools=data.get("supported_tools", []),
            supported_models=data.get("supported_models", []),
            system_prompt=data.get("system_prompt", ""),
            preferred_model=data.get("preferred_model", "claude-sonnet"),
            max_turns=data.get("max_turns", 100),
            requires_approval=data.get("requires_approval", False),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}
        self._load_builtins()
        from pathlib import Path

        from voly.registry.external_catalog import catalog_path_for, load_external_catalog, register_catalog_agents

        catalog = load_external_catalog(catalog_path_for(Path.cwd()))
        if catalog:
            register_catalog_agents(self, catalog)

    def register(self, agent: AgentDefinition) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentDefinition | None:
        return self._agents.get(name)

    def list_all(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def list_names(self) -> list[str]:
        return list(self._agents.keys())

    def find_by_capability(self, capability: str) -> list[AgentDefinition]:
        results: list[AgentDefinition] = []
        for agent in self._agents.values():
            if capability in agent.capabilities or capability in agent.tags:
                results.append(agent)
        return results

    def find_by_tool(self, tool: str) -> list[AgentDefinition]:
        return [
            agent
            for agent in self._agents.values()
            if tool in agent.supported_tools
        ]

    def find_by_skill(self, skill: str) -> list[AgentDefinition]:
        return [
            agent
            for agent in self._agents.values()
            if skill in agent.required_skills
        ]

    def to_dict(self) -> dict[str, Any]:
        return {name: agent.to_dict() for name, agent in self._agents.items()}

    def load_from_dicts(self, agent_dicts: list[dict[str, Any]]) -> None:
        for data in agent_dicts:
            try:
                self.register(AgentDefinition.from_dict(data))
            except Exception:
                pass

    def _load_builtins(self) -> None:
        for agent in BUILTIN_AGENTS:
            self.register(agent)


BUILTIN_AGENTS: list[AgentDefinition] = [
    AgentDefinition(
        name="cursor",
        description="Cursor Agent — реализация кода, большие задачи, multi-file",
        capabilities=["coding", "implementation", "refactoring", "debugging", "large-output"],
        required_skills=["coding", "testing"],
        supported_tools=["github", "gitlab", "docker"],
        supported_models=["composer-2.5-fast", "gpt-5.3-codex"],
        preferred_model="composer-2.5-fast",
        system_prompt="Ты Cursor Agent. Реализуй код в проекте, следуй конвенциям репозитория.",
        tags=["coding", "implementation", "cursor", "default"],
        metadata={"executor": "cursor", "api_key_env": "CURSOR_API_KEY"},
    ),
    AgentDefinition(
        name="architect",
        description="Архитектор — проектирует технические решения",
        capabilities=["architecture", "system-design", "tech-specs", "diagrams"],
        required_skills=["architecture", "system-design"],
        supported_tools=["github", "wiki", "confluence"],
        supported_models=["claude-opus", "claude-sonnet"],
        preferred_model="claude-opus",
        system_prompt="Ты архитектор ПО. Проектируй надёжные, масштабируемые решения.",
        tags=["planning", "design", "architecture"],
    ),
    AgentDefinition(
        name="developer",
        description="Разработчик — пишет и модифицирует код",
        capabilities=["coding", "implementation", "refactoring", "debugging"],
        required_skills=["coding", "testing"],
        supported_tools=["github", "gitlab", "docker"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="Ты опытный разработчик. Пиши чистый, эффективный код.",
        tags=["coding", "implementation"],
    ),
    AgentDefinition(
        name="reviewer",
        description="Ревьюер — проверяет качество кода",
        capabilities=["code-review", "static-analysis", "quality"],
        required_skills=["code-review", "coding-standards"],
        supported_tools=["github", "gitlab"],
        supported_models=["gpt-4o", "claude-sonnet"],
        preferred_model="gpt-4o",
        system_prompt="Ты ревьюер кода. Проверяй качество, безопасность и читаемость.",
        tags=["review", "quality"],
    ),
    AgentDefinition(
        name="tester",
        description="Тестировщик — пишет и запускает тесты",
        capabilities=["testing", "unit-tests", "integration-tests", "e2e-tests"],
        required_skills=["testing", "test-automation"],
        supported_tools=["github", "gitlab"],
        supported_models=["gpt-4o-mini", "claude-sonnet"],
        preferred_model="gpt-4o-mini",
        system_prompt="Ты тестировщик. Пиши comprehensive тесты и проверяй edge cases.",
        tags=["testing", "quality"],
    ),
    AgentDefinition(
        name="security",
        description="Специалист по безопасности — аудит и защита кода",
        capabilities=["security-audit", "vulnerability-scan", "compliance"],
        required_skills=["security", "owasp", "compliance"],
        supported_tools=["github", "gitlab"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="Ты эксперт по безопасности. Ищи уязвимости, проверяй OWASP Top 10.",
        tags=["security", "audit"],
    ),
    AgentDefinition(
        name="devops",
        description="DevOps инженер — CI/CD, инфраструктура и деплой",
        capabilities=["deployment", "ci-cd", "infrastructure", "containers"],
        required_skills=["docker", "kubernetes", "ci-cd", "terraform"],
        supported_tools=["github", "gitlab", "docker", "kubernetes", "cloudflare"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="Ты DevOps инженер. Управляй CI/CD, контейнерами и облачной инфраструктурой.",
        tags=["infrastructure", "deployment", "automation"],
    ),
    AgentDefinition(
        name="documenter",
        description="Документатор — пишет и обновляет документацию",
        capabilities=["documentation", "api-docs", "changelog", "readme"],
        required_skills=["technical-writing", "documentation"],
        supported_tools=["wiki", "confluence"],
        supported_models=["gpt-4o-mini", "claude-sonnet"],
        preferred_model="gpt-4o-mini",
        system_prompt="Ты технический писатель. Пиши чёткую и полезную документацию.",
        tags=["documentation", "writing"],
    ),
    AgentDefinition(
        name="product-analyst",
        description="Продуктовый аналитик — анализирует требования и метрики",
        capabilities=["requirements-analysis", "metrics", "user-stories"],
        required_skills=["product-analysis", "requirements"],
        supported_tools=["jira", "confluence"],
        supported_models=["gpt-4o", "claude-sonnet"],
        preferred_model="gpt-4o",
        system_prompt="Ты продуктовый аналитик. Анализируй требования и формируй user stories.",
        tags=["analysis", "product", "planning"],
    ),
]
