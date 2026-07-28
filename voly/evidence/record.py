"""EvidenceRecord construction from an executor result."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from voly import __version__
from voly.evidence.classifier import classify_root_cause
from voly.evidence.schema import (
    EvidenceOutcome,
    EvidenceRecord,
    ExecutionBundle,
    RepositoryBaseline,
)


def build_evidence_record(
    *,
    task_id: str,
    task: str,
    task_type: str,
    agent: str,
    executor: str,
    result: Any,
    baseline: RepositoryBaseline,
    error_class: str,
    retry_count: int,
    total_cost_usd: float,
    eval_policy_id: str = "executor-basic",
    eval_policy_version: str = "1",
    skills: list[dict[str, str]] | None = None,
) -> EvidenceRecord:
    metadata = getattr(result, "metadata", None) or {}
    report = getattr(result, "report", None)
    changed = set(getattr(report, "files_changed", None) or [])
    changed.update(getattr(report, "files_created", None) or [])
    root = classify_root_cause(
        success=bool(getattr(result, "success", False)),
        error_class=error_class,
        error=str(getattr(result, "error", "") or ""),
        baseline=baseline,
    )
    return EvidenceRecord(
        task_id=task_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        task_type=task_type or "unknown",
        task_fingerprint=hashlib.sha256((task or "").encode("utf-8")).hexdigest(),
        baseline=baseline,
        execution=ExecutionBundle(
            agent=agent,
            executor=executor,
            model=str(metadata.get("model") or ""),
            provider=str(metadata.get("provider") or ""),
            runtime_version=__version__,
            skills=list(skills or []),
            eval_policy_id=eval_policy_id,
            eval_policy_version=eval_policy_version,
        ),
        outcome=EvidenceOutcome(
            success=bool(getattr(result, "success", False)),
            state=root.state,
            failure_class=root.failure_class,
            error_class=error_class or "",
            penalize_agent=root.penalize_agent,
            cost_usd=float(total_cost_usd or 0.0),
            duration_ms=float(getattr(result, "duration_ms", 0.0) or 0.0),
            retries=int(retry_count or 0),
            files_changed=len(changed),
        ),
    )
