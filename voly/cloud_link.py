"""Report local runs to a linked VOLY Cloud control plane.

When a laptop is linked to an org (``cloud:`` in voly.yaml, or the env
overrides listed in .env.example), every finished run is reported to the
control plane so the whole team
sees one shared history alongside hosted runs — the "local agent reports run"
leg of voly-cloud's product journey.

Control-plane endpoint: ``POST /cloud/v1/tenants/{tenant_id}/runs/report``,
authenticated with the tenant edge JWT (org manifest), not a user session
token. Best-effort like the rest of telemetry: metadata only (task text
capped, cost, files touched — never file contents), and it never raises into
the run path.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from voly.telemetry import USER_AGENT, TaskEvent

logger = logging.getLogger(__name__)

_TASK_CAP = 500
_SUMMARY_CAP = 500

# Device link written by `voly cloud login` — lives next to the rest of the
# project's generated state (never committed; .voly/ is git-ignored).
LINK_FILE_ENV = "VOLY_CLOUD_LINK_FILE"
_DEFAULT_LINK_FILE = Path(".voly") / "cloud.json"


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
        target.chmod(0o600)  # holds the tenant JWT
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


def resolve_cloud_link(config: Any | None) -> dict[str, Any] | None:
    """Effective cloud link: explicit ``cloud:`` config/env first, else the
    device link written by ``voly cloud login``. Returns None when unlinked."""
    cloud = getattr(config, "cloud", None)
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


def report_run_event(event: TaskEvent, config: Any | None = None) -> bool:
    """POST one finished run to the linked control plane. Returns True on 2xx.

    Silently a no-op when the device is not linked (neither ``cloud:``
    config/env nor a ``voly cloud login`` link file); delivery failures are
    logged at debug level and never propagate.
    """
    link = resolve_cloud_link(config)
    if link is None:
        return False

    url = f"{link['base_url']}/cloud/v1/tenants/{link['tenant_id']}/runs/report"
    body = json.dumps(
        build_report_body(event, user_id=link["user_id"]), ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {link['token']}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=link["timeout_seconds"]) as resp:
            resp.read()
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.debug("cloud run report failed: HTTP %s", exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("cloud run report failed: %s", exc)
    return False
