"""SkillScout surfaces CF marketplace draft skills (unit + optional live)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voly.registry.marketplace import MarketplaceClient
from voly.registry.scout import SkillScout

_MP_URL = "https://voly-marketplace.margolanies.workers.dev"


def _empty_registry() -> MagicMock:
    reg = MagicMock()
    reg.index.list_all.return_value = []
    return reg


def test_skill_scout_filters_local_and_returns_cf_ids() -> None:
    scout = SkillScout(_empty_registry(), _MP_URL)

    mp = MagicMock()
    mp.search.return_value = {
        "source": "semantic",
        "skills": [
            {"id": "skill-cf-containers", "name": "CF Containers", "description": "x", "tags": []},
            {"id": "skill-docker", "name": "Docker", "description": "y", "tags": []},
        ],
    }

    with patch("voly.registry.marketplace.MarketplaceClient", return_value=mp):
        hits = scout.find_missing("Cloudflare Containers without local CLI", limit=5)

    assert [h["id"] for h in hits] == ["skill-cf-containers", "skill-docker"]
    mp.search.assert_called_once()


def _marketplace_reachable() -> bool:
    try:
        MarketplaceClient(_MP_URL, timeout=8)._request("GET", "/health")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _marketplace_reachable(), reason="marketplace Worker unreachable")
def test_skill_scout_live_surfaces_cf_draft_skills() -> None:
    scout = SkillScout(_empty_registry(), _MP_URL)

    containers = scout.find_missing(
        "Run this probe in Cloudflare Containers without local Claude CLI",
        limit=8,
    )
    assert any(s["id"] == "skill-cf-containers" for s in containers)

    memory = scout.find_missing(
        "Use Cloudflare Agent Memory as remote shared memory backend",
        limit=8,
    )
    assert any(s["id"] == "skill-cf-agent-memory" for s in memory)

    corr = scout.find_missing(
        "Debug run with X-Correlation-ID in Workers logs",
        limit=8,
    )
    assert any(s["id"] == "skill-cf-run-correlation" for s in corr)
