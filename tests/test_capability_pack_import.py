from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from voly.capability.packs import ExternalPackError, discover_ecc_pack
from voly.cli.commands.capability_cmd import capability_cmd


def _ecc_fixture(root: Path) -> Path:
    files = {
        "agents/architect.md": "# Architect\n",
        "skills/search-first/SKILL.md": "---\nname: search-first\n---\n",
        "rules/common/security.md": "# Security\n",
        "hooks/hooks.json": "{}\n",
        "mcp-configs/mcp-servers.json": "{}\n",
        "legacy-command-shims/commands/tdd.md": "# TDD\n",
        "package.json": json.dumps(
            {
                "name": "ecc-universal",
                "version": "2.1.0",
                "license": "MIT",
            }
        ),
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_discover_ecc_pack_inventory_is_deterministic(tmp_path: Path) -> None:
    root = _ecc_fixture(tmp_path / "ecc")

    report = discover_ecc_pack(root)

    assert report.pack_id == "ecc-universal"
    assert report.provenance.package_version == "2.1.0"
    assert report.provenance.license == "MIT"
    assert report.counts == {
        "agent": 1,
        "hook": 1,
        "legacy_command": 1,
        "mcp_config": 1,
        "rule": 1,
        "skill": 1,
    }
    assert [item.kind for item in report.components] == sorted(
        item.kind for item in report.components
    )
    assert report.dry_run is True


def test_discover_ecc_pack_rejects_invalid_package_json(tmp_path: Path) -> None:
    root = tmp_path / "ecc"
    root.mkdir()
    (root / "package.json").write_text("{", encoding="utf-8")

    with pytest.raises(ExternalPackError, match="invalid package.json"):
        discover_ecc_pack(root)


def test_discover_ecc_pack_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(ExternalPackError, match="does not exist"):
        discover_ecc_pack(tmp_path / "missing")


def test_capability_import_requires_dry_run(tmp_path: Path) -> None:
    root = _ecc_fixture(tmp_path / "ecc")

    result = CliRunner().invoke(
        capability_cmd,
        ["import", "ecc", "--source", str(root)],
    )

    assert result.exit_code == 2
    assert "--dry-run is required" in result.output


def test_capability_import_json_output(tmp_path: Path) -> None:
    root = _ecc_fixture(tmp_path / "ecc")

    result = CliRunner().invoke(
        capability_cmd,
        [
            "import",
            "ecc",
            "--source",
            str(root),
            "--dry-run",
            "--json-output",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["adapter"] == "ecc"
    assert payload["dry_run"] is True
    assert payload["counts"]["skill"] == 1
