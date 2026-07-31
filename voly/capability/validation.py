"""Production-validation suite and evidence-based activation decisions."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from voly.capability.evaluated_packs import (
    CapabilityInput,
    EvaluatedPackRouter,
    EvaluatedPackStore,
)


class ActivationDecision(str, Enum):
    ACTIVATE = "activate"
    KEEP_PILOT = "keep-pilot"
    RETIRE = "retire"


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    task: str
    role: str
    expected_capability: str
    held_out: bool = False
    project_features: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoutingProbe:
    task_id: str
    expected_capability: str
    routed_capability: str
    native_fallback: bool
    matched: bool
    duration_ms: float


@dataclass(frozen=True)
class SuiteReport:
    schema_version: int
    tasks: int
    held_out_tasks: int
    routing_matches: int
    native_fallbacks: int
    synthetic_outcomes: bool
    activation_allowed: bool
    probes: list[RoutingProbe]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityDecision:
    capability_id: str
    executor_id: str
    decision: ActivationDecision
    reasons: list[str]
    samples: int
    held_out_samples: int
    paired_delta: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


@dataclass(frozen=True)
class ActivationPlan:
    decisions: list[CapabilityDecision]
    local_activation_ready: bool
    cloudflare_deploy_ready: bool
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [item.to_dict() for item in self.decisions],
            "local_activation_ready": self.local_activation_ready,
            "cloudflare_deploy_ready": self.cloudflare_deploy_ready,
            "blockers": self.blockers,
        }


def load_suite(path: str | Path) -> list[BenchmarkTask]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported benchmark suite schema")
    tasks = [BenchmarkTask(**item) for item in data.get("tasks") or []]
    if len(tasks) != 20:
        raise ValueError("production validation suite must contain exactly 20 tasks")
    ids = [item.task_id for item in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("benchmark task IDs must be unique")
    if not any(item.held_out for item in tasks):
        raise ValueError("benchmark suite requires a held-out split")
    return tasks


def probe_routing(
    tasks: list[BenchmarkTask], router: EvaluatedPackRouter
) -> SuiteReport:
    probes = []
    for item in tasks:
        started = time.monotonic()
        route = router.route(CapabilityInput(
            item.task,
            item.role,
            item.project_features,
        ))
        probes.append(RoutingProbe(
            task_id=item.task_id,
            expected_capability=item.expected_capability,
            routed_capability=route.capability_id,
            native_fallback=route.native_fallback,
            matched=(
                route.capability_id == item.expected_capability
                if item.expected_capability
                else route.native_fallback
            ),
            duration_ms=(time.monotonic() - started) * 1000,
        ))
    return SuiteReport(
        schema_version=1,
        tasks=len(tasks),
        held_out_tasks=sum(item.held_out for item in tasks),
        routing_matches=sum(item.matched for item in probes),
        native_fallbacks=sum(item.native_fallback for item in probes),
        synthetic_outcomes=True,
        activation_allowed=False,
        probes=probes,
    )


def decide_capability(
    store: EvaluatedPackStore,
    capability_id: str,
    executor_id: str,
    *,
    required_samples: int,
    required_held_out: int = 2,
    early_retire_samples: int = 3,
) -> CapabilityDecision:
    pack = next(
        item for item in store.load_packs()
        if item.capability_id == capability_id
    )
    metrics = store.metrics(capability_id, executor_id)
    reasons = []
    criteria = pack.success_criteria
    early_no_value = (
        metrics.samples >= early_retire_samples
        and metrics.samples < required_samples
        and metrics.held_out_samples >= required_held_out
        and metrics.paired_delta < criteria.min_paired_delta
    )
    if early_no_value:
        decision = ActivationDecision.RETIRE
        reasons = ["early_falsification_no_measurable_added_value"]
    elif metrics.samples < required_samples:
        reasons.append("insufficient_measured_samples")
    if not early_no_value and metrics.held_out_samples < required_held_out:
        reasons.append("insufficient_held_out_evidence")
    if not early_no_value and reasons:
        decision = ActivationDecision.KEEP_PILOT
    elif not early_no_value:
        failures = []
        if metrics.paired_delta < criteria.min_paired_delta:
            failures.append("no_measurable_added_value")
        if metrics.completion_rate < criteria.min_completion_rate:
            failures.append("completion_below_threshold")
        if metrics.test_pass_rate < criteria.min_test_pass_rate:
            failures.append("test_pass_below_threshold")
        if metrics.rollback_rate > criteria.max_rollback_rate:
            failures.append("rollback_above_threshold")
        if metrics.correction_rate > criteria.max_correction_rate:
            failures.append("correction_above_threshold")
        if metrics.reviewer_acceptance < criteria.min_reviewer_acceptance:
            failures.append("reviewer_acceptance_below_threshold")
        if failures:
            decision = ActivationDecision.RETIRE
            reasons = failures
        else:
            decision = ActivationDecision.ACTIVATE
            reasons = ["measured_value_passed"]
    return CapabilityDecision(
        capability_id,
        executor_id,
        decision,
        reasons,
        metrics.samples,
        metrics.held_out_samples,
        metrics.paired_delta,
    )


def build_activation_plan(decisions: list[CapabilityDecision]) -> ActivationPlan:
    activated = [
        item for item in decisions if item.decision is ActivationDecision.ACTIVATE
    ]
    blockers = []
    if not activated:
        blockers.append("no_capability_passed_local_measured_validation")
    if any(item.decision is ActivationDecision.KEEP_PILOT for item in decisions):
        blockers.append("pilot_evidence_incomplete")
    return ActivationPlan(
        decisions=decisions,
        local_activation_ready=bool(activated),
        cloudflare_deploy_ready=bool(activated) and not blockers,
        blockers=blockers,
    )
