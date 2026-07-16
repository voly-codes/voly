"""BO002 — FinOps suite load/validate + Phase 2 mock harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "benchmarks" / "finops-suite"
RUN_PY = SUITE_DIR / "run.py"

sys.path.insert(0, str(SUITE_DIR))
from harness import run_suite_comparison, summarize  # noqa: E402
from suite import (  # noqa: E402
    FIXTURE_DIR,
    inventory,
    load_suite,
    materialize_fixture,
)


def test_suite_loads_and_meets_phase1_dod():
    suite = load_suite()
    assert suite.suite_id
    assert len(suite.tasks) >= 5
    assert len(suite.billing_fallback_chain) >= 2
    inv = inventory(suite)
    assert inv["task_count"] == len(suite.tasks)
    assert inv["billing_fallback_tasks"], "need ≥1 billing_fallback task for C1"
    assert inv["cross_vendor_mock_tasks"], "need ≥1 cross-vendor mock task for C3"
    assert (FIXTURE_DIR / "hello.py").is_file()
    assert (FIXTURE_DIR / "counter.py").is_file()
    assert (FIXTURE_DIR / "util.py").is_file()


def test_materialize_fixture_copies_expected_files(tmp_path):
    suite = load_suite()
    dest = materialize_fixture(tmp_path / "proj")
    for task in suite.tasks:
        for rel in task.expected_files:
            assert (dest / rel).is_file(), f"{task.id}: missing {rel}"


def test_harness_billing_fallback_has_positive_savings(tmp_path):
    suite = load_suite()
    cwd = materialize_fixture(tmp_path / "proj")
    rows = run_suite_comparison(suite, str(cwd))
    summary = summarize(rows)
    assert summary["billing_fallback_rows"] >= 1
    assert summary["billing_fallback_saved_usd"] > 0
    assert summary["cross_vendor_rows"] >= 1
    # At least one row uses ≥2 distinct executor vendors
    multi = [r for r in rows if len(set(r.executors_used)) >= 2]
    assert multi, [r.as_dict() for r in rows]
    # Happy-path (no billing_fallback) should not invent negative chaos
    for r in rows:
        if "billing_fallback" not in r.scenarios:
            assert r.saved_usd == pytest.approx(0.0, abs=1e-9)
            assert r.voly_success is True


def test_results_json_schema_from_mock_runner():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--mode", "mock"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    path = SUITE_DIR / "results" / "results.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mode"] == "mock"
    assert data["phase"] == 2
    assert "rows" in data and len(data["rows"]) >= 5
    row = data["rows"][0]
    for key in (
        "task_id",
        "baseline_usd",
        "voly_usd",
        "saved_usd",
        "saved_pct",
        "executors_used",
        "fallback",
    ):
        assert key in row, key
    assert data["summary"]["billing_fallback_saved_usd"] > 0
    md = SUITE_DIR / "results" / "results.md"
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "baseline_usd" in text
    assert "Anti-claim" in text


def test_report_one_pager_is_external_safe():
    """Phase 3 DoD: REPORT.md ready for external link (no machine-local paths)."""
    report = (SUITE_DIR / "REPORT.md").read_text(encoding="utf-8")
    assert "LiteLLM" in report or "OpenRouter" in report
    assert "midchain-quota" in report
    assert "claude-code" in report and "zen" in report
    assert "26" in report  # headline saved_pct
    assert "Layer B" in report or "Layer B" in report.replace("**", "")
    # No Windows/local absolute paths
    assert "D:\\" not in report
    assert "/Users/" not in report
    assert "C:\\" not in report


def test_live_without_confirm_exits_nonzero():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--mode", "live"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3


def test_duplicate_task_id_rejected(tmp_path):
    src = (SUITE_DIR / "tasks.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "tasks.yaml"
    bad.write_text(
        src
        + """
  - id: tiny-rename
    category: tiny_refactor
    prompt: duplicate should fail validation clearly here
    expected_files: [hello.py]
    size: xs
    scenarios: [baseline]
    mock:
      billing_fail_executors: []
      succeed_executor: claude-code
      costs_usd:
        claude-code: 0.01
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate task id"):
        load_suite(bad)
