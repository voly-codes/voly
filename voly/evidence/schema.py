"""Versioned local evidence records for file-capable executor runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

EVIDENCE_SCHEMA_VERSION = 1


@dataclass
class BaselineCheck:
    """One deterministic repository-health check captured before execution."""

    name: str
    command: str
    status: str
    exit_code: int | None = None
    duration_ms: float = 0.0
    failure_kind: str = ""
    output_excerpt: str = ""


@dataclass
class RepositoryBaseline:
    """Repository state observed before an executor may edit files."""

    captured_at: str
    health: str
    stack: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    checks: list[BaselineCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def has_preexisting_failures(self) -> bool:
        return self.health in {"preexisting_failure", "environment_failure"}


@dataclass
class ExecutionBundle:
    """Exact execution identity used to keep evidence lineages separate."""

    agent: str
    executor: str
    model: str = ""
    provider: str = ""
    runtime_version: str = ""
    skills: list[dict[str, str]] = field(default_factory=list)
    eval_policy_id: str = "executor-basic"
    eval_policy_version: str = "1"


@dataclass
class EvidenceOutcome:
    """Observed run outcome plus root-cause attribution."""

    success: bool
    state: str
    failure_class: str = ""
    error_class: str = ""
    penalize_agent: bool = False
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    retries: int = 0
    files_changed: int = 0


@dataclass
class HumanFeedback:
    """Explicit or imported developer feedback, kept separate from automation."""

    kind: str
    recorded_at: str
    source: str = "explicit"
    comment: str = ""


@dataclass
class EvidenceRecord:
    """Unified local evidence bundle for one run."""

    task_id: str
    created_at: str
    task_type: str
    task_fingerprint: str
    baseline: RepositoryBaseline
    execution: ExecutionBundle
    outcome: EvidenceOutcome
    human_feedback: list[HumanFeedback] = field(default_factory=list)
    schema_version: int = EVIDENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        baseline_data = dict(data.get("baseline") or {})
        checks = [
            BaselineCheck(**item)
            for item in (baseline_data.pop("checks", []) or [])
            if isinstance(item, dict)
        ]
        feedback = [
            HumanFeedback(**item)
            for item in (data.get("human_feedback") or [])
            if isinstance(item, dict)
        ]
        return cls(
            task_id=str(data["task_id"]),
            created_at=str(data.get("created_at") or ""),
            task_type=str(data.get("task_type") or "unknown"),
            task_fingerprint=str(data.get("task_fingerprint") or ""),
            baseline=RepositoryBaseline(checks=checks, **baseline_data),
            execution=ExecutionBundle(**dict(data.get("execution") or {})),
            outcome=EvidenceOutcome(**dict(data.get("outcome") or {})),
            human_feedback=feedback,
            schema_version=int(data.get("schema_version") or EVIDENCE_SCHEMA_VERSION),
        )
