from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import patch

from click.testing import CliRunner

from voly.cli.commands.workflow_cmd import workflow_cmd
from voly.config import TelemetryConfig, VOLYConfig
from voly.runtime.runs import RunTracker
from voly.workflow import ReviewLoopResult, ReviewStopReason


def _sdk_config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


_WORKFLOW_DOC = {
    "name": "research-review",
    "task": "Compare two markets",
    "nodes": [
        {"id": "research", "agent": {"name": "researcher"}},
        {"id": "review", "agent": {"name": "reviewer"}, "depends_on": ["research"]},
    ],
}


def _chat_ok(self, **kwargs):
    return {"content": f"ok:{kwargs.get('agent')}", "model": "x", "usage": {}}


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


# ── Phase 5 SDK workflow subcommands ─────────────────────────────────────


def test_workflow_validate_ok(tmp_path) -> None:
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(_WORKFLOW_DOC), encoding="utf-8")

    result = CliRunner().invoke(
        workflow_cmd, ["validate", str(path)], obj={"config": _sdk_config(tmp_path)},
    )

    assert result.exit_code == 0, result.output
    assert "research-review" in result.output
    assert "['research', 'review']" in result.output


def test_workflow_validate_reports_cycle(tmp_path) -> None:
    doc = {
        "name": "bad",
        "nodes": [
            {"id": "a", "agent": {"name": "x"}, "depends_on": ["b"]},
            {"id": "b", "agent": {"name": "y"}, "depends_on": ["a"]},
        ],
    }
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = CliRunner().invoke(
        workflow_cmd, ["validate", str(path)], obj={"config": _sdk_config(tmp_path)},
    )

    assert result.exit_code == 1
    assert "invalid" in result.output


def test_workflow_run_and_show_round_trip(tmp_path) -> None:
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(_WORKFLOW_DOC), encoding="utf-8")
    config = _sdk_config(tmp_path)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        run_result = CliRunner().invoke(
            workflow_cmd, ["run", str(path), "--json-out"], obj={"config": config},
        )

    assert run_result.exit_code == 0, run_result.output
    payload = json.loads(run_result.output)
    assert payload["success"] is True
    assert [n["node_id"] for n in payload["nodes"]] == ["research", "review"]
    plan_id = payload["plan_id"]

    show_result = CliRunner().invoke(
        workflow_cmd, ["show", plan_id, "--json-out"], obj={"config": config},
    )
    assert show_result.exit_code == 0, show_result.output
    shown = json.loads(show_result.output)
    assert shown["plan_id"] == plan_id
    assert shown["metadata"]["workflow_name"] == "research-review"


def test_workflow_run_task_and_cwd_overrides(tmp_path) -> None:
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(_WORKFLOW_DOC), encoding="utf-8")
    config = _sdk_config(tmp_path)
    seen = {}

    def chat(self, **kwargs):
        seen["content"] = kwargs["messages"][0]["content"]
        return _chat_ok(self, **kwargs)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = CliRunner().invoke(
            workflow_cmd,
            ["run", str(path), "--task", "Override task", "--json-out"],
            obj={"config": config},
        )

    assert result.exit_code == 0, result.output
    assert "Override task" in seen["content"]


def test_workflow_resume_continues_a_paused_approval_node(tmp_path) -> None:
    doc = {
        "name": "gated",
        "nodes": [
            {"id": "decide", "agent": {"name": "manager"}, "approval": True},
            {"id": "notify", "agent": {"name": "notifier"}, "depends_on": ["decide"]},
        ],
    }
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    config = _sdk_config(tmp_path)

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        run_result = CliRunner().invoke(
            workflow_cmd, ["run", str(path), "--json-out"], obj={"config": config},
        )
    payload = json.loads(run_result.output)
    assert run_result.exit_code == 1  # paused on approval, not yet successful
    plan_id = payload["plan_id"]

    from voly.plan.approval import decide as decide_human_review
    from voly.plan.store import PlanStore

    decide_human_review(PlanStore(config.plan.store_dir), plan_id, "decide", "approve")

    with patch("voly.ai_gateway.gateway.AIGateway.chat", _chat_ok):
        resume_result = CliRunner().invoke(
            workflow_cmd, ["resume", plan_id, "--json-out"], obj={"config": config},
        )

    assert resume_result.exit_code == 0, resume_result.output
    resumed_payload = json.loads(resume_result.output)
    assert resumed_payload["success"] is True


def test_workflow_show_unknown_plan_id_fails(tmp_path) -> None:
    result = CliRunner().invoke(
        workflow_cmd, ["show", "nope"], obj={"config": _sdk_config(tmp_path)},
    )
    assert result.exit_code == 1
    assert "No plan" in result.output
