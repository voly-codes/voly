"""Extract PROJECT-source skills from real project files.

Reads CLAUDE.md, README.md, ARCHITECTURE.md, and project manifests
to build Skill objects with actual useful content.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


# Files read for project skills, in priority order
_DOC_SOURCES: list[tuple[str, list[str], str]] = [
    # (skill_suffix, candidate_paths, description_template)
    ("guidelines",  ["CLAUDE.md", ".claude/CLAUDE.md"],                       "Coding guidelines for {name}"),
    ("overview",    ["README.md", "README.rst", "README.txt"],                 "Project overview: {name}"),
    ("architecture",["docs/ARCHITECTURE.md", "ARCHITECTURE.md", "docs/architecture.md"], "Architecture: {name}"),
    ("agents",      ["AGENTS.md", ".codeops/AGENTS.md", "docs/AGENTS.md"],    "Agent instructions: {name}"),
    ("contributing",["CONTRIBUTING.md", "docs/CONTRIBUTING.md"],               "Contributing guide: {name}"),
]

# Max chars to include from each document (fits in one skill inject block)
_MAX_DOC_CHARS = 6000


def _project_id(project_name: str) -> str:
    return hashlib.sha256(project_name.encode()).hexdigest()[:8]


def _read_first(root: Path, paths: list[str]) -> tuple[str, str] | None:
    """Return (relative_path, content) for the first existing path."""
    for rel in paths:
        p = root / rel
        if p.exists() and p.is_file():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return rel, content
            except OSError:
                pass
    return None


def extract_from_docs(
    project_root: Path,
    project_name: str,
) -> list[dict[str, Any]]:
    """Generate PROJECT skills by reading real documentation files.

    Each file that exists and has content becomes its own skill.
    """
    pid = _project_id(project_name)
    skills: list[dict[str, Any]] = []

    for suffix, candidates, desc_tmpl in _DOC_SOURCES:
        found = _read_first(project_root, candidates)
        if not found:
            continue
        rel_path, content = found
        description = desc_tmpl.format(name=project_name)
        skills.append({
            "id": f"proj-{suffix}-{pid}",
            "name": f"{project_name}: {suffix.capitalize()}",
            "description": description,
            "source": "project",
            "status": "active",
            "tags": ["project", suffix, project_name.lower()],
            "capabilities": [suffix],
            "content": content[:_MAX_DOC_CHARS],
            "metadata": {"source_file": rel_path, "project": project_name},
        })

    return skills


def extract_from_stack(
    profile: Any,  # ProjectProfile from scanner
    project_name: str,
) -> list[dict[str, Any]]:
    """Generate a single consolidated stack skill from the project profile."""
    pid = _project_id(project_name)

    lines: list[str] = [f"# {project_name} — project stack\n"]
    lines.append(f"Architecture: {profile.architecture}")

    if profile.languages:
        langs = ", ".join(
            f"{l.name}" + (f" {l.version}" if l.version else "")
            for l in profile.languages
        )
        lines.append(f"Languages: {langs}")

    if profile.frameworks:
        lines.append(f"Frameworks: {', '.join(f.name for f in profile.frameworks)}")

    if profile.package_managers:
        lines.append(f"Package managers: {', '.join(profile.package_managers)}")

    if profile.infrastructure.databases:
        lines.append(f"Databases: {', '.join(profile.infrastructure.databases)}")

    if profile.infrastructure.docker:
        lines.append("Containerized: Docker")

    if profile.test_frameworks:
        lines.append(f"Testing: {', '.join(profile.test_frameworks)}")

    if profile.linter_tools:
        lines.append(f"Linters: {', '.join(profile.linter_tools)}")

    if profile.ci:
        lines.append(f"CI: {', '.join(c.provider for c in profile.ci)}")

    lines.append("\nFollow conventions and best practices for the stack above.")

    compatible_languages = [l.name for l in profile.languages]
    compatible_frameworks = [f.name for f in profile.frameworks]

    return [{
        "id": f"proj-stack-{pid}",
        "name": f"{project_name}: Stack",
        "description": f"Tech stack and conventions for {project_name}",
        "source": "project",
        "status": "active",
        "tags": ["project", "stack", project_name.lower()] + compatible_languages + compatible_frameworks,
        "capabilities": ["architecture", "system-design"],
        "compatible_languages": compatible_languages,
        "compatible_frameworks": compatible_frameworks,
        "content": "\n".join(lines),
        "metadata": {"project": project_name},
    }]


def generate_project_skills(
    project_root: Path | str,
    profile: Any,  # ProjectProfile
) -> list[dict[str, Any]]:
    """Main entry point: generate all PROJECT skills for a project.

    Returns a list of skill dicts ready to be passed to skill_from_dict().
    """
    root = Path(project_root).resolve()
    name = profile.name or root.name

    skills: list[dict[str, Any]] = []
    skills.extend(extract_from_docs(root, name))
    skills.extend(extract_from_stack(profile, name))
    return skills
