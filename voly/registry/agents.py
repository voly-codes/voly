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
        description="Cursor Agent — code implementation, large tasks, multi-file",
        capabilities=["coding", "implementation", "refactoring", "debugging", "large-output"],
        required_skills=["coding", "testing"],
        supported_tools=["github", "gitlab", "docker"],
        supported_models=["composer-2.5-fast", "gpt-5.3-codex"],
        preferred_model="composer-2.5-fast",
        system_prompt="You are Cursor Agent. Implement code in the project, follow the repository conventions.",
        tags=["coding", "implementation", "cursor", "default"],
        metadata={"executor": "cursor", "api_key_env": "CURSOR_API_KEY"},
    ),
    AgentDefinition(
        name="architect",
        description="Architect — designs technical solutions",
        capabilities=["architecture", "system-design", "tech-specs", "diagrams"],
        required_skills=["architecture", "system-design"],
        supported_tools=["github", "wiki", "confluence"],
        supported_models=["claude-opus", "claude-sonnet"],
        preferred_model="claude-opus",
        system_prompt="You are a software architect. Design reliable, scalable solutions.",
        tags=["planning", "design", "architecture"],
    ),
    AgentDefinition(
        name="developer",
        description="Developer — writes and modifies code",
        capabilities=["coding", "implementation", "refactoring", "debugging"],
        required_skills=["coding", "testing"],
        supported_tools=["github", "gitlab", "docker"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="You are an experienced developer. Write clean, efficient code.",
        tags=["coding", "implementation"],
    ),
    AgentDefinition(
        name="reviewer",
        description="Reviewer — checks code quality",
        capabilities=["code-review", "static-analysis", "quality"],
        required_skills=["code-review", "coding-standards"],
        supported_tools=["github", "gitlab"],
        supported_models=["gpt-4o", "claude-sonnet"],
        preferred_model="gpt-4o",
        system_prompt="You are a code reviewer. Check quality, security, and readability.",
        tags=["review", "quality"],
    ),
    AgentDefinition(
        name="tester",
        description="Tester — writes and runs tests",
        capabilities=["testing", "unit-tests", "integration-tests", "e2e-tests"],
        required_skills=["testing", "test-automation"],
        supported_tools=["github", "gitlab"],
        supported_models=["gpt-4o-mini", "claude-sonnet"],
        preferred_model="gpt-4o-mini",
        system_prompt="You are a tester. Write comprehensive tests and check edge cases.",
        tags=["testing", "quality"],
    ),
    AgentDefinition(
        name="security",
        description="Security specialist — code audit and protection",
        capabilities=["security-audit", "vulnerability-scan", "compliance"],
        required_skills=["security", "owasp", "compliance"],
        supported_tools=["github", "gitlab"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="You are a security expert. Hunt for vulnerabilities, check OWASP Top 10.",
        tags=["security", "audit"],
    ),
    AgentDefinition(
        name="devops",
        description="DevOps engineer — CI/CD, infrastructure, and deployment",
        capabilities=["deployment", "ci-cd", "infrastructure", "containers"],
        required_skills=["docker", "kubernetes", "ci-cd", "terraform"],
        supported_tools=["github", "gitlab", "docker", "kubernetes", "cloudflare"],
        supported_models=["claude-sonnet", "gpt-4o"],
        preferred_model="claude-sonnet",
        system_prompt="You are a DevOps engineer. Manage CI/CD, containers, and cloud infrastructure.",
        tags=["infrastructure", "deployment", "automation"],
    ),
    AgentDefinition(
        name="documenter",
        description="Documenter — writes and updates documentation",
        capabilities=["documentation", "api-docs", "changelog", "readme"],
        required_skills=["technical-writing", "documentation"],
        supported_tools=["wiki", "confluence"],
        supported_models=["gpt-4o-mini", "claude-sonnet"],
        preferred_model="gpt-4o-mini",
        system_prompt="You are a technical writer. Write clear and useful documentation.",
        tags=["documentation", "writing"],
    ),
    AgentDefinition(
        name="product-analyst",
        description="Product analyst — analyzes requirements and metrics",
        capabilities=["requirements-analysis", "metrics", "user-stories"],
        required_skills=["product-analysis", "requirements"],
        supported_tools=["jira", "confluence"],
        supported_models=["gpt-4o", "claude-sonnet"],
        preferred_model="gpt-4o",
        system_prompt="You are a product analyst. Analyze requirements and craft user stories.",
        tags=["analysis", "product", "planning"],
    ),
]
