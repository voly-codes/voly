from __future__ import annotations

from pathlib import Path

from voly.config import (
    EvaluationConfig,
    EvidenceConfig,
    RTKConfig,
    VOLYConfig,
)
from voly.evaluation import evaluate_run, select_policy
from voly.evidence import BaselineCheck, EvidenceStore, RepositoryBaseline
from voly.executor.base import ExecutorResult


def _baseline(*checks: BaselineCheck) -> RepositoryBaseline:
    return RepositoryBaseline(
        captured_at="2026-07-28T00:00:00Z",
        health="healthy" if checks else "metadata_only",
        checks=list(checks),
    )


def test_policy_selection_is_deterministic() -> None:
    assert select_policy("docs").id == "documentation-basic"
    assert select_policy("tests").id == "testing-basic"
    assert select_policy("backend").id == "executor-basic"
    assert select_policy(None).id == "executor-basic"


def test_evaluation_config_parser() -> None:
    from voly.config._parser import _parse_config

    config = _parse_config(
        {
            "evaluation": {
                "enabled": True,
                "policy_id": "testing-basic",
                "command_timeout_seconds": 42,
            }
        }
    )

    assert config.evaluation.enabled is True
    assert config.evaluation.policy_id == "testing-basic"
    assert config.evaluation.command_timeout_seconds == 42


def test_eval_verified_success_replays_exact_baseline_command(tmp_path: Path) -> None:
    report = evaluate_run(
        select_policy("backend"),
        result=ExecutorResult(success=True, output="done"),
        baseline=_baseline(
            BaselineCheck(
                name="tests",
                command='python -c "raise SystemExit(0)"',
                status="passed",
                argv=["python", "-c", "raise SystemExit(0)"],
            )
        ),
        cwd=str(tmp_path),
        git_before={},
        git_after={},
        files_touched=["module.py"],
    )

    assert report.state == "verified_success"
    assert [check.status for check in report.checks] == [
        "passed",
        "passed",
        "passed",
        "passed",
    ]


def test_eval_is_partial_without_deterministic_post_check(tmp_path: Path) -> None:
    report = evaluate_run(
        select_policy("backend"),
        result=ExecutorResult(success=True, output="done"),
        baseline=_baseline(),
        cwd=str(tmp_path),
        git_before={},
        git_after={},
        files_touched=["module.py"],
    )

    assert report.state == "partial_success"
    assert report.checks[-1].status == "skipped"


def test_eval_soft_failure_when_post_check_regresses(tmp_path: Path) -> None:
    report = evaluate_run(
        select_policy("backend"),
        result=ExecutorResult(success=True, output="done"),
        baseline=_baseline(
            BaselineCheck(
                name="tests",
                command='python -c "raise SystemExit(1)"',
                status="passed",
                argv=["python", "-c", "raise SystemExit(1)"],
            )
        ),
        cwd=str(tmp_path),
        git_before={},
        git_after={},
        files_touched=["module.py"],
    )

    assert report.state == "soft_failure"
    assert report.checks[-1].status == "failed"
    assert report.checks[-1].detail["returncode"] == 1


def test_eval_stops_without_spending_more_checks_after_executor_failure(
    tmp_path: Path,
) -> None:
    report = evaluate_run(
        select_policy("backend"),
        result=ExecutorResult(success=False, error="failed"),
        baseline=_baseline(),
        cwd=str(tmp_path),
        git_before={},
        git_after={},
        files_touched=[],
    )

    assert report.state == "soft_failure"
    assert len(report.checks) == 1
    assert report.checks[0].id == "executor"


class _WritingExecutor:
    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kwargs):
        Path(cwd, "generated.txt").write_text("verified\n", encoding="utf-8")
        return ExecutorResult(success=True, output="done", duration_ms=5)


def test_agent_runner_attaches_eval_report_to_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from voly.runner import agent_runner as runner_mod

    store_dir = tmp_path / "evidence"
    config = VOLYConfig(
        rtk=RTKConfig(enabled=False),
        evidence=EvidenceConfig(
            enabled=True,
            store_dir=str(store_dir),
            baseline_auto_commands=False,
            baseline_commands={
                "tests": 'python -c "raise SystemExit(0)"',
            },
        ),
        evaluation=EvaluationConfig(enabled=True),
    )
    monkeypatch.setattr(
        runner_mod,
        "_build_executor",
        lambda name, model=None: _WritingExecutor(),
    )

    result = runner_mod.AgentRunner(config).run(
        "implement backend helper",
        "zen",
        cwd=str(tmp_path),
        emit_event=False,
        collect_evidence=False,
    )

    record = EvidenceStore(store_dir).load(result.task_id)
    assert record is not None
    assert record.evaluation is not None
    assert record.evaluation.state == "verified_success"
    assert record.outcome.state == "verified_success"
    assert record.execution.eval_policy_id == "executor-basic"
    assert result.result.metadata["eval_state"] == "verified_success"
