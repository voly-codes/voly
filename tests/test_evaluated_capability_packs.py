from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from voly.capability import (
    CapabilityInput,
    CapabilityOutput,
    CapabilityRunEvidence,
    EvaluatedPackRouter,
    EvaluatedPackStore,
    PackState,
)


def _evidence(
    capability_id: str = "security-reviewer",
    executor_id: str = "claude-code",
    *,
    good: bool = True,
    run_id: str = "run-1",
    held_out: bool = False,
) -> CapabilityRunEvidence:
    return CapabilityRunEvidence(
        capability_id=capability_id,
        executor_id=executor_id,
        run_id=run_id,
        completion=good,
        tests_passed=good,
        rollback=not good,
        corrections=0 if good else 1,
        cost_usd=0.02,
        latency_ms=1200,
        retries=0 if good else 2,
        reviewer_accepted=good,
        baseline_score=0.5,
        variant_score=0.8 if good else 0.4,
        held_out=held_out,
    )


class _Matcher:
    def __init__(self, degraded: bool = False):
        self.degraded = degraded
        self.requests = []

    def find_executors(self, request):
        self.requests.append(request)
        profile = SimpleNamespace(id="claude-code", model="claude-sonnet")
        return SimpleNamespace(
            recommended=None if self.degraded else profile,
            degraded=self.degraded,
        )


def test_three_pilot_packs_have_typed_contracts(tmp_path):
    packs = EvaluatedPackStore(tmp_path).initialize()

    assert {pack.capability_id for pack in packs} == {
        "security-reviewer", "tdd-workflow", "python-reviewer"
    }
    assert all(pack.input_contract == "CapabilityInput.v1" for pack in packs)
    assert all(pack.output_contract == "CapabilityOutput.v1" for pack in packs)
    assert CapabilityOutput("x", True).completion is True


def test_activation_requires_measured_evidence(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()

    with pytest.raises(ValueError, match="measured evidence"):
        store.activate("security-reviewer")

    store.record(_evidence())
    assert store.activate("security-reviewer").state is PackState.ACTIVE


def test_metrics_track_all_required_outcomes(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    store.record(_evidence(run_id="good", held_out=True))
    store.record(_evidence(good=False, run_id="bad"))

    metrics = store.metrics("security-reviewer", "claude-code")

    assert metrics.samples == 2
    assert metrics.completion_rate == 0.5
    assert metrics.test_pass_rate == 0.5
    assert metrics.rollback_rate == 0.5
    assert metrics.correction_rate == 0.5
    assert metrics.avg_cost_usd == 0.02
    assert metrics.avg_latency_ms == 1200
    assert metrics.avg_retries == 1
    assert metrics.reviewer_acceptance == 0.5
    assert metrics.held_out_samples == 1
    assert metrics.cost_samples == 2
    assert metrics.token_samples == 2


def test_full_routing_chain_uses_existing_executor_matcher(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    store.record(_evidence())
    store.activate("security-reviewer")
    matcher = _Matcher()

    route = EvaluatedPackRouter(store, matcher).route(
        CapabilityInput("perform security threat review", "security", ["python"])
    )

    assert route.role == "security"
    assert route.capability_id == "security-reviewer"
    assert route.executor == "claude-code"
    assert route.model == "claude-sonnet"
    assert route.native_fallback is False
    assert matcher.requests[0].dimension == "security"


def test_native_fallback_when_no_active_capability_or_match_degrades(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    no_active = EvaluatedPackRouter(store, _Matcher()).route(
        CapabilityInput("security review", "security")
    )
    assert no_active.native_fallback is True
    assert no_active.reason == "native_voly_no_capability"

    store.record(_evidence())
    store.activate("security-reviewer")
    degraded = EvaluatedPackRouter(store, _Matcher(degraded=True)).route(
        CapabilityInput("security review", "security")
    )
    assert degraded.native_fallback is True
    assert degraded.reason == "native_voly_match_degraded"


def test_retirement_when_paired_variant_has_no_added_value(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    for index in range(3):
        store.record(_evidence(
            good=False,
            run_id=f"bad-{index}",
            held_out=index >= 1,
        ))

    retired, reasons = store.evaluate_retirement(
        "security-reviewer", "claude-code"
    )

    assert retired is True
    assert "no_measurable_added_value" in reasons
    pack = next(
        item for item in store.load_packs()
        if item.capability_id == "security-reviewer"
    )
    assert pack.state is PackState.RETIRED


def test_retirement_requires_held_out_evidence(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    for index in range(3):
        store.record(_evidence(good=False, run_id=f"bad-{index}"))

    retired, reasons = store.evaluate_retirement(
        "security-reviewer", "claude-code"
    )

    assert retired is False
    assert reasons == ["insufficient_held_out_evidence"]


def test_imported_capability_cannot_be_active_without_evidence(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    packs = store.initialize()
    packs[0].origin = "imported"
    store.save_packs(packs)

    with pytest.raises(ValueError, match="imported capability"):
        store.activate("security-reviewer")


def test_held_out_paired_delta_is_positive_for_good_variant(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    store.record(_evidence(held_out=True))

    metrics = store.metrics("security-reviewer", "claude-code")

    assert metrics.paired_delta == pytest.approx(0.3)
    assert metrics.held_out_samples == 1


def test_paired_experiment_rejects_multiple_capability_changes(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    evidence = replace(
        _evidence(),
        changed_capabilities=["security-reviewer", "tdd-workflow"],
    )

    with pytest.raises(ValueError, match="exactly one capability"):
        store.record(evidence)
