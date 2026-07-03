"""Tests for Agent Registry and Skill Registry."""

from voly.registry.agents import AgentRegistry, AgentDefinition, BUILTIN_AGENTS
from voly.registry.skills import (
    SkillRegistry,
    SkillIndex,
    Skill,
    SkillSource,
    SkillStatus,
)

# Sample skills used across tests — mirrors builtin_data.BUILTIN_SKILLS structure
_SAMPLE_SKILLS = [
    Skill(
        id="skill-architecture",
        name="Software Architecture",
        description="Architecture principles",
        source=SkillSource.BUILTIN,
        tags=["architecture", "design"],
        capabilities=["architecture", "system-design"],
        compatible_agents=["architect"],
        content="SOLID, DDD, Clean Architecture...",
    ),
    Skill(
        id="skill-docker",
        name="Docker & Containers",
        description="Containerization",
        source=SkillSource.BUILTIN,
        tags=["docker", "container", "devops"],
        capabilities=["containerization"],
        compatible_agents=["devops", "developer"],
        content="Multi-stage builds, healthchecks...",
    ),
    Skill(
        id="skill-nextjs",
        name="Next.js Development",
        description="Next.js 14/15",
        source=SkillSource.BUILTIN,
        tags=["nextjs", "react", "frontend"],
        capabilities=["frontend", "ssr"],
        compatible_agents=["developer", "architect"],
        compatible_languages=["typescript", "javascript"],
        compatible_frameworks=["nextjs", "react"],
        content="App Router, Server Components...",
    ),
    Skill(
        id="skill-dotnet",
        name=".NET Development",
        description=".NET 8/9",
        source=SkillSource.BUILTIN,
        tags=["dotnet", "csharp"],
        compatible_languages=["csharp"],
        compatible_frameworks=["dotnet", "aspnet"],
        content="Minimal APIs, Native AOT...",
    ),
    Skill(
        id="skill-developer",
        name="Developer",
        description="General development",
        source=SkillSource.BUILTIN,
        tags=["developer"],
        compatible_agents=["developer"],
        content="Best practices...",
    ),
]


# ── Agent Registry ────────────────────────────────────────────────────────────

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


# ── Skill Registry ────────────────────────────────────────────────────────────

def _reg_with_builtins() -> SkillRegistry:
    """Helper: empty registry pre-populated with sample skills."""
    reg = SkillRegistry()
    for skill in _SAMPLE_SKILLS:
        reg.register(skill)
    return reg


def test_skill_registry_starts_empty() -> None:
    """Registry loads nothing by default — skills come from .voly/skills/ only."""
    reg = SkillRegistry()
    assert reg.index.count() == 0


def test_skill_registry_loads_from_directory(tmp_path) -> None:
    """Skills saved as YAML are loaded on init."""
    from voly.registry.loader import save_skill_yaml, skill_from_dict

    skill_dict = {
        "id": "test-skill",
        "name": "Test Skill",
        "description": "A test skill",
        "source": "marketplace",
        "tags": ["test"],
        "content": "Do the thing.",
    }
    save_skill_yaml(skill_from_dict(skill_dict), tmp_path / "test-skill.yaml")

    reg = SkillRegistry(skills_path=tmp_path)
    assert reg.index.count() == 1
    assert reg.get("test-skill") is not None


def test_skill_search_by_tag() -> None:
    reg = _reg_with_builtins()
    results = reg.search(tags=["docker"])
    assert len(results) >= 1
    assert any("docker" in s.tags for s in results)


def test_skill_search_by_language() -> None:
    reg = _reg_with_builtins()
    results = reg.search(language="csharp")
    assert len(results) >= 1
    assert any("csharp" in s.compatible_languages for s in results)


def test_skill_search_by_framework() -> None:
    reg = _reg_with_builtins()
    results = reg.search(framework="nextjs")
    assert len(results) >= 1
    assert any("nextjs" in s.compatible_frameworks for s in results)


def test_skill_search_by_agent() -> None:
    reg = _reg_with_builtins()
    results = reg.search(agent="developer")
    assert len(results) >= 1


def test_skill_serialization() -> None:
    skill = _SAMPLE_SKILLS[0]
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
