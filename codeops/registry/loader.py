"""
Skill loaders — YAML files and marketplace payloads → Skill objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from voly.registry.skills import Skill, SkillSource, SkillStatus


def skill_from_dict(data: dict[str, Any]) -> Skill:
    source_raw = data.get("source", "project")
    try:
        source = SkillSource(source_raw)
    except ValueError:
        source = SkillSource.PROJECT

    status_raw = data.get("status", "active")
    try:
        status = SkillStatus(status_raw)
    except ValueError:
        status = SkillStatus.ACTIVE

    skill_id = data.get("id") or data.get("name", "").lower().replace(" ", "-")
    if not skill_id:
        raise ValueError("Skill must have id or name")

    return Skill(
        id=skill_id,
        name=data.get("name", skill_id),
        description=data.get("description", ""),
        source=source,
        status=status,
        version=data.get("version", "1.0.0"),
        content=data.get("content", ""),
        tags=list(data.get("tags") or []),
        capabilities=list(data.get("capabilities") or []),
        required_tools=list(data.get("required_tools") or []),
        compatible_agents=list(data.get("compatible_agents") or []),
        compatible_languages=list(data.get("compatible_languages") or []),
        compatible_frameworks=list(data.get("compatible_frameworks") or []),
        examples=list(data.get("examples") or []),
        author=data.get("author", ""),
        usage_count=int(data.get("usage_count") or 0),
        success_rate=float(data.get("success_rate") if data.get("success_rate") is not None else 1.0),
        metadata=dict(data.get("metadata") or {}),
    )


def skill_to_yaml_dict(skill: Skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "source": skill.source.value,
        "status": skill.status.value,
        "version": skill.version,
        "content": skill.content,
        "tags": skill.tags,
        "capabilities": skill.capabilities,
        "required_tools": skill.required_tools,
        "compatible_agents": skill.compatible_agents,
        "compatible_languages": skill.compatible_languages,
        "compatible_frameworks": skill.compatible_frameworks,
        "examples": skill.examples,
        "author": skill.author,
        "usage_count": skill.usage_count,
        "success_rate": skill.success_rate,
        "metadata": skill.metadata,
    }


def load_skills_from_directory(path: Path) -> list[Skill]:
    if not path.is_dir():
        return []

    skills: list[Skill] = []
    for file_path in sorted(path.glob("*.yml")) + sorted(path.glob("*.yaml")):
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            continue
        if "id" not in data:
            data["id"] = file_path.stem
        skills.append(skill_from_dict(data))
    return skills


def save_skill_yaml(skill: Skill, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(skill_to_yaml_dict(skill), f, allow_unicode=True, sort_keys=False)
    return path
