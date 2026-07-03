"""
Registry package — Agent Registry + Skill Registry.
"""

from voly.registry.agents import AgentRegistry, AgentDefinition, BUILTIN_AGENTS
from voly.registry.loader import (
    load_skills_from_directory,
    save_skill_yaml,
    skill_from_dict,
    skill_to_yaml_dict,
)
from voly.registry.marketplace import MarketplaceClient, MarketplaceError
from voly.registry.skills import (
    SkillRegistry,
    SkillIndex,
    Skill,
    SkillSource,
    SkillStatus,
    create_skill_registry,
    resolve_marketplace_url,
    resolve_skills_path,
)
from voly.registry.builtin_data import BUILTIN_SKILLS

__all__ = [
    "AgentRegistry",
    "AgentDefinition",
    "BUILTIN_AGENTS",
    "SkillRegistry",
    "SkillIndex",
    "Skill",
    "SkillSource",
    "SkillStatus",
    "BUILTIN_SKILLS",
    "create_skill_registry",
    "resolve_marketplace_url",
    "resolve_skills_path",
    "MarketplaceClient",
    "MarketplaceError",
    "load_skills_from_directory",
    "save_skill_yaml",
    "skill_from_dict",
    "skill_to_yaml_dict",
]
