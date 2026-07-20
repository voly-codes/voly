"""A2A evidence hooks — fire-and-forget capability updates after role runs."""

from __future__ import annotations

import logging
import threading
from typing import Any

_log = logging.getLogger("voly.a2a.core")

_DEFAULT_PROFILES_DIR = ".voly/capability/profiles"

_A2A_ROLES = frozenset({
    "architect",
    "developer",
    "tester",
    "reviewer",
    "devops",
    "security",
    "bugfixer",
    "documenter",
})

_ROLE_DIMENSION: dict[str, str] = {
    "developer": "backend",
    "bugfixer": "backend",
    "tester": "testing",
    "devops": "devops",
    "architect": "backend",
    "reviewer": "backend",
    "security": "backend",
    "documenter": "backend",
}


def is_a2a_role(role: str) -> bool:
    return (role or "").strip().lower() in _A2A_ROLES


def role_dimension(role: str) -> str:
    return _ROLE_DIMENSION.get((role or "").strip().lower(), "backend")


def emit_assignment_evidence(
    *,
    role: str,
    executor_id: str,
    success: bool,
    files_changed: int = 0,
    retry_count: int = 0,
    billing_error: bool = False,
    not_available: bool = False,
    duration_ms: float = 0.0,
    worker_url: str = "",
    profiles_dir: str = _DEFAULT_PROFILES_DIR,
    worker_timeout_s: float = 3.0,
) -> None:
    """Fire-and-forget evidence for one multi-agent role run. Never raises."""
    try:
        from voly.capability.evidence import RunRecord, record_run

        record = RunRecord(
            executor_id=executor_id,
            dimension=role_dimension(role),
            success=success,
            files_changed=files_changed,
            retry_count=retry_count,
            billing_error=billing_error,
            not_available=not_available,
            duration_ms=duration_ms,
        )
        threading.Thread(
            target=record_run,
            kwargs={
                "record": record,
                "worker_url": worker_url,
                "worker_timeout_s": worker_timeout_s,
                "profiles_dir": profiles_dir,
            },
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001
        _log.debug("emit_assignment_evidence failed: %s", exc)


def emit_assignment_from_result(
    assignment: Any,
    *,
    worker_url: str = "",
    profiles_dir: str = _DEFAULT_PROFILES_DIR,
    worker_timeout_s: float = 3.0,
) -> None:
    """Build evidence payload from a finalized Assignment. Never raises."""
    executor_id = (
        str(getattr(assignment, "executor", "") or "")
        or f"{getattr(assignment, 'provider', '')}/{getattr(assignment, 'model', '')}"
    ).strip("/") or "unknown"
    files = [
        f for f in (getattr(assignment, "files_touched", None) or [])
        if f and not str(f).startswith(".voly/")
    ]
    emit_assignment_evidence(
        role=str(getattr(assignment, "role", "") or "backend"),
        executor_id=executor_id,
        success=bool(getattr(assignment, "ok", False)),
        files_changed=len(files),
        duration_ms=float(getattr(assignment, "duration_ms", 0.0) or 0.0),
        worker_url=worker_url,
        profiles_dir=profiles_dir,
        worker_timeout_s=worker_timeout_s,
    )
