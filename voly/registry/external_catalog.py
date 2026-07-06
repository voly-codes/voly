"""Import external skills/agents/plugins into a local VOLY catalog snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CATALOG_NAME = "external-registry.yaml"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, text

    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except Exception:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, body


def _root_label(root: Path) -> str:
    return root.name or root.resolve().name


def _unique_id(candidate: str, used: set[str], fallback: str) -> str:
    if candidate and candidate not in used:
        used.add(candidate)
        return candidate
    if fallback and fallback not in used:
        used.add(fallback)
        return fallback
    i = 2
    while True:
        alt = f"{fallback}-{i}"
        if alt not in used:
            used.add(alt)
            return alt
        i += 1


def _frontmatter_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key) or []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value]
    return []


def _build_skill_record(path: Path, root: Path, used_ids: set[str]) -> dict[str, Any] | None:
    data, body = _split_frontmatter(_read_text(path))
    if not data.get("name") and not data.get("description"):
        return None

    raw_name = str(data.get("name") or path.parent.name)
    fallback = _slugify(str(path.relative_to(root).with_suffix("")).replace("/", "-"))
    skill_id = _unique_id(_slugify(raw_name), used_ids, fallback)
    compatible_agents = _frontmatter_list(data, "compatible_tools")
    tags = _frontmatter_list(data, "tags")
    if not tags:
        tags = [p for p in path.relative_to(root).parts[:-1] if p not in {"skills", "skill", "agents", "agent"}]
    metadata = {
        "source_repo": _root_label(root),
        "source_path": str(path.relative_to(root)),
        "import_kind": "skill",
        "frontmatter_keys": sorted(data.keys()),
    }
    if compatible_agents:
        metadata["compatible_tools"] = compatible_agents
    if data.get("source"):
        metadata["upstream_source"] = data.get("source")
    return {
        "id": skill_id,
        "name": raw_name,
        "description": str(data.get("description") or ""),
        "source": "organization",
        "status": "active",
        "version": str(data.get("version") or "1.0.0"),
        "content": body.strip(),
        "tags": tags,
        "capabilities": tags,
        "required_tools": _frontmatter_list(data, "required_tools"),
        "compatible_agents": compatible_agents,
        "compatible_languages": _frontmatter_list(data, "compatible_languages"),
        "compatible_frameworks": _frontmatter_list(data, "compatible_frameworks"),
        "examples": _frontmatter_list(data, "examples"),
        "author": str(data.get("author") or _root_label(root)),
        "usage_count": int(data.get("usage_count") or 0),
        "success_rate": float(data.get("success_rate") or 1.0),
        "metadata": metadata,
    }


def _build_agent_record(path: Path, root: Path, used_ids: set[str]) -> dict[str, Any] | None:
    data, body = _split_frontmatter(_read_text(path))
    if not data.get("name") and not data.get("description"):
        return None

    name = str(data.get("name") or path.stem)
    fallback = _slugify(str(path.relative_to(root).with_suffix("")).replace("/", "-"))
    agent_id = _unique_id(_slugify(name), used_ids, fallback)
    category = path.relative_to(root).parts[0] if path.relative_to(root).parts else root.name
    tags = [category, _slugify(name)]
    description = str(data.get("description") or (body.splitlines()[0] if body else ""))
    metadata = {
        "source_repo": _root_label(root),
        "source_path": str(path.relative_to(root)),
        "import_kind": "agent",
        "frontmatter_keys": sorted(data.keys()),
    }
    if data.get("color"):
        metadata["color"] = data.get("color")
    if data.get("emoji"):
        metadata["emoji"] = data.get("emoji")
    if data.get("vibe"):
        metadata["vibe"] = data.get("vibe")
    return {
        "name": name,
        "description": description,
        "version": str(data.get("version") or "1.0.0"),
        "capabilities": tags,
        "required_skills": tags,
        "supported_tools": [],
        "supported_models": [],
        "system_prompt": body.strip(),
        "preferred_model": str(data.get("model") or "claude-sonnet"),
        "max_turns": int(data.get("max_turns") or 100),
        "requires_approval": bool(data.get("requires_approval") or False),
        "tags": tags,
        "metadata": {**metadata, "registry_id": agent_id},
    }


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(_read_text(path))
    if not isinstance(data, dict):
        return {}
    return data


def _build_plugin_record(path: Path, root: Path) -> dict[str, Any] | None:
    if path.name == "plugin.json":
        data = _load_json(path)
        if not data:
            return None
        return {
            "kind": "claude-plugin",
            "name": str(data.get("name") or path.parent.parent.name),
            "description": str(data.get("description") or ""),
            "version": str(data.get("version") or "1.0.0"),
            "author": data.get("author", {}),
            "homepage": str(data.get("homepage") or ""),
            "repository": str(data.get("repository") or ""),
            "license": str(data.get("license") or ""),
            "skills": data.get("skills", []),
            "source": data.get("source", {}),
            "attribution": data.get("attribution", {}),
            "metadata": {
                "source_repo": _root_label(root),
                "source_path": str(path.relative_to(root)),
                "install_kind": "plugin",
            },
        }
    if path.name == "tools.json":
        data = _load_json(path)
        tools = data.get("tools", {}) if isinstance(data.get("tools"), dict) else {}
        if not tools:
            return None
        out = []
        for tool_id, tool in sorted(tools.items()):
            if not isinstance(tool, dict):
                continue
            out.append(
                {
                    "kind": "agency-tool",
                    "id": str(tool.get("id") or tool_id),
                    "name": str(tool.get("label") or tool_id),
                    "description": str(tool.get("label") or tool_id),
                    "version": "1.0.0",
                    "author": "agency-agents",
                    "homepage": "",
                    "repository": "",
                    "license": "",
                    "skills": [],
                    "source": tool,
                    "metadata": {
                        "source_repo": _root_label(root),
                        "source_path": str(path.relative_to(root)),
                        "install_kind": tool.get("installKind", "per-agent"),
                    },
                }
            )
        return {"kind": "agency-tools", "items": out}
    return None


def build_external_catalog(
    claude_skills_root: Path,
    agency_agents_root: Path,
) -> dict[str, Any]:
    skill_ids: set[str] = set()
    agent_ids: set[str] = set()

    skills: list[dict[str, Any]] = []
    for path in sorted(claude_skills_root.rglob("SKILL.md")):
        if any(part in {".git", "node_modules", "eval-workspace", ".gemini"} for part in path.parts):
            continue
        record = _build_skill_record(path, claude_skills_root, skill_ids)
        if record:
            skills.append(record)

    agents: list[dict[str, Any]] = []
    for path in sorted(agency_agents_root.rglob("*.md")):
        if path.name.lower() in {"readme.md", "contributing.md", "contributing_zh-cn.md"}:
            continue
        if any(part in {".git", "node_modules", "dist"} for part in path.parts):
            continue
        record = _build_agent_record(path, agency_agents_root, agent_ids)
        if record:
            agents.append(record)

    plugins: list[dict[str, Any]] = []
    for path in sorted(claude_skills_root.rglob(".claude-plugin/plugin.json")):
        record = _build_plugin_record(path, claude_skills_root)
        if record:
            plugins.append(record)

    agency_tools = agency_agents_root / "tools.json"
    if agency_tools.exists():
        record = _build_plugin_record(agency_tools, agency_agents_root)
        if record:
            plugins.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "kind": "claude-skills",
                "root": str(claude_skills_root),
                "items": len(skills),
            },
            {
                "kind": "agency-agents",
                "root": str(agency_agents_root),
                "items": len(agents),
            },
        ],
        "skills": skills,
        "agents": agents,
        "plugins": plugins,
        "counts": {
            "skills": len(skills),
            "agents": len(agents),
            "plugins": len(plugins),
        },
    }


def write_external_catalog(catalog: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(catalog, f, allow_unicode=True, sort_keys=False)
    return path


def load_external_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def register_catalog_skills(registry: Any, catalog: dict[str, Any]) -> int:
    skills = catalog.get("skills", [])
    if not skills:
        return 0
    registry.load_from_dicts(skills)
    return len(skills)


def register_catalog_agents(registry: Any, catalog: dict[str, Any]) -> int:
    agents = catalog.get("agents", [])
    if not agents:
        return 0
    registry.load_from_dicts(agents)
    return len(agents)


def catalog_path_for(base_dir: Path) -> Path:
    return base_dir / ".voly" / "catalog" / _DEFAULT_CATALOG_NAME
