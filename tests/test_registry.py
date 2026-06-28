"""Tests for Agent Registry and Skill Registry."""

from codeops.registry.agents import AgentRegistry, AgentDefinition, BUILTIN_AGENTS
from codeops.registry.skills import (
    SkillRegistry,
    SkillIndex,
    Skill,
    SkillSource,
    SkillStatus,
    BUILTIN_SKILLS,
)


def test_agent_registry_loads_builtins() -> None:
    reg = AgentRegistry()
    agents = reg.list_all()
    assert len(agents) >= 7
    names = [a.name for a in agents]
    assert "architect" in names
    assert "developer" in names
    assert "reviewer" in names
    assert "tester" in names


def test_agent_registry_find_by_capability() -> None:
    reg = AgentRegistry()
    results = reg.find_by_capability("architecture")
    assert len(results) >= 1
    assert results[0].name == "architect"

    results = reg.find_by_capability("testing")
    assert len(results) >= 1


def test_agent_registry_find_by_tool() -> None:
    reg = AgentRegistry()
    results = reg.find_by_tool("github")
    assert len(results) >= 3


def test_agent_definition_serialization() -> None:
    agent = BUILTIN_AGENTS[0]
    d = agent.to_dict()
    restored = AgentDefinition.from_dict(d)
    assert restored.name == agent.name
    assert restored.description == agent.description
    assert restored.capabilities == agent.capabilities


def test_skill_registry_loads_builtins() -> None:
    reg = SkillRegistry()
    skills = reg.index.list_all()
    assert len(skills) >= 8
    ids = [s.id for s in skills]
    assert "skill-architecture" in ids
    assert "skill-nextjs" in ids
    assert "skill-dotnet" in ids


def test_skill_search_by_tag() -> None:
    reg = SkillRegistry()
    results = reg.search(tags=["docker"])
    assert len(results) >= 1
    assert any("docker" in s.tags for s in results)


def test_skill_search_by_language() -> None:
    reg = SkillRegistry()
    results = reg.search(language="csharp")
    assert len(results) >= 1
    assert any("csharp" in s.compatible_languages for s in results)


def test_skill_search_by_framework() -> None:
    reg = SkillRegistry()
    results = reg.search(framework="nextjs")
    assert len(results) >= 1
    assert any("nextjs" in s.compatible_frameworks for s in results)


def test_skill_search_by_agent() -> None:
    reg = SkillRegistry()
    results = reg.search(agent="developer")
    assert len(results) >= 1


def test_skill_serialization() -> None:
    skill = BUILTIN_SKILLS[0]
    d = skill.to_dict()
    restored = Skill.from_dict(d)
    assert restored.id == skill.id
    assert restored.name == skill.name


def test_skill_auto_generate() -> None:
    reg = SkillRegistry()
    skill = reg.auto_generate("Implement auth", "Success: added JWT middleware", "developer")
    assert skill.source == SkillSource.GENERATED
    assert skill.status == SkillStatus.CANDIDATE
    candidates = reg.list_candidates()
    assert any(c.id == skill.id for c in candidates)


def test_skill_approve_reject() -> None:
    reg = SkillRegistry()
    skill = reg.auto_generate("Task", "Result", "developer")

    assert reg.approve_candidate(skill.id) is True
    assert skill.status == SkillStatus.ACTIVE

    skill2 = reg.auto_generate("Task2", "Result2", "developer")
    assert reg.reject_candidate(skill2.id) is True
    assert reg.get(skill2.id) is None
