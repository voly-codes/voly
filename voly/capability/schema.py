"""Capability profile schema — dataclasses only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CapabilityDomain:
    score: float = 0.5
    confidence: float = 0.0
    sub_scores: dict[str, float] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


@dataclass
class ConstraintsInfo:
    context_window: int = 0
    file_tools: bool = True
    browser_tools: bool = False
    image_input: bool = False
    max_output_tokens: int = 0


@dataclass
class EvidenceInfo:
    internal_runs: int = 0
    successful_runs: int = 0
    last_evaluated_at: str | None = None
    benchmark_sources: list[dict] = field(default_factory=list)


@dataclass
class OperationalInfo:
    avg_latency_ms: float = 0.0
    completion_rate: float = 1.0
    retry_rate: float = 0.0
    cost_per_task_usd: float = 0.0
    total_runs: int = 0


@dataclass
class ExecutorCapabilityProfile:
    id: str
    kind: str
    provider: str = ""
    model: str = ""
    capabilities: dict[str, CapabilityDomain] = field(default_factory=dict)
    constraints: ConstraintsInfo = field(default_factory=ConstraintsInfo)
    evidence: EvidenceInfo = field(default_factory=EvidenceInfo)
    operational: OperationalInfo = field(default_factory=OperationalInfo)

    @classmethod
    def unknown(cls, executor_id: str, kind: str = "executor") -> ExecutorCapabilityProfile:
        return cls(
            id=executor_id,
            kind=kind,
            capabilities={},
            constraints=ConstraintsInfo(file_tools=True),
            evidence=EvidenceInfo(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutorCapabilityProfile:
        caps_raw = data.get("capabilities") or {}
        capabilities = {
            name: _capability_domain_from_dict(raw)
            for name, raw in caps_raw.items()
        }
        constraints_raw = data.get("constraints") or {}
        evidence_raw = data.get("evidence") or {}
        operational_raw = data.get("operational") or {}
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind") or "executor"),
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            capabilities=capabilities,
            constraints=ConstraintsInfo(
                context_window=int(constraints_raw.get("context_window") or 0),
                file_tools=bool(constraints_raw.get("file_tools", True)),
                browser_tools=bool(constraints_raw.get("browser_tools", False)),
                image_input=bool(constraints_raw.get("image_input", False)),
                max_output_tokens=int(constraints_raw.get("max_output_tokens") or 0),
            ),
            evidence=EvidenceInfo(
                internal_runs=int(evidence_raw.get("internal_runs") or 0),
                successful_runs=int(evidence_raw.get("successful_runs") or 0),
                last_evaluated_at=evidence_raw.get("last_evaluated_at"),
                benchmark_sources=list(evidence_raw.get("benchmark_sources") or []),
            ),
            operational=OperationalInfo(
                avg_latency_ms=float(operational_raw.get("avg_latency_ms") or 0.0),
                completion_rate=float(operational_raw.get("completion_rate", 1.0)),
                retry_rate=float(operational_raw.get("retry_rate") or 0.0),
                cost_per_task_usd=float(operational_raw.get("cost_per_task_usd") or 0.0),
                total_runs=int(operational_raw.get("total_runs") or 0),
            ),
        )


@dataclass
class CapabilityMatchResult:
    recommended: ExecutorCapabilityProfile | None
    score: float
    fallbacks: list[tuple[ExecutorCapabilityProfile, float]]
    excluded: list[tuple[str, str]]
    degraded: bool = False


def _capability_domain_from_dict(data: dict[str, Any]) -> CapabilityDomain:
    sub_scores_raw = data.get("sub_scores") or {}
    return CapabilityDomain(
        score=float(data.get("score", 0.5)),
        confidence=float(data.get("confidence", 0.0)),
        sub_scores={k: float(v) for k, v in sub_scores_raw.items()},
        strengths=[str(s) for s in (data.get("strengths") or [])],
        weaknesses=[str(w) for w in (data.get("weaknesses") or [])],
    )
