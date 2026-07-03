"""
Skill Registry — переиспользуемые операционные знания для агентов.

Skills — это first-class citizens. Агенты не хранят доменные знания.
Агенты потребляют skills.

Источники скиллов:
    1. Built-in — встроенные в VOLY
    2. Project — сгенерированные из анализа проекта (voly scan)
    3. Organization — предоставленные компанией
    4. Marketplace — скачанные из community registry
    5. Generated — созданные автоматически из успешных выполнений

Жизненный цикл скилла:
    Task → Success → Retrospective → Skill Candidate → Human Approval → New Skill
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SkillSource(Enum):
    BUILTIN = "builtin"
    PROJECT = "project"
    ORGANIZATION = "organization"
    MARKETPLACE = "marketplace"
    GENERATED = "generated"


class SkillStatus(Enum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    source: SkillSource = SkillSource.BUILTIN
    status: SkillStatus = SkillStatus.ACTIVE
    version: str = "1.0.0"
    content: str = ""
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    compatible_agents: list[str] = field(default_factory=list)
    compatible_languages: list[str] = field(default_factory=list)
    compatible_frameworks: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    author: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    usage_count: int = 0
    success_rate: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source.value,
            "status": self.status.value,
            "version": self.version,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "required_tools": self.required_tools,
            "compatible_agents": self.compatible_agents,
            "compatible_languages": self.compatible_languages,
            "compatible_frameworks": self.compatible_frameworks,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            source=SkillSource(data.get("source", "builtin")),
            status=SkillStatus(data.get("status", "active")),
            version=data.get("version", "1.0.0"),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            capabilities=data.get("capabilities", []),
            required_tools=data.get("required_tools", []),
            compatible_agents=data.get("compatible_agents", []),
            compatible_languages=data.get("compatible_languages", []),
            compatible_frameworks=data.get("compatible_frameworks", []),
            examples=data.get("examples", []),
            author=data.get("author", ""),
            usage_count=data.get("usage_count", 0),
            success_rate=data.get("success_rate", 1.0),
            metadata=data.get("metadata", {}),
        )


class SkillIndex:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._by_tag: dict[str, set[str]] = {}
        self._by_capability: dict[str, set[str]] = {}
        self._by_language: dict[str, set[str]] = {}
        self._by_framework: dict[str, set[str]] = {}
        self._by_agent: dict[str, set[str]] = {}

    def add(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

        for tag in skill.tags:
            self._by_tag.setdefault(tag, set()).add(skill.id)
        for cap in skill.capabilities:
            self._by_capability.setdefault(cap, set()).add(skill.id)
        for lang in skill.compatible_languages:
            self._by_language.setdefault(lang, set()).add(skill.id)
        for fw in skill.compatible_frameworks:
            self._by_framework.setdefault(fw, set()).add(skill.id)
        for agent in skill.compatible_agents:
            self._by_agent.setdefault(agent, set()).add(skill.id)

    def remove(self, skill_id: str) -> None:
        skill = self._skills.pop(skill_id, None)
        if skill:
            for tag in skill.tags:
                self._by_tag.get(tag, set()).discard(skill_id)
            for cap in skill.capabilities:
                self._by_capability.get(cap, set()).discard(skill_id)
            for lang in skill.compatible_languages:
                self._by_language.get(lang, set()).discard(skill_id)
            for fw in skill.compatible_frameworks:
                self._by_framework.get(fw, set()).discard(skill_id)
            for agent in skill.compatible_agents:
                self._by_agent.get(agent, set()).discard(skill_id)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def search(
        self,
        query: str = "",
        tags: list[str] | None = None,
        capability: str | None = None,
        language: str | None = None,
        framework: str | None = None,
        agent: str | None = None,
        source: SkillSource | None = None,
    ) -> list[Skill]:
        candidates: set[str] = set(self._skills.keys())

        if query:
            q = query.lower()
            query_ids: set[str] = set()
            for sid, skill in self._skills.items():
                if (
                    q in skill.name.lower()
                    or q in skill.description.lower()
                    or any(q in tag.lower() for tag in skill.tags)
                    or any(q in cap.lower() for cap in skill.capabilities)
                ):
                    query_ids.add(sid)
            candidates &= query_ids

        if tags:
            tag_ids: set[str] = set()
            for tag in tags:
                tag_ids |= self._by_tag.get(tag, set())
            candidates &= tag_ids

        if capability:
            candidates &= self._by_capability.get(capability, set())

        if language:
            candidates &= self._by_language.get(language, set())

        if framework:
            candidates &= self._by_framework.get(framework, set())

        if agent:
            candidates &= self._by_agent.get(agent, set())

        if source:
            candidates = {sid for sid in candidates if self._skills[sid].source == source}

        return [self._skills[sid] for sid in candidates]

    def count(self) -> int:
        return len(self._skills)


class SkillRegistry:
    def __init__(
        self,
        skills_path: Path | str | None = None,
        marketplace_url: str = "",
    ):
        self.index = SkillIndex()
        self._candidates: list[Skill] = []
        self.marketplace_url = marketplace_url.rstrip("/")
        self.skills_path = Path(skills_path) if skills_path else None
        if self.skills_path:
            self._load_directory(self.skills_path)

    def register(self, skill: Skill) -> None:
        self.index.add(skill)
        if skill.status == SkillStatus.CANDIDATE:
            self._candidates.append(skill)

    def get(self, skill_id: str) -> Skill | None:
        return self.index.get(skill_id)

    def search(self, **kwargs: Any) -> list[Skill]:
        return self.index.search(**kwargs)

    def list_candidates(self) -> list[Skill]:
        return list(self._candidates)

    def approve_candidate(self, skill_id: str) -> bool:
        skill = self.index.get(skill_id)
        if skill and skill.status == SkillStatus.CANDIDATE:
            skill.status = SkillStatus.ACTIVE
            self._candidates = [c for c in self._candidates if c.id != skill_id]
            return True
        return False

    def reject_candidate(self, skill_id: str) -> bool:
        skill = self.index.get(skill_id)
        if skill and skill.status == SkillStatus.CANDIDATE:
            self.index.remove(skill_id)
            self._candidates = [c for c in self._candidates if c.id != skill_id]
            return True
        return False

    def auto_generate(self, task: str, result: str, agent_name: str) -> Skill:
        import time
        import hashlib

        skill_id = hashlib.sha256(f"{task}:{agent_name}:{time.time()}".encode()).hexdigest()[:12]
        skill = Skill(
            id=f"gen-{skill_id}",
            name=f"Generated: {task[:60]}",
            description=f"Auto-generated from successful execution by {agent_name}",
            source=SkillSource.GENERATED,
            status=SkillStatus.CANDIDATE,
            content=result[:2000],
            tags=["auto-generated", agent_name],
            compatible_agents=[agent_name],
            usage_count=1,
        )
        self.register(skill)
        return skill

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": [s.to_dict() for s in self.index.list_all()],
            "candidates": len(self._candidates),
        }

    def _register_from_dicts(self, skill_dicts: list[dict[str, Any]]) -> None:
        from voly.registry.loader import skill_from_dict
        for data in skill_dicts:
            try:
                self.register(skill_from_dict(data))
            except Exception:
                pass

    def _load_directory(self, path: Path) -> None:
        from voly.registry.loader import load_skills_from_directory

        for skill in load_skills_from_directory(path):
            if self.index.get(skill.id):
                self.index.remove(skill.id)
            self.register(skill)

    def install_from_marketplace(self, skill_id: str, *, client: Any = None) -> Skill:
        """Download skill from marketplace and save to skills_path."""
        from voly.registry.loader import save_skill_yaml, skill_from_dict
        from voly.registry.marketplace import MarketplaceClient, MarketplaceError

        if not self.marketplace_url:
            raise MarketplaceError("marketplace_url is not configured")

        mp = client or MarketplaceClient(self.marketplace_url)
        data = mp.download_skill(skill_id)
        data["source"] = "marketplace"
        skill = skill_from_dict(data)

        if self.skills_path:
            save_skill_yaml(skill, self.skills_path / f"{skill.id}.yaml")

        if self.index.get(skill.id):
            self.index.remove(skill.id)
        self.register(skill)
        return skill

    def publish_to_marketplace(self, payload: dict[str, Any], *, client: Any = None) -> dict[str, Any]:
        from voly.registry.marketplace import MarketplaceClient, MarketplaceError

        if not self.marketplace_url:
            raise MarketplaceError("marketplace_url is not configured")

        mp = client or MarketplaceClient(self.marketplace_url)
        return mp.publish_skill(payload)


def resolve_skills_path(skills_path: str, config_dir: Path | None = None) -> Path:
    path = Path(skills_path)
    if path.is_absolute():
        return path
    base = config_dir if config_dir else Path.cwd()
    return base / path


def resolve_marketplace_url(config_url: str) -> str:
    import os

    url = (config_url or "").strip()
    if url:
        return os.path.expandvars(url).rstrip("/")
    for key in ("CF_WORKER_MARKETPLACE_URL", "MARKETPLACE_URL"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def create_skill_registry(
    skills_path: str = ".voly/skills",
    marketplace_url: str = "",
    config_dir: Path | None = None,
) -> SkillRegistry:
    resolved_path = resolve_skills_path(skills_path, config_dir)
    resolved_path.mkdir(parents=True, exist_ok=True)
    return SkillRegistry(
        skills_path=resolved_path,
        marketplace_url=resolve_marketplace_url(marketplace_url),
    )
