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
