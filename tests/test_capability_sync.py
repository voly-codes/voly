"""Tests for voly.capability.sync (Phase 5.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_sync_roles_no_worker():
    from voly.capability.sync import sync_roles_to_worker

    result = sync_roles_to_worker("", timeout_s=1.0)
    assert result is False


def test_sync_roles_success():
    from voly.capability.sync import sync_roles_to_worker

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True, "upserted": 7}
        mock_post.return_value = mock_resp
        result = sync_roles_to_worker("http://localhost:8787", timeout_s=1.0)
    assert result is True


def test_sync_seeds_no_worker():
    from voly.capability.sync import sync_seeds_to_worker

    result = sync_seeds_to_worker("", timeout_s=1.0)
    assert result is False


def test_sync_seeds_success():
    from voly.capability.sync import sync_seeds_to_worker

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True, "seeded": 7, "skipped": 0}
        mock_post.return_value = mock_resp
        result = sync_seeds_to_worker("http://localhost:8787", timeout_s=1.0)
    assert result is True


def test_startup_sync_no_raise():
    from voly.capability.sync import startup_sync

    startup_sync("")
