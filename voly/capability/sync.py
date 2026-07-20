"""Startup sync of roles and capability seeds to CF Worker."""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict

_log = logging.getLogger("voly.capability.sync")


def _worker_base_url(worker_url: str) -> str:
    return (worker_url or "").strip().rstrip("/")


def sync_roles_to_worker(worker_url: str, timeout_s: float = 5.0) -> bool:
    """POST ROLE_REGISTRY to CF Worker POST /roles/sync. Never raises."""
    url = _worker_base_url(worker_url)
    if not url:
        return False
    try:
        import httpx
        from voly.a2a.roles import ROLE_REGISTRY

        roles = [asdict(role) for role in ROLE_REGISTRY.values()]
        resp = httpx.post(
            f"{url}/roles/sync",
            json={"roles": roles},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        return bool(isinstance(data, dict) and data.get("ok"))
    except Exception as exc:  # noqa: BLE001
        _log.debug("sync_roles_to_worker failed: %s", exc)
        return False


def sync_seeds_to_worker(
    worker_url: str, seeds_dir: str | None = None, timeout_s: float = 30.0
) -> bool:
    """POST seed profiles to CF Worker POST /profiles/seed. Never raises."""
    url = _worker_base_url(worker_url)
    if not url:
        return False
    try:
        import httpx
        from voly.capability.sync_payloads import load_seed_payloads

        profiles = load_seed_payloads(seeds_dir)
        if not profiles:
            _log.debug("sync_seeds_to_worker: no seed profiles found")
            return False
        resp = httpx.post(
            f"{url}/profiles/seed",
            json={"profiles": profiles},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        return bool(isinstance(data, dict) and data.get("ok"))
    except Exception as exc:  # noqa: BLE001
        _log.debug("sync_seeds_to_worker failed: %s", exc)
        return False


def startup_sync(
    worker_url: str, seeds_dir: str | None = None, timeout_s: float = 5.0
) -> None:
    """Non-blocking daemon thread: sync roles + seeds. Never raises."""

    def _run() -> None:
        try:
            roles_ok = sync_roles_to_worker(worker_url, timeout_s)
            seeds_ok = sync_seeds_to_worker(worker_url, seeds_dir, timeout_s)
            _log.info(
                "startup_sync: roles=%s seeds=%s worker=%s",
                roles_ok,
                seeds_ok,
                worker_url,
            )
        except Exception as exc:  # noqa: BLE001
            _log.debug("startup_sync failed: %s", exc)

    threading.Thread(
        target=_run, daemon=True, name="voly-capability-sync"
    ).start()
