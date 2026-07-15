"""Tests for ``voly skill seed --path`` (CF marketplace draft seeding)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from voly.cli.commands.skill import skill
from voly.registry.loader import load_skills_from_directory
from voly.registry.marketplace import MarketplaceError


def test_load_cf_draft_skills_from_docs(repo_root: Path | None = None) -> None:
    drafts = Path(__file__).resolve().parents[1] / "docs" / "marketplace" / "skills"
    skills = load_skills_from_directory(drafts)
    ids = {s.id for s in skills}
    assert "skill-cf-containers" in ids
    assert "skill-cf-agent-memory" in ids
    assert "skill-cf-run-correlation" in ids


def test_skill_seed_path_dry_run(tmp_path: Path) -> None:
    yaml_file = tmp_path / "skill-cf-demo.yaml"
    yaml_file.write_text(
        "id: skill-cf-demo\nname: Demo\ndescription: d\ncontent: c\ntags: [cloudflare]\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    with patch("voly.cli.commands.skill._marketplace_client") as mock_client_factory:
        mock_client_factory.return_value = MagicMock()
        result = runner.invoke(
            skill,
            ["seed", "--path", str(tmp_path), "--dry-run"],
            obj={"config": MagicMock(), "config_path": None},
        )

    assert result.exit_code == 0, result.output
    assert "would seed: skill-cf-demo" in result.output


def test_skill_seed_path_skips_existing(tmp_path: Path) -> None:
    yaml_file = tmp_path / "skill-cf-demo.yaml"
    yaml_file.write_text(
        "id: skill-cf-demo\nname: Demo\ndescription: d\ncontent: c\n",
        encoding="utf-8",
    )

    mp = MagicMock()
    mp.get_skill.return_value = {"id": "skill-cf-demo"}

    runner = CliRunner()
    with patch("voly.cli.commands.skill._marketplace_client", return_value=mp):
        result = runner.invoke(
            skill,
            ["seed", "--path", str(tmp_path)],
            obj={"config": MagicMock(), "config_path": None},
        )

    assert result.exit_code == 0, result.output
    assert "skip (exists): skill-cf-demo" in result.output
    mp.publish_skill.assert_not_called()


def test_skill_seed_path_publishes_missing(tmp_path: Path) -> None:
    yaml_file = tmp_path / "skill-cf-demo.yaml"
    yaml_file.write_text(
        "id: skill-cf-demo\nname: Demo\ndescription: d\ncontent: hello\n",
        encoding="utf-8",
    )

    mp = MagicMock()
    mp.get_skill.side_effect = MarketplaceError("HTTP 404: not found")
    mp.publish_skill.return_value = {"id": "skill-cf-demo"}

    runner = CliRunner()
    with patch("voly.cli.commands.skill._marketplace_client", return_value=mp):
        result = runner.invoke(
            skill,
            ["seed", "--path", str(tmp_path)],
            obj={"config": MagicMock(), "config_path": None},
        )

    assert result.exit_code == 0, result.output
    assert "seeded: skill-cf-demo" in result.output
    mp.publish_skill.assert_called_once()
    payload = mp.publish_skill.call_args[0][0]
    assert payload["id"] == "skill-cf-demo"
    assert payload["content"] == "hello"
