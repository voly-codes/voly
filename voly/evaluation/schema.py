"""Versioned schemas for deterministic run evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

EVAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EvalRequirement:
    """One evaluator required by a policy."""

    id: str
    evaluator: str
    required: bool = True


@dataclass(frozen=True)
class EvalPolicy:
    """Versioned definition of success for a task class."""

    id: str
    version: str
    task_types: tuple[str, ...]
    requirements: tuple[EvalRequirement, ...]


@dataclass
class EvalCheckResult:
    """Observed result from one evaluator."""

    id: str
    evaluator: str
    status: str
    required: bool = True
    message: str = ""
    duration_ms: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalCheckResult:
        return cls(
            id=str(data.get("id") or "unknown"),
            evaluator=str(data.get("evaluator") or "unknown"),
            status=str(data.get("status") or "error"),
            required=bool(data.get("required", True)),
            message=str(data.get("message") or ""),
            duration_ms=float(data.get("duration_ms") or 0.0),
            detail=dict(data.get("detail") or {}),
        )


@dataclass
class EvalReport:
    """Deterministic evaluation report attached to an EvidenceRecord."""

    policy_id: str
    policy_version: str
    state: str
    started_at: str
    completed_at: str
    checks: list[EvalCheckResult] = field(default_factory=list)
    schema_version: int = EVAL_SCHEMA_VERSION
    deterministic_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalReport:
        return cls(
            policy_id=str(data.get("policy_id") or "unknown"),
            policy_version=str(data.get("policy_version") or "1"),
            state=str(data.get("state") or "partial_success"),
            started_at=str(data.get("started_at") or ""),
            completed_at=str(data.get("completed_at") or ""),
            checks=[
                EvalCheckResult.from_dict(item)
                for item in (data.get("checks") or [])
                if isinstance(item, dict)
            ],
            schema_version=int(data.get("schema_version") or EVAL_SCHEMA_VERSION),
            deterministic_only=bool(data.get("deterministic_only", True)),
        )
