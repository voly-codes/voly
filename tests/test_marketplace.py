"""Tests for skill marketplace client, loader, and registry integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from voly.registry.loader import (
    load_skills_from_directory,
    save_skill_yaml,
    skill_from_dict,
    skill_to_yaml_dict,
)
from voly.registry.marketplace import MarketplaceClient, MarketplaceError
from voly.registry.skills import (
    Skill,
    SkillSource,
    create_skill_registry,
    resolve_marketplace_url,
)


def test_skill_from_dict_and_yaml_roundtrip() -> None:
    skill = Skill(
        id="test-skill",
        name="Test Skill",
        description="A test skill",
        source=SkillSource.PROJECT,
        tags=["test"],
        content="Do the thing.",
    )
    data = skill_to_yaml_dict(skill)
    restored = skill_from_dict(data)
    assert restored.id == skill.id
    assert restored.name == skill.name
    assert restored.source == SkillSource.PROJECT


def test_load_skills_from_directory(tmp_path: Path) -> None:
    skill_file = tmp_path / "my-skill.yaml"
    skill_file.write_text(
        yaml.safe_dump(
            {
                "name": "My Skill",
                "description": "desc",
                "source": "project",
                "content": "body",
            }
        ),
        encoding="utf-8",
    )
    skills = load_skills_from_directory(tmp_path)
    assert len(skills) == 1
    assert skills[0].id == "my-skill"


def test_save_skill_yaml(tmp_path: Path) -> None:
    skill = skill_from_dict({"id": "saved", "name": "Saved", "content": "x"})
    path = save_skill_yaml(skill, tmp_path / "saved.yaml")
    assert path.exists()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["id"] == "saved"


def test_resolve_marketplace_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_MARKETPLACE_URL", raising=False)
    monkeypatch.delenv("MARKETPLACE_URL", raising=False)
    assert resolve_marketplace_url("") == ""

    monkeypatch.setenv("CF_WORKER_MARKETPLACE_URL", "https://example.com/")
    assert resolve_marketplace_url("") == "https://example.com"
    assert resolve_marketplace_url("${CF_WORKER_MARKETPLACE_URL}") == "https://example.com"


def test_marketplace_client_list_skills() -> None:
    client = MarketplaceClient("https://example.com")
    payload = {"skills": [{"id": "a", "name": "A"}], "total": 1}

    with patch("urllib.request.urlopen") as urlopen:
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        urlopen.return_value = resp

        data = client.list_skills(limit=5)
        assert data["total"] == 1
        assert data["skills"][0]["id"] == "a"


def test_marketplace_client_plugins() -> None:
    client = MarketplaceClient("https://example.com")
    payload = {"plugins": [{"id": "p", "name": "Plugin"}], "count": 1}

    with patch("urllib.request.urlopen") as urlopen:
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        urlopen.return_value = resp

        data = client.list_plugins(limit=5)
        assert data["count"] == 1
        assert data["plugins"][0]["id"] == "p"

    with patch("urllib.request.urlopen") as urlopen:
        resp = MagicMock()
        resp.read.return_value = json.dumps({"id": "p", "ok": True}).encode()
        resp.__enter__.return_value = resp
        urlopen.return_value = resp

        data = client.publish_plugin({"id": "p", "name": "Plugin"})
        assert data["ok"] is True


def test_install_from_marketplace(tmp_path: Path) -> None:
    reg = create_skill_registry(
        skills_path=tmp_path / "skills",
        marketplace_url="https://example.com",
    )
    mock_client = MagicMock()
    mock_client.download_skill.return_value = {
        "id": "skill-remote",
        "name": "Remote Skill",
        "description": "from marketplace",
        "content": "instructions",
        "tags": ["remote"],
    }

    skill = reg.install_from_marketplace("skill-remote", client=mock_client)
    assert skill.id == "skill-remote"
    assert skill.source == SkillSource.MARKETPLACE
    assert (tmp_path / "skills" / "skill-remote.yaml").exists()
    assert reg.get("skill-remote") is not None


def test_install_without_marketplace_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_MARKETPLACE_URL", raising=False)
    monkeypatch.delenv("MARKETPLACE_URL", raising=False)
    reg = create_skill_registry(marketplace_url="")
    with pytest.raises(MarketplaceError, match="marketplace_url"):
        reg.install_from_marketplace("skill-x")


# ─── Web route: local fallback path (Skill Marketplace drawer in dev) ────────
def test_marketplace_skills_route_local_fallback_no_url() -> None:
    """No CF_WORKER_MARKETPLACE_URL → route returns the local registry, no crash.

    Regression guard: the drawer calls /api/marketplace/skills on mount; when no
    remote marketplace is configured the handler must return local skills instead
    of raising (a missing `status` param used to make it 500 → empty drawer).
    """
    from voly.web.routes.marketplace import marketplace_skills

    request = MagicMock()
    request.app.state.app.marketplace_url.return_value = ""  # not configured

    rows = [{"id": "s1", "name": "Skill One"}, {"id": "s2", "name": "Skill Two"}]
    with patch("voly.web.routes.marketplace._local_skill_rows", return_value=rows):
        result = marketplace_skills(request)

    assert result["configured"] is False
    assert result["skills"] == rows
    assert result["total"] == 2
    assert "hint" in result


# ─── Web route: bulk plugin sync proxy ───────────────────────────────────────
def test_marketplace_plugins_sync_requires_url() -> None:
    from fastapi import HTTPException

    from voly.web.routes.marketplace import marketplace_plugins_sync

    request = MagicMock()
    request.app.state.app.marketplace_url.return_value = ""
    with pytest.raises(HTTPException) as exc:
        marketplace_plugins_sync(request, {"plugins": [{"id": "p1"}]})
    assert exc.value.status_code == 503


def test_marketplace_plugins_sync_proxies_to_worker() -> None:
    from voly.web.routes.marketplace import marketplace_plugins_sync

    request = MagicMock()
    request.app.state.app.marketplace_url.return_value = "https://mp.example"

    with patch("voly.registry.marketplace.MarketplaceClient") as MC:
        MC.return_value.sync_plugins.return_value = {"upserted": 2}
        result = marketplace_plugins_sync(request, {"plugins": [{"id": "p1"}, {"id": "p2"}]})

    MC.return_value.sync_plugins.assert_called_once_with({"plugins": [{"id": "p1"}, {"id": "p2"}]})
    assert result == {"upserted": 2, "configured": True}
