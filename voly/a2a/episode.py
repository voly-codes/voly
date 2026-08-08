"""Versioned multi-agent traces and episodes.

An episode is the orchestration-level record.  Existing ``EvidenceRecord`` and
``EvalReport`` objects remain the source of truth for executor evidence and
verification; traces link to those records instead of duplicating them.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EPISODE_SCHEMA_VERSION = 1
ROLE_METRIC_NAMES = frozenset(
    {
        "architecture_usefulness",
        "implementation_correctness",
        "test_coverage",
        "reviewer_precision",
        "cost_adjusted_contribution",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceMessage:
    role: str
    content: str
    created_at: str = field(default_factory=utc_now)
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    ok: bool = False
    duration_ms: float = 0.0
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceArtifact:
    kind: str
    uri: str
    title: str = ""
    digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceDecision:
    kind: str
    summary: str
    rationale: str = ""
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleMetric:
    name: str
    score: float
    source: str
    evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in ROLE_METRIC_NAMES:
            raise ValueError(f"unsupported role metric: {self.name}")
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("role metric score must be between 0 and 1")


@dataclass
class AgentTrace:
    trace_id: str
    agent_id: str
    role: str
    task: str
    status: str = "pending"
    started_at: str = field(default_factory=utc_now)
    completed_at: str = ""
    model: str = ""
    provider: str = ""
    executor: str = ""
    parent_trace_ids: list[str] = field(default_factory=list)
    messages: list[TraceMessage] = field(default_factory=list)
    tool_calls: list[TraceToolCall] = field(default_factory=list)
    artifacts: list[TraceArtifact] = field(default_factory=list)
    decisions: list[TraceDecision] = field(default_factory=list)
    metrics: list[RoleMetric] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, agent_id: str, role: str, task: str, **kwargs: Any) -> AgentTrace:
        return cls(trace_id=f"trace-{uuid.uuid4().hex}", agent_id=agent_id, role=role, task=task, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTrace:
        payload = dict(data)
        payload["messages"] = [TraceMessage(**item) for item in payload.get("messages", [])]
        payload["tool_calls"] = [TraceToolCall(**item) for item in payload.get("tool_calls", [])]
        payload["artifacts"] = [TraceArtifact(**item) for item in payload.get("artifacts", [])]
        payload["decisions"] = [TraceDecision(**item) for item in payload.get("decisions", [])]
        payload["metrics"] = [RoleMetric(**item) for item in payload.get("metrics", [])]
        return cls(**payload)


@dataclass
class MultiAgentEpisode:
    episode_id: str
    task_id: str
    task: str
    environment: str
    status: str = "running"
    started_at: str = field(default_factory=utc_now)
    completed_at: str = ""
    traces: list[AgentTrace] = field(default_factory=list)
    artifacts: list[TraceArtifact] = field(default_factory=list)
    decisions: list[TraceDecision] = field(default_factory=list)
    metrics: list[RoleMetric] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = EPISODE_SCHEMA_VERSION

    @classmethod
    def create(cls, *, task_id: str, task: str, environment: str, **kwargs: Any) -> MultiAgentEpisode:
        return cls(episode_id=f"episode-{uuid.uuid4().hex}", task_id=task_id, task=task, environment=environment, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultiAgentEpisode:
        payload = dict(data)
        payload["traces"] = [AgentTrace.from_dict(item) for item in payload.get("traces", [])]
        payload["artifacts"] = [TraceArtifact(**item) for item in payload.get("artifacts", [])]
        payload["decisions"] = [TraceDecision(**item) for item in payload.get("decisions", [])]
        payload["metrics"] = [RoleMetric(**item) for item in payload.get("metrics", [])]
        return cls(**payload)


class EpisodeStore:
    """Atomic local JSON store for orchestration episodes."""

    def __init__(self, store_dir: str | Path = ".voly/episodes") -> None:
        self.store_dir = Path(store_dir)

    def save(self, episode: MultiAgentEpisode) -> Path:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"{episode.task_id}.json"
        temporary = path.with_suffix(f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
        temporary.write_text(
            json.dumps(episode.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return path

    def load(self, task_id: str) -> MultiAgentEpisode | None:
        path = self.store_dir / f"{task_id}.json"
        if not path.is_file():
            return None
        return MultiAgentEpisode.from_dict(json.loads(path.read_text(encoding="utf-8")))


def episode_from_assignments(
    *,
    task_id: str,
    task: str,
    assignments: list[Any],
    acceptance_criteria: list[str] | None = None,
) -> MultiAgentEpisode:
    """Adapt the existing dependency-wave runtime to the Episode contract."""
    episode = MultiAgentEpisode.create(
        task_id=task_id,
        task=task,
        environment="pipeline",
        acceptance_criteria=list(acceptance_criteria or []),
    )
    trace_ids = {
        int(item.idx): f"trace-{uuid.uuid4().hex}"
        for item in assignments
    }
    total_cost = sum(float(getattr(item, "cost_usd", 0.0) or 0.0) for item in assignments)
    for assignment in assignments:
        assignment.trace_id = trace_ids[int(assignment.idx)]
        ok = bool(getattr(assignment, "ok", False))
        cost = float(getattr(assignment, "cost_usd", 0.0) or 0.0)
        contribution = 0.0 if not ok else 1.0 / (1.0 + (cost / max(total_cost, 0.000001)))
        cost_metric = RoleMetric(
            name="cost_adjusted_contribution",
            score=round(contribution, 4),
            source="runtime_proxy",
            evidence="Successful role outcome adjusted by its share of episode cost",
        )
        assignment.role_metrics = [asdict(cost_metric)]
        trace = AgentTrace(
            trace_id=assignment.trace_id,
            agent_id=f"agent-{assignment.idx}",
            role=str(assignment.role),
            task=str(assignment.description),
            status="completed" if ok else "failed",
            completed_at=utc_now(),
            model=str(getattr(assignment, "model", "") or ""),
            provider=str(getattr(assignment, "provider", "") or ""),
            executor=str(getattr(assignment, "executor", "") or ""),
            parent_trace_ids=[
                trace_ids[index]
                for index in (getattr(assignment, "depends_on", None) or [])
                if index in trace_ids
            ],
            messages=[
                TraceMessage(role="user", content=str(assignment.description)),
                TraceMessage(role="assistant", content=str(getattr(assignment, "content", "") or "")),
            ],
            tool_calls=[
                TraceToolCall(
                    name="executor_attempt",
                    arguments={"executor": item.get("executor"), "model": item.get("model")},
                    result=str(item.get("status") or ""),
                    ok=item.get("status") == "success",
                    duration_ms=float(item.get("duration_ms") or 0.0),
                    metadata={key: value for key, value in item.items() if key not in {"executor", "model", "status", "duration_ms"}},
                )
                for item in (getattr(assignment, "chain_timelog", None) or [])
                if isinstance(item, dict)
            ],
            artifacts=[
                TraceArtifact(kind="file", uri=str(path))
                for path in (getattr(assignment, "files_touched", None) or [])
            ],
            decisions=[
                TraceDecision(
                    kind="execution_route",
                    summary=f"Use {getattr(assignment, 'mode', 'chat')} mode",
                    rationale=str(getattr(assignment, "mode_reason", "") or ""),
                    metadata={"tier": getattr(assignment, "tier", ""), "skills": list(getattr(assignment, "skills", None) or [])},
                )
            ],
            metrics=[cost_metric],
            input_tokens=int(getattr(assignment, "input_tokens", 0) or 0),
            output_tokens=int(getattr(assignment, "output_tokens", 0) or 0),
            cost_usd=cost,
            duration_ms=float(getattr(assignment, "duration_ms", 0.0) or 0.0),
            error=str(getattr(assignment, "error", "") or ""),
            metadata={
                "plan_status": getattr(assignment, "plan_status", ""),
                "plan_verify_ok": getattr(assignment, "plan_verify_ok", None),
                "cache_hit": bool(getattr(assignment, "cache_hit", False)),
            },
        )
        episode.traces.append(trace)
        episode.metrics.append(cost_metric)
    episode.status = (
        "completed" if episode.traces and all(item.status == "completed" for item in episode.traces)
        else "partial" if any(item.status == "completed" for item in episode.traces)
        else "failed"
    )
    episode.completed_at = utc_now()
    episode.artifacts = [artifact for trace in episode.traces for artifact in trace.artifacts]
    return episode
