from __future__ import annotations

import json
from dataclasses import replace
from importlib.resources import files
from types import SimpleNamespace

import pytest

from voly.capability import (
    ActivationDecision,
    CapabilityRunEvidence,
    EvaluatedPackStore,
    build_activation_plan,
    decide_capability,
    load_suite,
    probe_routing,
    render_variant_task,
)
from voly.capability.pack_store import PackStore, PackStoreError


def _record(
    capability_id: str,
    run: int,
    *,
    good: bool,
    held_out: bool,
) -> CapabilityRunEvidence:
    return CapabilityRunEvidence(
        capability_id=capability_id,
        executor_id="claude-code",
        run_id=f"{capability_id}-{run}",
        completion=good,
        tests_passed=good,
        rollback=not good,
        corrections=0 if good else 1,
        cost_usd=0.01,
        latency_ms=500,
        retries=0 if good else 1,
        reviewer_accepted=good,
        baseline_score=0.5,
        variant_score=0.75 if good else 0.4,
        held_out=held_out,
        experiment_id=f"pair-{run}",
        changed_capabilities=[capability_id],
        baseline_latency_ms=600,
        baseline_tokens=1000,
        variant_tokens=900 if good else 1200,
    )


def test_bundled_suite_has_20_unique_tasks_and_held_out_split():
    path = files("voly.capability").joinpath("benchmark_suite_v1.json")
    tasks = load_suite(str(path))

    assert len(tasks) == 20
    assert len({task.task_id for task in tasks}) == 20
    assert sum(task.held_out for task in tasks) == 7
    assert {task.expected_capability for task in tasks} == {
        "", "security-reviewer", "tdd-workflow", "python-reviewer"
    }


def test_offline_probe_can_never_allow_activation():
    tasks = load_suite(str(
        files("voly.capability").joinpath("benchmark_suite_v1.json")
    ))

    class Router:
        def route(self, item):
            expected = next(task.expected_capability for task in tasks if task.task == item.task)
            return SimpleNamespace(
                capability_id=expected,
                native_fallback=not expected,
            )

    report = probe_routing(tasks, Router())

    assert report.routing_matches == 20
    assert report.synthetic_outcomes is True
    assert report.activation_allowed is False


def test_no_real_evidence_keeps_pilot_and_blocks_cf(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    packs = store.initialize()
    decisions = [
        decide_capability(store, pack.capability_id, "claude-code", required_samples=6)
        for pack in packs
    ]
    plan = build_activation_plan(decisions)

    assert all(item.decision is ActivationDecision.KEEP_PILOT for item in decisions)
    assert plan.local_activation_ready is False
    assert plan.cloudflare_deploy_ready is False
    assert "no_capability_passed_local_measured_validation" in plan.blockers


def test_six_good_pairs_with_two_held_out_allow_activation(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    for run in range(6):
        store.record(_record(
            "security-reviewer", run, good=True, held_out=run >= 4
        ))

    decision = decide_capability(
        store, "security-reviewer", "claude-code", required_samples=6
    )

    assert decision.decision is ActivationDecision.ACTIVATE
    assert decision.held_out_samples == 2
    assert decision.paired_delta > 0


def test_unmeasured_cost_is_not_reported_as_zero_cost_evidence(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    evidence = _record("security-reviewer", 1, good=True, held_out=False)
    store.record(replace(evidence, cost_usd=0, cost_measured=False))

    metrics = store.metrics("security-reviewer", "claude-code")

    assert metrics.cost_samples == 0
    assert metrics.avg_cost_usd == 0


def test_unmeasured_tokens_are_not_reported_as_zero_token_evidence(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    evidence = _record("tdd-workflow", 1, good=True, held_out=False)
    store.record(replace(
        evidence,
        baseline_tokens=1000,
        variant_tokens=0,
        tokens_measured=False,
    ))

    metrics = store.metrics("tdd-workflow", "claude-code")

    assert metrics.token_samples == 0
    assert metrics.avg_token_delta == 0


def test_negative_measured_value_retires_after_complete_sample(tmp_path):
    store = EvaluatedPackStore(tmp_path)
    store.initialize()
    for run in range(6):
        store.record(_record(
            "tdd-workflow", run, good=False, held_out=run >= 4
        ))

    decision = decide_capability(
        store, "tdd-workflow", "claude-code", required_samples=6
    )

    assert decision.decision is ActivationDecision.RETIRE
    assert "no_measurable_added_value" in decision.reasons


def test_cf_ready_only_when_all_decisions_resolved_and_one_activates():
    activate = SimpleNamespace(decision=ActivationDecision.ACTIVATE)
    retire = SimpleNamespace(decision=ActivationDecision.RETIRE)
    keep = SimpleNamespace(decision=ActivationDecision.KEEP_PILOT)

    ready = build_activation_plan([activate, retire])
    blocked = build_activation_plan([activate, keep])

    assert ready.cloudflare_deploy_ready is True
    assert blocked.cloudflare_deploy_ready is False
    assert "pilot_evidence_incomplete" in blocked.blockers


def _ecc_instruction_fixture(root):
    content = {
        "agents/security-reviewer.md": "---\nname: security-reviewer\n---\nCheck auth boundaries.\n",
        "agents/python-reviewer.md": "---\nname: python-reviewer\n---\nCheck typing and Ruff.\n",
        "skills/security-review/SKILL.md": "---\nname: security-review\n---\nReview secrets.\n",
        "skills/tdd-workflow/SKILL.md": "---\nname: tdd-workflow\n---\nUse RED GREEN REFACTOR.\n",
        "package.json": json.dumps({
            "name": "ecc-universal", "version": "1.0.0", "license": "MIT"
        }),
    }
    for relative, text in content.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_variant_uses_only_verified_admitted_staged_instructions(tmp_path):
    packs_root = tmp_path / "packs"
    PackStore(packs_root).install_ecc(_ecc_instruction_fixture(tmp_path / "ecc"))
    evaluated = EvaluatedPackStore(tmp_path / "evaluated")
    pack = next(
        item for item in evaluated.initialize()
        if item.capability_id == "security-reviewer"
    )

    variant = render_variant_task(
        pack,
        SimpleNamespace(task="Review auth", role="security"),
        packs_root=packs_root,
    )

    assert variant.task.startswith("Review auth")
    assert "Check auth boundaries" in variant.task
    assert "Review secrets" in variant.task
    assert len(variant.instruction_hashes) == 2

    source = packs_root / "ecc-universal/content/agents/security-reviewer.md"
    source.write_text("tampered", encoding="utf-8")
    with pytest.raises(PackStoreError, match="verification failed"):
        render_variant_task(
            pack,
            SimpleNamespace(task="Review auth", role="security"),
            packs_root=packs_root,
        )
