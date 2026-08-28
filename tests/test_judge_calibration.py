from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from voly.cli.commands.eval_cmd import eval_cmd
from voly.evaluation.calibration import (
    build_calibration_report,
    save_calibration_report,
)


def _record(
    task_id: str,
    *,
    judge: str,
    human: str | None,
    model: str = "judge-v1",
    events: list[dict] | None = None,
) -> dict:
    calibration_events = events
    if calibration_events is None and human is not None:
        calibration_events = [
            {
                "human_label": human,
                "judge_label": judge,
                "agreement": human == judge,
                "feedback_kind": "accepted" if human == "pass" else "reverted",
            }
        ]
    return {
        "schema_version": 2,
        "task_id": task_id,
        "created_at": "2026-07-28T00:00:00Z",
        "task_type": "backend",
        "task_fingerprint": "a" * 64,
        "baseline": {"captured_at": "", "health": "healthy"},
        "execution": {
            "agent": "agent",
            "executor": "executor",
            "model": "worker",
            "provider": "local",
            "eval_policy_id": "executor-basic",
            "eval_policy_version": "2-judge-shadow.1",
        },
        "outcome": {"success": True, "state": "verified_success"},
        "evaluation": {
            "policy_id": "executor-basic",
            "policy_version": "2-judge-shadow.1",
            "state": "verified_success",
            "started_at": "",
            "completed_at": "",
            "checks": [
                {
                    "id": "llm-judge",
                    "evaluator": "llm_judge",
                    "status": "passed" if judge == "pass" else "failed",
                    "required": False,
                    "detail": {
                        "rubric_id": "general-code@1",
                        "model": model,
                        "provider": "test",
                        "threshold": 0.75,
                        "calibration_events": calibration_events or [],
                    },
                }
            ],
        },
    }


def _write(root: Path, name: str, payload: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_calibration_builds_confusion_matrix_and_rates(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    _write(evidence, "tp", _record("tp", judge="pass", human="pass"))
    _write(evidence, "tn", _record("tn", judge="fail", human="fail"))
    _write(evidence, "fp", _record("fp", judge="pass", human="fail"))
    _write(evidence, "fn", _record("fn", judge="fail", human="pass"))

    report = build_calibration_report(evidence, min_samples=4)

    assert report["summary"]["labeled_decisions"] == 4
    group = report["groups"][0]
    assert group["sample_status"] == "sufficient"
    assert group["confusion_matrix"] == {
        "true_pass": 1,
        "true_fail": 1,
        "false_pass": 1,
        "false_fail": 1,
    }
    assert group["metrics"]["agreement_rate"] == 0.5
    assert group["metrics"]["false_pass_rate"] == 0.5
    assert len(group["disagreements"]) == 2
    assert report["policy"]["automatic_threshold_changes"] is False


def test_calibration_uses_latest_feedback_and_separates_lineages(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    events = [
        {
            "human_label": "fail",
            "judge_label": "pass",
            "feedback_kind": "edited",
        },
        {
            "human_label": "pass",
            "judge_label": "pass",
            "feedback_kind": "accepted",
        },
    ]
    _write(
        evidence,
        "latest",
        _record("latest", judge="pass", human=None, events=events),
    )
    _write(
        evidence,
        "other-model",
        _record("other-model", judge="pass", human="pass", model="judge-v2"),
    )

    report = build_calibration_report(evidence)

    assert report["summary"]["lineages"] == 2
    assert all(group["sample_status"] == "informational" for group in report["groups"])
    assert all(group["metrics"]["agreement_rate"] == 1.0 for group in report["groups"])


def test_calibration_counts_unlabeled_and_invalid_records(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    _write(evidence, "unlabeled", _record("unlabeled", judge="pass", human=None))
    (evidence / "broken.json").write_text("{", encoding="utf-8")

    report = build_calibration_report(evidence)

    assert report["source"]["records_scanned"] == 2
    assert report["source"]["invalid"] == 1
    assert report["summary"]["judge_decisions"] == 1
    assert report["summary"]["unlabeled_decisions"] == 1
    assert report["groups"] == []


def test_calibration_report_save_and_cli(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    _write(evidence, "one", _record("one", judge="pass", human="pass"))
    output = tmp_path / "calibration.json"

    direct = save_calibration_report(
        build_calibration_report(evidence, min_samples=1),
        output,
    )
    assert json.loads(direct.read_text(encoding="utf-8"))["summary"]["lineages"] == 1

    cli_output = tmp_path / "cli.json"
    result = CliRunner().invoke(
        eval_cmd,
        [
            "calibrate",
            "--evidence-dir",
            str(evidence),
            "--min-samples",
            "1",
            "--output",
            str(cli_output),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["labeled_decisions"] == 1
    assert cli_output.exists()


def test_calibration_reports_business_decisions_without_tuning(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    plans = tmp_path / "plans"
    _write(evidence, "one", _record("one", judge="pass", human="pass"))
    _write(plans, "approved", {
        "metadata": {
            "kind": "business_decision",
            "decision": "approved",
            "execution": "completed",
            "urgency": "high",
        }
    })
    _write(plans, "rejected", {
        "metadata": {
            "kind": "business_decision",
            "decision": "rejected",
            "execution": "pending",
            "urgency": "high",
        }
    })
    _write(plans, "unrelated", {"metadata": {"kind": "coding_plan"}})

    report = build_calibration_report(evidence, min_samples=1, plans_dir=plans)

    assert report["business_decisions"] == {
        "records_scanned": 2,
        "invalid": 0,
        "counts": {"pending": 0, "approved": 1, "rejected": 1},
        "execution": {"pending": 1, "running": 0, "completed": 1, "failed": 0},
        "approval_rate": 0.5,
        "by_urgency": {"high": {"total": 2, "approved": 1, "rejected": 1}},
    }
    assert report["policy"]["automatic_threshold_changes"] is False


def test_calibration_cli_accepts_business_plans_dir(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    plans = tmp_path / "plans"
    _write(evidence, "one", _record("one", judge="pass", human="pass"))
    _write(plans, "pending", {
        "metadata": {
            "kind": "business_decision",
            "decision": "pending",
            "execution": "pending",
        }
    })
    output = tmp_path / "calibration.json"

    result = CliRunner().invoke(eval_cmd, [
        "calibrate", "--evidence-dir", str(evidence), "--plans-dir", str(plans),
        "--min-samples", "1", "--output", str(output),
    ])

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["business_decisions"]["records_scanned"] == 1
