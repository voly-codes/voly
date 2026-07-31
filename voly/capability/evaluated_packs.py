"""Evaluated agent/skill packs layered over native executor matching."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from voly.capability.matcher import ExecutorMatcher, MatchRequest


class PackState(str, Enum):
    PILOT = "pilot"
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True)
class CapabilityInput:
    task: str
    role: str
    project_features: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CapabilityOutput:
    capability_id: str
    completion: bool
    findings: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class SuccessCriteria:
    min_completion_rate: float = 0.7
    min_test_pass_rate: float = 0.7
    min_reviewer_acceptance: float = 0.6
    max_rollback_rate: float = 0.2
    max_correction_rate: float = 0.3
    min_paired_delta: float = 0.01
    min_samples: int = 3


@dataclass
class EvaluatedCapabilityPack:
    capability_id: str
    version: int
    role: str
    dimension: str
    triggers: list[str]
    input_contract: str
    output_contract: str
    success_criteria: SuccessCriteria
    state: PackState = PackState.PILOT
    origin: str = "builtin"
    evidence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluatedCapabilityPack:
        return cls(
            capability_id=data["capability_id"],
            version=int(data["version"]),
            role=data["role"],
            dimension=data["dimension"],
            triggers=list(data["triggers"]),
            input_contract=data["input_contract"],
            output_contract=data["output_contract"],
            success_criteria=SuccessCriteria(**data["success_criteria"]),
            state=PackState(data.get("state", "pilot")),
            origin=data.get("origin", "builtin"),
            evidence_count=int(data.get("evidence_count", 0)),
        )


@dataclass(frozen=True)
class CapabilityRunEvidence:
    capability_id: str
    executor_id: str
    run_id: str
    completion: bool
    tests_passed: bool
    rollback: bool
    corrections: int
    cost_usd: float
    latency_ms: float
    retries: int
    reviewer_accepted: bool
    baseline_score: float
    variant_score: float
    held_out: bool = False
    experiment_id: str = ""
    changed_capabilities: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CapabilityMetrics:
    capability_id: str
    executor_id: str
    samples: int
    completion_rate: float
    test_pass_rate: float
    rollback_rate: float
    correction_rate: float
    avg_cost_usd: float
    avg_latency_ms: float
    avg_retries: float
    reviewer_acceptance: float
    paired_delta: float
    held_out_samples: int


@dataclass(frozen=True)
class EvaluatedRoute:
    role: str
    capability_id: str
    executor: str
    model: str
    native_fallback: bool
    reason: str


def pilot_packs() -> list[EvaluatedCapabilityPack]:
    criteria = SuccessCriteria()
    return [
        EvaluatedCapabilityPack(
            "security-reviewer", 1, "security", "security",
            ["security", "secret", "vulnerability", "auth", "threat"],
            "CapabilityInput.v1", "CapabilityOutput.v1", criteria,
        ),
        EvaluatedCapabilityPack(
            "tdd-workflow", 1, "tester", "testing",
            ["tdd", "test-first", "regression", "failing test", "pytest"],
            "CapabilityInput.v1", "CapabilityOutput.v1", criteria,
        ),
        EvaluatedCapabilityPack(
            "python-reviewer", 1, "reviewer", "backend",
            ["python", "pytest", "ruff", "type hint", "pyproject"],
            "CapabilityInput.v1", "CapabilityOutput.v1", criteria,
        ),
    ]


class EvaluatedPackStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.packs_path = self.root / "packs.json"
        self.evidence_path = self.root / "evidence.jsonl"

    def initialize(self) -> list[EvaluatedCapabilityPack]:
        if self.packs_path.is_file():
            return self.load_packs()
        self.save_packs(pilot_packs())
        return self.load_packs()

    def load_packs(self) -> list[EvaluatedCapabilityPack]:
        if not self.packs_path.is_file():
            return []
        return [
            EvaluatedCapabilityPack.from_dict(item)
            for item in json.loads(self.packs_path.read_text(encoding="utf-8"))
        ]

    def save_packs(self, packs: list[EvaluatedCapabilityPack]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([pack.to_dict() for pack in packs], indent=2) + "\n"
        temporary = self.packs_path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.packs_path)

    def record(self, evidence: CapabilityRunEvidence) -> None:
        if evidence.changed_capabilities and evidence.changed_capabilities != [
            evidence.capability_id
        ]:
            raise ValueError("paired experiment must change exactly one capability")
        self.root.mkdir(parents=True, exist_ok=True)
        with self.evidence_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(evidence), ensure_ascii=False) + "\n")
        packs = self.load_packs()
        for pack in packs:
            if pack.capability_id == evidence.capability_id:
                pack.evidence_count += 1
        self.save_packs(packs)

    def evidence(self, capability_id: str = "") -> list[CapabilityRunEvidence]:
        if not self.evidence_path.is_file():
            return []
        rows = [
            CapabilityRunEvidence(**json.loads(line))
            for line in self.evidence_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [row for row in rows if not capability_id or row.capability_id == capability_id]

    def metrics(self, capability_id: str, executor_id: str) -> CapabilityMetrics:
        rows = [
            row for row in self.evidence(capability_id)
            if row.executor_id == executor_id
        ]
        count = len(rows)
        if not count:
            return CapabilityMetrics(
                capability_id, executor_id, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
            )
        def mean(values: list[float]) -> float:
            return sum(values) / count
        return CapabilityMetrics(
            capability_id=capability_id,
            executor_id=executor_id,
            samples=count,
            completion_rate=mean([float(row.completion) for row in rows]),
            test_pass_rate=mean([float(row.tests_passed) for row in rows]),
            rollback_rate=mean([float(row.rollback) for row in rows]),
            correction_rate=mean([float(row.corrections > 0) for row in rows]),
            avg_cost_usd=mean([row.cost_usd for row in rows]),
            avg_latency_ms=mean([row.latency_ms for row in rows]),
            avg_retries=mean([float(row.retries) for row in rows]),
            reviewer_acceptance=mean([float(row.reviewer_accepted) for row in rows]),
            paired_delta=mean([row.variant_score - row.baseline_score for row in rows]),
            held_out_samples=sum(row.held_out for row in rows),
        )

    def activate(self, capability_id: str) -> EvaluatedCapabilityPack:
        packs = self.load_packs()
        pack = next(item for item in packs if item.capability_id == capability_id)
        if pack.origin == "imported" and pack.evidence_count == 0:
            raise ValueError("active imported capability requires measured evidence")
        if pack.evidence_count == 0:
            raise ValueError("activation requires measured evidence")
        pack.state = PackState.ACTIVE
        self.save_packs(packs)
        return pack

    def evaluate_retirement(
        self, capability_id: str, executor_id: str
    ) -> tuple[bool, list[str]]:
        packs = self.load_packs()
        pack = next(item for item in packs if item.capability_id == capability_id)
        metrics = self.metrics(capability_id, executor_id)
        criteria = pack.success_criteria
        if metrics.samples < criteria.min_samples:
            return False, ["insufficient_samples"]
        reasons = []
        if metrics.paired_delta < criteria.min_paired_delta:
            reasons.append("no_measurable_added_value")
        if metrics.completion_rate < criteria.min_completion_rate:
            reasons.append("completion_below_threshold")
        if metrics.test_pass_rate < criteria.min_test_pass_rate:
            reasons.append("test_pass_below_threshold")
        if metrics.rollback_rate > criteria.max_rollback_rate:
            reasons.append("rollback_above_threshold")
        if metrics.correction_rate > criteria.max_correction_rate:
            reasons.append("correction_above_threshold")
        if metrics.reviewer_acceptance < criteria.min_reviewer_acceptance:
            reasons.append("reviewer_acceptance_below_threshold")
        if reasons:
            pack.state = PackState.RETIRED
            self.save_packs(packs)
        return bool(reasons), reasons


class EvaluatedPackRouter:
    def __init__(self, store: EvaluatedPackStore, matcher: ExecutorMatcher):
        self.store = store
        self.matcher = matcher

    def route(
        self,
        input_data: CapabilityInput,
        *,
        available_executors: list[str] | None = None,
    ) -> EvaluatedRoute:
        task = input_data.task.lower()
        candidates = []
        for pack in self.store.load_packs():
            if (
                pack.state is not PackState.ACTIVE
                or pack.evidence_count == 0
                or not (pack.role == input_data.role or input_data.role in {"", "auto"})
            ):
                continue
            trigger_hits = sum(
                bool(re.search(rf"\b{re.escape(trigger)}", task))
                for trigger in pack.triggers
            )
            if trigger_hits:
                candidates.append((trigger_hits, pack))
        if not candidates:
            return EvaluatedRoute(
                input_data.role, "", "", "", True, "native_voly_no_capability"
            )
        pack = sorted(candidates, key=lambda item: (-item[0], item[1].capability_id))[0][1]
        match = self.matcher.find_executors(MatchRequest(
            dimension=pack.dimension,
            available_executors=available_executors,
            project_features=input_data.project_features,
            requires_file_tools=True,
        ))
        if match.recommended is None or match.degraded:
            return EvaluatedRoute(
                pack.role, pack.capability_id, "", "", True, "native_voly_match_degraded"
            )
        return EvaluatedRoute(
            pack.role,
            pack.capability_id,
            match.recommended.id,
            match.recommended.model,
            False,
            "evaluated_capability",
        )
