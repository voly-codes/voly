from __future__ import annotations

import json
from pathlib import Path

from voly.registry.agents import AgentRegistry
from voly.registry.external_catalog import (
    build_external_catalog,
    catalog_path_for,
    write_external_catalog,
)
from voly.registry.skills import create_skill_registry


def _write_skill(root: Path) -> None:
    skill_dir = root / "domain" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        """---
name: Demo Skill
description: Demo skill for testing
version: 1.2.3
tags: [demo, test]
compatible_tools: [claude-code, cursor]
---

# Demo Skill

Do the demo thing.
""",
        encoding="utf-8",
    )
    skill_dir.joinpath(".claude-plugin").mkdir()
    skill_dir.joinpath(".claude-plugin", "plugin.json").write_text(
        json.dumps(
            {
                "name": "demo-plugin",
                "description": "Demo plugin",
                "version": "1.0.0",
                "author": {"name": "Acme", "url": "https://example.com"},
                "homepage": "https://example.com",
                "repository": "https://example.com/repo",
                "license": "MIT",
                "skills": ["./"],
            }
        ),
        encoding="utf-8",
    )


def _write_agent(root: Path) -> None:
    agent_dir = root / "engineering"
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_dir.joinpath("engineering-demo-agent.md").write_text(
        """---
name: Demo Agent
description: Demo agent for testing
model: claude-sonnet
color: cyan
emoji: 🧪
---

You are a demo agent.
""",
        encoding="utf-8",
    )
    root.joinpath("tools.json").write_text(
        json.dumps(
            {
                "tools": {
                    "demo": {
                        "id": "demo",
                        "label": "Demo Tool",
                        "installKind": "per-agent",
                        "format": "skill-md",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_build_and_load_external_catalog(tmp_path: Path, monkeypatch) -> None:
    claude_root = tmp_path / "claude-skills"
    agency_root = tmp_path / "agency-agents"
    claude_root.mkdir()
    agency_root.mkdir()
    _write_skill(claude_root)
    _write_agent(agency_root)

    catalog = build_external_catalog(claude_root, agency_root)
    assert catalog["counts"] == {"skills": 1, "agents": 1, "plugins": 2}
    assert catalog["skills"][0]["source"] == "organization"
    assert catalog["agents"][0]["metadata"]["registry_id"]

    out_path = catalog_path_for(tmp_path)
    write_external_catalog(catalog, out_path)

    reg = create_skill_registry(config_dir=tmp_path)
    assert reg.get(catalog["skills"][0]["id"]) is not None

    monkeypatch.chdir(tmp_path)
    agents = AgentRegistry()
    assert agents.get("Demo Agent") is not None
