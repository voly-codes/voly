from __future__ import annotations

import json
from importlib import import_module

from click.testing import CliRunner

from voly.cli.commands.workflow_cmd import workflow_cmd
from voly.config import VOLYConfig
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
