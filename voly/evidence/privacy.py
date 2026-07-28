"""Privacy boundary for optional remote EvidenceRecord analytics."""

from __future__ import annotations

import hashlib
from typing import Any

from voly.evidence.schema import EvidenceRecord

EVIDENCE_CLOUD_SCHEMA_VERSION = 1


def evidence_to_cloud_record(record: EvidenceRecord) -> dict[str, Any]:
    """Return a metadata-only allowlist with no raw repository observations."""
    checks = [
        {
            "name": check.name,
            "status": check.status,
            "exit_code": check.exit_code,
            "duration_ms": check.duration_ms,
            "failure_kind": check.failure_kind,
        }
        for check in record.baseline.checks
    ]
    skills = [
        {
            key: str(skill[key])
            for key in ("id", "version")
            if key in skill and str(skill[key]).strip()
        }
        for skill in record.execution.skills
        if isinstance(skill, dict)
    ]
    evidence_id = hashlib.sha256(
        f"voly-cloud-evidence:{record.task_id}".encode()
    ).hexdigest()
    return {
        "schema_version": EVIDENCE_CLOUD_SCHEMA_VERSION,
        "source_schema_version": record.schema_version,
        "evidence_id": evidence_id,
        "created_at": record.created_at,
        "task_type": record.task_type,
        "baseline": {
            "health": record.baseline.health,
            "stack": list(record.baseline.stack),
            "test_frameworks": list(record.baseline.test_frameworks),
            "package_managers": list(record.baseline.package_managers),
            "checks": checks,
        },
        "execution": {
            "agent": record.execution.agent,
            "executor": record.execution.executor,
            "model": record.execution.model,
            "provider": record.execution.provider,
            "runtime_version": record.execution.runtime_version,
            "skills": skills,
            "eval_policy_id": record.execution.eval_policy_id,
            "eval_policy_version": record.execution.eval_policy_version,
        },
        "outcome": {
            "success": record.outcome.success,
            "state": record.outcome.state,
            "failure_class": record.outcome.failure_class,
            "error_class": record.outcome.error_class,
            "penalize_agent": record.outcome.penalize_agent,
            "cost_usd": record.outcome.cost_usd,
            "duration_ms": record.outcome.duration_ms,
            "retries": record.outcome.retries,
            "files_changed": record.outcome.files_changed,
        },
        "human_feedback": [
            {"kind": item.kind, "source": item.source}
            for item in record.human_feedback
        ],
    }
