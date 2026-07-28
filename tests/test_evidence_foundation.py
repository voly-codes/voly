from __future__ import annotations

import json
from datetime import datetime, timezone

from voly.config import EvidenceConfig, RTKConfig, VOLYConfig
from voly.evidence import (
    BaselineCheck,
    EvidenceOutcome,
    EvidenceRecord,
    EvidenceStore,
    ExecutionBundle,
    HumanFeedback,
    RepositoryBaseline,
    capture_repository_baseline,
    classify_root_cause,
    evidence_to_cloud_record,
)
from voly.executor.base import ExecutorResult


def _baseline(health: str = "healthy") -> RepositoryBaseline:
    return RepositoryBaseline(
        captured_at=datetime.now(timezone.utc).isoformat(),
        health=health,
        stack=["python"],
    )


def _record(task_id: str = "run-1") -> EvidenceRecord:
    return EvidenceRecord(
        task_id=task_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        task_type="backend",
        task_fingerprint="abc",
        baseline=_baseline(),
        execution=ExecutionBundle(
            agent="developer",
            executor="zen",
            runtime_version="0.1.0",
        ),
        outcome=EvidenceOutcome(success=True, state="execution_success"),
    )


def test_baseline_metadata_only_when_commands_are_disabled(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    baseline = capture_repository_baseline(
        str(tmp_path),
        auto_commands=False,
        commands={},
    )

    assert baseline.health == "metadata_only"
    assert baseline.checks == []
    assert "python" in [item.lower() for item in baseline.stack]


def test_baseline_distinguishes_preexisting_failure(monkeypatch, tmp_path) -> None:
    from voly.evidence import baseline as baseline_mod

    monkeypatch.setattr(
        baseline_mod,
        "_configured_commands",
        lambda raw: [baseline_mod._Command("tests", ["python", "-c", "raise SystemExit(3)"])],
    )

    baseline = capture_repository_baseline(
        str(tmp_path),
        auto_commands=False,
        commands={"tests": "ignored"},
    )

    assert baseline.health == "preexisting_failure"
    assert baseline.checks[0].status == "failed"
    assert baseline.checks[0].exit_code == 3


def test_root_cause_does_not_blame_agent_for_baseline_or_provider() -> None:
    repository = classify_root_cause(
        success=False,
        error_class="unrecognized",
        baseline=_baseline("preexisting_failure"),
    )
    provider = classify_root_cause(
        success=False,
        error_class="billing",
        baseline=_baseline(),
    )
    agent = classify_root_cause(
        success=False,
        error_class="unrecognized",
        baseline=_baseline(),
    )

    assert (repository.failure_class, repository.penalize_agent) == (
        "repository_failure",
        False,
    )
    assert (provider.failure_class, provider.penalize_agent) == (
        "provider_failure",
        False,
    )
    assert (agent.failure_class, agent.penalize_agent) == ("agent_failure", True)


def test_evidence_store_roundtrip_and_feedback(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence")
    path = store.save(_record())

    assert path.is_file()
    loaded = store.load("run-1")
    assert loaded is not None
    assert loaded.execution.runtime_version == "0.1.0"

    updated = store.add_human_feedback(
        "run-1",
        "accepted",
        comment="merged unchanged",
    )
    assert updated.human_feedback[0].kind == "accepted"
    assert store.load("run-1").human_feedback[0].comment == "merged unchanged"


class _FakeExecutor:
    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kwargs):
        return ExecutorResult(success=False, error="agent failed", duration_ms=5)


def test_agent_runner_writes_versioned_evidence(monkeypatch, tmp_path) -> None:
    from voly.runner import agent_runner as runner_mod

    store_dir = tmp_path / "evidence"
    config = VOLYConfig(
        rtk=RTKConfig(enabled=False),
        evidence=EvidenceConfig(
            enabled=True,
            store_dir=str(store_dir),
            baseline_auto_commands=False,
        ),
    )
    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: _FakeExecutor())

    result = runner_mod.AgentRunner(config).run(
        "fix backend",
        "zen",
        cwd=str(tmp_path),
        emit_event=False,
        collect_evidence=False,
    )

    record = EvidenceStore(store_dir).load(result.task_id)
    assert record is not None
    assert record.schema_version == 1
    assert record.task_fingerprint != "fix backend"
    assert record.execution.executor == "zen"
    assert record.outcome.failure_class == "agent_failure"
    assert result.result.metadata["evidence_record"].endswith(f"{result.task_id}.json")


def test_capability_skips_non_agent_failure() -> None:
    from voly.capability.evidence import RunRecord, _compute_run_score

    assert _compute_run_score(
        RunRecord(
            executor_id="zen",
            dimension="backend",
            success=False,
            failure_class="environment_failure",
            penalize_agent=False,
        )
    ) is None


def test_evidence_config_parser() -> None:
    from voly.config._parser import _parse_config

    config = _parse_config(
        {
            "evidence": {
                "enabled": True,
                "store_dir": "facts",
                "baseline_auto_commands": False,
                "baseline_commands": {"tests": "pytest tests/unit -q"},
                "eval_policy_version": 2,
            }
        }
    )

    assert config.evidence.enabled is True
    assert config.evidence.store_dir == "facts"
    assert config.evidence.baseline_auto_commands is False
    assert config.evidence.baseline_commands == {"tests": "pytest tests/unit -q"}
    assert config.evidence.eval_policy_version == "2"


def test_cloud_evidence_record_excludes_raw_observations() -> None:
    record = _record()
    record.baseline.notes = ["private repository note"]
    record.baseline.checks = [
        BaselineCheck(
            name="tests",
            command="pytest secret/customer/path",
            status="failed",
            output_excerpt="API_KEY=private",
        )
    ]
    record.execution.skills = [
        {"id": "pytest", "version": "1", "source_path": "private/skill.md"}
    ]
    record.human_feedback = [
        HumanFeedback(
            kind="edited",
            recorded_at="2026-07-28T00:00:00Z",
            comment="customer-specific correction",
        )
    ]

    cloud = evidence_to_cloud_record(record)
    serialized = json.dumps(cloud)

    assert cloud["evidence_id"] != record.task_id
    assert cloud["schema_version"] == 1
    assert cloud["source_schema_version"] == record.schema_version
    assert set(cloud) == {
        "schema_version",
        "source_schema_version",
        "evidence_id",
        "created_at",
        "task_type",
        "baseline",
        "execution",
        "outcome",
        "human_feedback",
    }
    assert "task_fingerprint" not in cloud
    assert "pytest secret/customer/path" not in serialized
    assert "API_KEY=private" not in serialized
    assert "private repository note" not in serialized
    assert "private/skill.md" not in serialized
    assert "customer-specific correction" not in serialized
