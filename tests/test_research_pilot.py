from __future__ import annotations

import json

from click.testing import CliRunner

from voly.cli.main import main
from voly.research import ResearchDecision, run_research, save_report


def test_small_task_is_skipped_without_scanning(tmp_path):
    report = run_research("fix typo", tmp_path)

    assert report.eligible is False
    assert report.decision is ResearchDecision.BUILD
    assert report.candidates == []
    assert report.network_used is False


def test_local_candidate_produces_adapt_decision(tmp_path):
    source = tmp_path / "docs" / "security-pipeline.md"
    source.parent.mkdir()
    source.write_text("Security pipeline integration architecture.", encoding="utf-8")

    report = run_research(
        "Design a security pipeline integration architecture for the agent",
        tmp_path,
    )

    assert report.eligible is True
    assert report.decision is ResearchDecision.ADAPT
    assert report.selected_candidate_id == "local-1"
    assert report.candidates[0].location == "docs/security-pipeline.md"
    assert report.network_used is False


def test_existing_reuse_report_can_produce_reuse_decision(tmp_path):
    reports = tmp_path / ".voly" / "reuse" / "reports"
    reports.mkdir(parents=True)
    (reports / "latest.json").write_text(json.dumps({
        "report_id": "reuse123",
        "picked": [{
            "repo": "example/project",
            "path": "src/auth.py",
            "confidence": 0.9,
            "reason": "matching authentication flow",
        }],
    }), encoding="utf-8")

    report = run_research(
        "Implement a secure authentication integration for the API",
        tmp_path,
    )

    assert report.decision is ResearchDecision.REUSE
    assert report.candidates[0].provenance == "reuse-report:reuse123"


def test_report_save_is_typed_json(tmp_path):
    report = run_research("Design an agent security integration pipeline", tmp_path)
    path = save_report(report, tmp_path / "reports")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["mode"] == "shadow"
    assert payload["network_used"] is False
    assert (tmp_path / "reports" / "latest.json").is_file()


def test_research_cli_shadow(tmp_path):
    result = CliRunner().invoke(
        main,
        ["research", "shadow", "Design an API security integration", "--cwd", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "eligible=true" in result.output
    assert (tmp_path / ".voly" / "research" / "reports" / "latest.json").is_file()
