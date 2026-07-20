"""Tests for voly.capability.evidence (Phase 5)."""

from __future__ import annotations

import pytest


def test_skip_on_billing_error():
    from voly.capability.evidence import RunRecord, _compute_run_score

    rec = RunRecord("test", "backend", success=False, billing_error=True)
    assert _compute_run_score(rec) is None


def test_score_success_no_files():
    from voly.capability.evidence import RunRecord, _compute_run_score

    rec = RunRecord("test", "backend", success=True, files_changed=0)
    assert _compute_run_score(rec) == pytest.approx(0.35)


def test_score_success_with_files():
    from voly.capability.evidence import RunRecord, _compute_run_score

    rec = RunRecord("test", "backend", success=True, files_changed=3)
    assert 0.5 < _compute_run_score(rec) <= 0.80


def test_score_retry_penalty():
    from voly.capability.evidence import RunRecord, _compute_run_score

    rec = RunRecord("test", "backend", success=True, files_changed=3, retry_count=2)
    base = 0.75
    expected = base * (0.90 ** 2)
    assert _compute_run_score(rec) == pytest.approx(expected, rel=0.01)


def test_score_failure():
    from voly.capability.evidence import RunRecord, _compute_run_score

    rec = RunRecord("test", "backend", success=False, files_changed=5)
    assert _compute_run_score(rec) == 0.0


def test_record_run_no_worker(tmp_path):
    from voly.capability.evidence import record_run, RunRecord

    rec = RunRecord("claude-code", "backend", success=True, files_changed=2)
    record_run(rec, worker_url="", profiles_dir=str(tmp_path / "profiles"))
