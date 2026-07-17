"""Report local runs to a linked VOLY Cloud control plane.

When a laptop is linked to an org (``cloud:`` in voly.yaml, device-code
``voly cloud login``, or ``VOLY_CLOUD_*`` env), every finished run is reported
so the team sees one shared history alongside hosted runs.

Control-plane endpoint: ``POST /cloud/v1/tenants/{tenant_id}/runs/report``,
authenticated with a **device-bound** tenant edge JWT. Best-effort: metadata
only (task text capped, cost, files touched — never file contents).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from voly.telemetry import USER_AGENT, TaskEvent, load_events

logger = logging.getLogger(__name__)

_TASK_CAP = 500
_SUMMARY_CAP = 500

LINK_FILE_ENV = "VOLY_CLOUD_LINK_FILE"
_DEFAULT_LINK_FILE = Path(".voly") / "cloud.json"

_heartbeat_stop = threading.Event()
_heartbeat_thread: threading.Thread | None = None


def link_file_path() -> Path:
    override = os.environ.get(LINK_FILE_ENV, "").strip()
    return Path(override) if override else _DEFAULT_LINK_FILE


def read_link_file(path: Path | None = None) -> dict[str, Any] | None:
    target = path or link_file_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_link_file(data: dict[str, Any], path: Path | None = None) -> Path:
    target = path or link_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def delete_link_file(path: Path | None = None) -> bool:
    target = path or link_file_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False


def resolve_cloud_link(config: Any | None = None) -> dict[str, Any] | None:
    """Effective cloud link: explicit ``cloud:`` config/env first, else login file."""
    cloud = getattr(config, "cloud", None) if config is not None else None
    if cloud is not None and getattr(cloud, "enabled", False):
        base = (cloud.base_url or "").strip().rstrip("/")
        tenant_id = (cloud.tenant_id or "").strip()
        token = (cloud.token or "").strip()
        if base and tenant_id and token:
            return {
                "base_url": base,
                "tenant_id": tenant_id,
                "token": token,
                "user_id": (cloud.user_id or "").strip(),
                "device_id": str(getattr(cloud, "device_id", "") or "").strip(),
                "timeout_seconds": float(getattr(cloud, "timeout_seconds", 5.0) or 5.0),
            }
        logger.debug("cloud link enabled but base_url/tenant_id/token incomplete — skipping")
        return None
    link = read_link_file()
    if not link:
        return None
    base = str(link.get("base_url") or "").strip().rstrip("/")
    tenant_id = str(link.get("tenant_id") or "").strip()
    token = str(link.get("token") or "").strip()
    if not (base and tenant_id and token):
        return None
    return {
        "base_url": base,
        "tenant_id": tenant_id,
        "token": token,
        "user_id": str(link.get("user_id") or "").strip(),
        "device_id": str(link.get("device_id") or "").strip(),
        "timeout_seconds": 5.0,
    }


def _files_touched(event: TaskEvent) -> list[str]:
    report = event.report or {}
    files: list[str] = []
    for key in ("files_changed", "files_created", "files_deleted"):
        value = report.get(key)
        if isinstance(value, list):
            files.extend(str(f) for f in value)
    return files


def build_report_body(event: TaskEvent, *, user_id: str = "") -> dict[str, Any]:
    """Metadata-only run record matching the control plane's report schema."""
    report = event.report or {}
    summary = report.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = (event.result or "")[:_SUMMARY_CAP]
    return {
        "run_id": event.task_id,
        "task": (event.task_prompt or event.task_id)[:_TASK_CAP],
        "success": event.status == "completed",
        "status": event.status,
        "executor": event.executor or event.agent,
        "cost_usd": event.cost_usd,
        "files_touched": _files_touched(event),
        "summary": summary[:_SUMMARY_CAP],
        "user_id": user_id or None,
    }


def _request(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return int(resp.status), parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return int(exc.code), parsed if isinstance(parsed, dict) else {"detail": raw}


def send_heartbeat(config: Any | None = None, *, version: str = "") -> bool:
    """POST device heartbeat. No-op when unlinked or device_id missing."""
    link = resolve_cloud_link(config)
    if link is None:
        return False
    device_id = link.get("device_id") or ""
    if not device_id:
        logger.debug("cloud heartbeat skipped — no device_id in link")
        return False
    url = (
        f"{link['base_url']}/cloud/v1/tenants/{link['tenant_id']}"
        f"/devices/{device_id}/heartbeat"
    )
    body: dict[str, Any] = {}
    if version:
        body["version"] = version
    try:
        status, _ = _request(
            "POST", url, token=link["token"], body=body or {}, timeout=link["timeout_seconds"]
        )
        return 200 <= status < 300
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("cloud heartbeat failed: %s", exc)
        return False


def start_heartbeat_loop(config: Any | None = None, *, interval: float = 30.0) -> bool:
    """Background heartbeats while `voly ui` (or similar) is running."""
    global _heartbeat_thread
    link = resolve_cloud_link(config)
    if link is None or not link.get("device_id"):
        return False
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        return True
    _heartbeat_stop.clear()

    def _loop() -> None:
        while not _heartbeat_stop.wait(timeout=max(5.0, interval)):
            send_heartbeat(config)

    send_heartbeat(config)
    _heartbeat_thread = threading.Thread(target=_loop, name="voly-cloud-heartbeat", daemon=True)
    _heartbeat_thread.start()
    return True


def stop_heartbeat_loop() -> None:
    _heartbeat_stop.set()


def report_run_event(event: TaskEvent, config: Any | None = None) -> bool:
    """POST one finished run to the linked control plane. Returns True on 2xx."""
    link = resolve_cloud_link(config)
    if link is None:
        return False

    url = f"{link['base_url']}/cloud/v1/tenants/{link['tenant_id']}/runs/report"
    body = build_report_body(event, user_id=link["user_id"])
    try:
        status, _ = _request(
            "POST", url, token=link["token"], body=body, timeout=link["timeout_seconds"]
        )
        if 200 <= status < 300:
            send_heartbeat(config)
            return True
        logger.debug("cloud run report failed: HTTP %s", status)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("cloud run report failed: %s", exc)
    return False


def sync_local_events(
    config: Any | None = None,
    *,
    since_days: int = 30,
    limit: int = 200,
    dry_run: bool = False,
    events_dir: str | Path | None = None,
) -> dict[str, int]:
    """Upload historical `.voly/events` to the linked org (idempotent by run_id)."""
    link = resolve_cloud_link(config)
    counts = {"synced": 0, "skipped": 0, "failed": 0}
    if link is None:
        return counts

    target = Path(events_dir) if events_dir else Path(".voly") / "events"
    cutoff = time.time() - max(0, since_days) * 86400
    # Prefer filesystem mtime for "since" filtering (TaskEvent has no timestamp).
    paths = sorted(target.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if target.exists() else []
    uploaded = 0
    events_by_id = {e.task_id: e for e in load_events(target)}
    for path in paths:
        if uploaded >= limit:
            break
        try:
            mtime = path.stat().st_mtime
        except OSError:
            counts["skipped"] += 1
            continue
        if mtime < cutoff:
            counts["skipped"] += 1
            continue
        task_id = path.stem
        event = events_by_id.get(task_id)
        if event is None:
            counts["skipped"] += 1
            continue
        if dry_run:
            counts["synced"] += 1
            uploaded += 1
            continue
        if report_run_event(event, config):
            counts["synced"] += 1
        else:
            counts["failed"] += 1
        uploaded += 1
    return counts
