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
        is_index=bool(data.get("is_index", False)),
    )


def skill_to_yaml_dict(skill: Skill) -> dict[str, Any]:
    out: dict[str, Any] = {
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
    if skill.is_index:
        out["is_index"] = True
    # Promote package install fields from metadata so the CF marketplace
    # worker persists them in the repository/install_kind columns.
    if skill.metadata.get("repository"):
        out["repository"] = skill.metadata["repository"]
    if skill.metadata.get("install_kind"):
        out["install_kind"] = skill.metadata["install_kind"]
    return out


def load_skills_from_directory(path: Path) -> list[Skill]:
    """Load skills from a directory.

    Handles two layouts:
    - Flat YAML files (*.yml / *.yaml) — written by install_from_marketplace single-file.
    - Subdirectory packages with SKILL.md — written by install_from_marketplace git clone
      (e.g. .voly/skills/pmbok6/SKILL.md). Frontmatter is parsed via _skill_from_skill_md.
    """
    if not path.is_dir():
        return []

    skills: list[Skill] = []

    # Flat YAML skills
    for file_path in sorted(path.glob("*.yml")) + sorted(path.glob("*.yaml")):
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                continue
            if "id" not in data:
                data["id"] = file_path.stem
            skills.append(skill_from_dict(data))
        except Exception:
            continue

    # Package-based skills: subdirectories with a SKILL.md
    for skill_md in sorted(path.glob("*/SKILL.md")):
        try:
            skill = _skill_from_skill_md(skill_md)
            if skill:
                skills.append(skill)
        except Exception:
            continue

    return skills


def _skill_from_skill_md(skill_md: Path) -> "Skill | None":
    """Parse a SKILL.md file (frontmatter + body) into a Skill object."""
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None

    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    try:
        fm = yaml.safe_load("\n".join(lines[1:end])) or {}
    except Exception:
        return None
    if not isinstance(fm, dict):
        return None

    body = "\n".join(lines[end + 1:]).strip()
    skill_id = str(fm.get("name") or skill_md.parent.name).lower().replace(" ", "-")
    data = {
        "id": skill_id,
        "name": str(fm.get("name") or skill_md.parent.name),
        "description": str(fm.get("description") or ""),
        "source": "marketplace",
        "status": "active",
        "version": str(fm.get("version") or "1.0.0"),
        "content": body,
        "tags": list(fm.get("triggers") or fm.get("tags") or []),
        "capabilities": list(fm.get("triggers") or fm.get("tags") or []),
        "compatible_agents": list(fm.get("compatible_tools") or []),
        "author": str(fm.get("author") or skill_md.parent.name),
        "metadata": {
            "installed_path": str(skill_md.parent),
            "install_kind": "git",
            "skill_md": str(skill_md),
        },
    }
    return skill_from_dict(data)


def save_skill_yaml(skill: Skill, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(skill_to_yaml_dict(skill), f, allow_unicode=True, sort_keys=False)
    return path
