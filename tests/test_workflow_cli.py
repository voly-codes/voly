from __future__ import annotations

import json
from importlib import import_module

from click.testing import CliRunner

from voly.cli.commands.workflow_cmd import workflow_cmd
from voly.config import TelemetryConfig, VOLYConfig
from voly.runtime.runs import RunTracker
from voly.workflow import ReviewLoopResult, ReviewStopReason


def test_review_until_clean_cli_json(tmp_path, monkeypatch) -> None:
    module = import_module("voly.cli.commands.workflow_cmd")
    monkeypatch.setattr(
        module,
        "_execute_review",
        lambda *args, **kwargs: ReviewLoopResult(
            True, ReviewStopReason.CLEAN, workflow_id="wf-1",
        ),
    )

    result = CliRunner().invoke(
        workflow_cmd,
        [
            "review-until-clean", "fix app", "--cwd", str(tmp_path),
            "--max-rounds", "2", "--json",
        ],
        obj={"config": VOLYConfig()},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["workflow"] == "review-until-clean"
    assert payload["task_id"] == "wf-1"
    assert payload["stop_reason"] == "clean"


def test_workflow_stats_reports_guarded_rollout_metrics(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    tracker = RunTracker(str(runs_dir))
    tracker.start("wf-clean", "fix", ["developer", "reviewer"])
    tracker.workflow_update(
        "wf-clean", workflow="review-until-clean", stop_reason="clean",
        metrics={
            "laps": 2, "verified_completion": True, "manual_interventions": 0,
            "cost_usd": 0.3, "duration_ms": 1200, "stop_reason": "clean",
        },
    )
    tracker.finish("wf-clean")
    tracker.start("wf-stop", "fix", ["developer", "reviewer"])
    tracker.workflow_update(
        "wf-stop", workflow="review-until-clean", stop_reason="max_rounds",
        metrics={
            "laps": 3, "verified_completion": False, "manual_interventions": 1,
            "cost_usd": 0.5, "duration_ms": 1800, "stop_reason": "max_rounds",
        },
    )
    tracker.finish("wf-stop", status="failed")
    config = VOLYConfig(telemetry=TelemetryConfig(runs_dir=str(runs_dir)))

    result = CliRunner().invoke(
        workflow_cmd, ["stats", "--json"], obj={"config": config},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sample_size"] == 2
    assert payload["verified_rate"] == 0.5
    assert payload["average_laps"] == 2.5
    assert payload["total_cost_usd"] == 0.8
    assert payload["stop_reasons"] == {"clean": 1, "max_rounds": 1}
