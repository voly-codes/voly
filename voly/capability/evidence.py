"""Fire-and-forget evidence collection after executor runs."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from voly.capability.registry import CapabilityRegistry
from voly.capability.schema import CapabilityDomain

_log = logging.getLogger("voly.capability.evidence")

_DEFAULT_PROFILES_DIR = ".voly/capability/profiles"
_EMA_ALPHA = 0.15
_CONFIDENCE_STEP = 0.02

_KNOWN_FEATURES = (
    "react", "svelte", "vue", "next.js", "fastapi", "django", "flask",
    "pytest", "jest", "vitest", "docker", "kubernetes", "terraform",
    "typescript", "python", "go",
)


@dataclass
class RunRecord:
    executor_id: str
    dimension: str
    success: bool
    files_changed: int = 0
    retry_count: int = 0
    billing_error: bool = False
    not_available: bool = False
    duration_ms: float = 0.0


def infer_dimension_from_task(task: str, default: str = "backend") -> str:
    """Map task text to a capability dimension via feature keywords."""
    from voly.capability.scorer import feature_to_dimension

    text = (task or "").lower()
    for feature in _KNOWN_FEATURES:
        if feature in text:
            dim = feature_to_dimension(feature)
            if dim:
                return dim
    return default


def resolve_run_dimension(task: str, agent_role: str = "") -> str:
    """Prefer A2A role dimension when agent_role is a known multi-agent role."""
    from voly.a2a.core import is_a2a_role, role_dimension

    role_key = (agent_role or "").strip().lower()
    if role_key and is_a2a_role(role_key):
        return role_dimension(role_key)
    return infer_dimension_from_task(task)


def _compute_run_score(record: RunRecord) -> float | None:
    if record.billing_error or record.not_available:
        return None
    if not record.success:
        return 0.0
    if record.files_changed <= 0:
        return 0.35
    score = 0.75 * (0.90 ** record.retry_count)
    return max(0.0, min(1.0, score))


def record_run(
    record: RunRecord,
    worker_url: str = "",
    worker_timeout_s: float = 3.0,
    profiles_dir: str = _DEFAULT_PROFILES_DIR,
) -> None:
    """Post evidence for one executor run. Never raises."""
    try:
        if record.billing_error or record.not_available:
            return
        run_score = _compute_run_score(record)
        if run_score is None:
            return
        _update_local_ema(
            record.executor_id,
            record.dimension,
            run_score,
            record.success,
            profiles_dir=profiles_dir,
        )
        url = (worker_url or "").strip().rstrip("/")
        if url:
            threading.Thread(
                target=_post_evidence,
                args=(
                    record.executor_id,
                    record.dimension,
                    run_score,
                    record.success,
                    record.files_changed,
                    url,
                    worker_timeout_s,
                ),
                daemon=True,
            ).start()
    except Exception as exc:  # noqa: BLE001
        _log.debug("record_run failed: %s", exc)


def fire_executor_evidence(
    *,
    executor_id: str,
    task: str,
    result: Any,
    retry_count: int = 0,
    agent_role: str = "",
    worker_url: str = "",
    profiles_dir: str = _DEFAULT_PROFILES_DIR,
    worker_timeout_s: float = 3.0,
) -> None:
    """Schedule fire-and-forget evidence from an ExecutorResult. Never raises."""
    try:
        files_changed = 0
        report = getattr(result, "report", None)
        if report is not None:
            files_changed = len(
                set(getattr(report, "files_changed", None) or [])
                | set(getattr(report, "files_created", None) or [])
            )
        record = RunRecord(
            executor_id=executor_id,
            dimension=resolve_run_dimension(task, agent_role),
            success=bool(not getattr(result, "error", "") and not result.billing_error),
            files_changed=files_changed,
            retry_count=retry_count,
            billing_error=bool(getattr(result, "billing_error", False)),
            not_available=bool(getattr(result, "not_available", False)),
            duration_ms=float(getattr(result, "duration_ms", 0.0) or 0.0),
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
        _log.debug("fire_executor_evidence failed: %s", exc)


def _post_evidence(
    executor_id: str,
    dimension: str,
    run_score: float,
    success: bool,
    files_changed: int,
    worker_url: str,
    timeout: float,
) -> None:
    try:
        import httpx

        httpx.post(
            f"{worker_url}/profiles/evidence",
            json={
                "executor_id": executor_id,
                "dimension": dimension,
                "run_score": run_score,
                "success": success,
                "files_changed": files_changed,
            },
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("evidence POST failed: %s", exc)


def _update_local_ema(
    executor_id: str,
    dimension: str,
    run_score: float,
    success: bool,
    *,
    profiles_dir: str = _DEFAULT_PROFILES_DIR,
) -> None:
    try:
        registry = CapabilityRegistry(profiles_dir)
        profile = registry.load(executor_id)
        domain = profile.capabilities.get(dimension)
        if domain is None:
            domain = CapabilityDomain(score=0.5, confidence=0.0)
            profile.capabilities[dimension] = domain
        domain.score = max(
            0.0,
            min(1.0, domain.score * (1.0 - _EMA_ALPHA) + run_score * _EMA_ALPHA),
        )
        domain.confidence = min(1.0, domain.confidence + _CONFIDENCE_STEP)
        profile.evidence.internal_runs += 1
        if success:
            profile.evidence.successful_runs += 1
        registry.save(profile)
    except Exception as exc:  # noqa: BLE001
        _log.debug("local EMA update failed: %s", exc)
