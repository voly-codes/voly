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
import urllib.error
import urllib.request
from typing import Any

from voly.telemetry import USER_AGENT, TaskEvent

logger = logging.getLogger(__name__)

_TASK_CAP = 500
_SUMMARY_CAP = 500


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

    Silently a no-op when the cloud link is disabled or incomplete; delivery
    failures are logged at debug level and never propagate.
    """
    cloud = getattr(config, "cloud", None)
    if cloud is None or not getattr(cloud, "enabled", False):
        return False
    base = (cloud.base_url or "").strip().rstrip("/")
    tenant_id = (cloud.tenant_id or "").strip()
    token = (cloud.token or "").strip()
    if not (base and tenant_id and token):
        logger.debug("cloud link enabled but base_url/tenant_id/token incomplete — skipping")
        return False

    url = f"{base}/cloud/v1/tenants/{tenant_id}/runs/report"
    body = json.dumps(
        build_report_body(event, user_id=cloud.user_id), ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    timeout = float(getattr(cloud, "timeout_seconds", 5.0) or 5.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.debug("cloud run report failed: HTTP %s", exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("cloud run report failed: %s", exc)
    return False
