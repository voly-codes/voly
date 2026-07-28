from __future__ import annotations

from pathlib import Path

from voly.config import (
    EvaluationConfig,
    EvidenceConfig,
    RTKConfig,
    VOLYConfig,
)
from voly.evaluation import (
    evaluate_run,
    is_test_artifact,
    scan_changed_security,
    select_policy,
    validate_markdown_links,
    validate_test_artifacts,
)
from voly.evidence import BaselineCheck, EvidenceStore, RepositoryBaseline
from voly.executor.base import ExecutorResult


def _baseline(*checks: BaselineCheck) -> RepositoryBaseline:
    return RepositoryBaseline(
        captured_at="2026-07-28T00:00:00Z",
        health="healthy" if checks else "metadata_only",
        checks=list(checks),
    )


def test_policy_selection_is_deterministic() -> None:
    docs_policy = select_policy("docs")
    assert docs_policy.id == "documentation-basic"
    assert docs_policy.version == "2"
    testing_policy = select_policy("tests")
    assert testing_policy.id == "testing-basic"
    assert testing_policy.version == "2"
    security_policy = select_policy("security")
    assert security_policy.id == "security-basic"
    assert security_policy.version == "1"
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


def test_markdown_links_validate_relative_targets_and_ignore_fences(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text("# Target\n", encoding="utf-8")
    guide = docs / "guide.md"
    guide.write_text(
        "```\n[example](missing-example.md)\n```\n"
        "[target](target.md)\n[reference][target-ref]\n"
        "[target-ref]: target.md\n[web](https://example.com)\n",
        encoding="utf-8",
    )

    ok, message, detail = validate_markdown_links(
        str(tmp_path),
        ["docs/guide.md"],
    )

    assert ok is True
    assert "2 local link(s) valid" in message
    assert detail["broken"] == []


def test_markdown_links_fail_for_missing_or_outside_root(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "[missing](missing.md)\n[outside](../../outside.md)\n",
        encoding="utf-8",
    )

    ok, _message, detail = validate_markdown_links(
        str(tmp_path),
        ["docs/guide.md"],
    )

    assert ok is False
    assert {item["reason"] for item in detail["broken"]} == {
        "missing",
        "outside_root",
    }


def test_test_artifact_detection_uses_common_conventions() -> None:
    assert is_test_artifact("tests/test_auth.py")
    assert is_test_artifact("src/auth_test.py")
    assert is_test_artifact("web/auth.spec.ts")
    assert is_test_artifact("jest.config.js")
    assert not is_test_artifact("src/auth.py")

    ok, message, detail = validate_test_artifacts(
        ["src/auth.py", "tests/test_auth.py"]
    )
    assert ok is True
    assert message == "1 test artifact(s) changed"
    assert detail["test_artifacts"] == ["tests/test_auth.py"]


def test_test_artifact_validation_fails_without_tests() -> None:
    ok, message, detail = validate_test_artifacts(["src/auth.py"])
    assert ok is False
    assert message == "testing task changed no recognized test artifacts"
    assert detail["test_artifacts"] == []


def test_changed_security_scan_is_diff_scoped_and_redacts_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "auth.py"
    source.write_text('password = "supersecret123"\n', encoding="utf-8")
    (tmp_path / "legacy.py").write_text("eval(user_input)\n", encoding="utf-8")

    status, message, detail = scan_changed_security(
        str(tmp_path),
        ["auth.py"],
    )

    assert status == "failed"
    assert message == "1 security finding(s) in changed files"
    assert detail["findings"] == [
        {
            "label": "hardcoded_secret",
            "path": "auth.py",
            "description": "Possible hardcoded secret",
        }
    ]
    assert "supersecret123" not in repr(detail)
    assert all(item["path"] != "legacy.py" for item in detail["findings"])


def test_changed_security_scan_passes_clean_source_and_rejects_outside_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "safe.py").write_text("answer = 42\n", encoding="utf-8")
    status, _message, detail = scan_changed_security(str(tmp_path), ["safe.py"])
    assert status == "passed"
    assert detail["scanned_files"] == ["safe.py"]

    status, _message, detail = scan_changed_security(
        str(tmp_path),
        ["../outside.py"],
    )
    assert status == "failed"
    assert detail["findings"][0]["label"] == "outside_repository"


def test_changed_security_scan_is_partial_without_supported_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Safe\n", encoding="utf-8")
    status, message, detail = scan_changed_security(
        str(tmp_path),
        ["README.md"],
    )
    assert status == "skipped"
    assert message == "no supported changed source files to scan"
    assert detail["scanned_files"] == []


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


def test_testing_policy_requires_changed_test_artifact(tmp_path: Path) -> None:
    report = evaluate_run(
        select_policy("testing"),
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
        files_touched=["src/module.py"],
    )

    assert report.state == "soft_failure"
    assert report.checks[-1].id == "test_artifacts"
    assert report.checks[-1].status == "failed"


def test_security_policy_scans_diff_and_waits_for_human_review(
    tmp_path: Path,
) -> None:
    source = tmp_path / "auth.py"
    source.write_text("answer = 42\n", encoding="utf-8")
    report = evaluate_run(
        select_policy("security"),
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
        files_touched=["auth.py"],
    )

    assert report.state == "partial_success"
    assert report.checks[-2].id == "security_scan"
    assert report.checks[-2].status == "passed"
    assert report.checks[-1].id == "human_review"
    assert report.checks[-1].status == "pending"


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


class _DocumentationExecutor:
    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kwargs):
        Path(cwd, "guide.md").write_text(
            "[reference](reference.md)\n",
            encoding="utf-8",
        )
        return ExecutorResult(success=True, output="documented", duration_ms=5)


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


def test_documentation_policy_waits_for_and_applies_human_feedback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from voly.runner import agent_runner as runner_mod

    (tmp_path / "reference.md").write_text("# Reference\n", encoding="utf-8")
    store_dir = tmp_path / "evidence"
    config = VOLYConfig(
        rtk=RTKConfig(enabled=False),
        evidence=EvidenceConfig(
            enabled=True,
            store_dir=str(store_dir),
            baseline_auto_commands=False,
            baseline_commands={
                "links": 'python -c "raise SystemExit(0)"',
            },
        ),
        evaluation=EvaluationConfig(enabled=True),
    )
    monkeypatch.setattr(
        runner_mod,
        "_build_executor",
        lambda name, model=None: _DocumentationExecutor(),
    )

    result = runner_mod.AgentRunner(config).run(
        "document the guide",
        "zen",
        cwd=str(tmp_path),
        emit_event=False,
        collect_evidence=False,
    )
    store = EvidenceStore(store_dir)
    record = store.load(result.task_id)
    assert record is not None and record.evaluation is not None
    assert record.execution.eval_policy_id == "documentation-basic"
    assert record.evaluation.state == "partial_success", [
        (check.id, check.status, check.message, check.detail)
        for check in record.evaluation.checks
    ]
    assert record.evaluation.checks[-1].status == "pending"

    accepted = store.add_human_feedback(result.task_id, "accepted")
    assert accepted.evaluation is not None
    assert accepted.evaluation.state == "verified_success"
    assert accepted.outcome.state == "verified_success"

    reverted = store.add_human_feedback(result.task_id, "reverted")
    assert reverted.evaluation is not None
    assert reverted.evaluation.state == "soft_failure"
    assert reverted.outcome.state == "soft_failure"
