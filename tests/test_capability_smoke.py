"""Smoke tests for voly.capability (Phase 3)."""

from __future__ import annotations


def test_schema_instantiation():
    from voly.capability import ExecutorCapabilityProfile, CapabilityMatchResult

    p = ExecutorCapabilityProfile.unknown("test-exec")
    assert p.id == "test-exec"
    assert p.constraints.file_tools is True
    _ = CapabilityMatchResult(recommended=None, score=0.0, fallbacks=[], excluded=[])


def test_calibration():
    from voly.capability.calibration import calibrate

    domains = calibrate(
        "claude-code",
        [{"name": "swe_bench", "raw_score": 0.72, "date": "2025-01-01"}],
    )
    assert "backend" in domains
    assert domains["backend"].confidence == 0.25
    assert 0 < domains["backend"].score < 1.0


def test_registry_unknown_executor(tmp_path):
    from voly.capability.registry import CapabilityRegistry

    reg = CapabilityRegistry(str(tmp_path / "profiles"))
    profile = reg.load("unknown-exec")
    assert profile.id == "unknown-exec"
    assert profile.evidence.internal_runs == 0


def test_registry_seeds_load(tmp_path):
    import os

    from voly.capability.registry import CapabilityRegistry

    seeds_dir = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds_dir)
    profile = reg.load("claude-code")
    assert profile.id == "claude-code"
    assert "backend" in profile.capabilities


def test_registry_save_load_roundtrip(tmp_path):
    from voly.capability import ExecutorCapabilityProfile, CapabilityDomain
    from voly.capability.registry import CapabilityRegistry

    reg = CapabilityRegistry(str(tmp_path / "profiles"))
    p = ExecutorCapabilityProfile(
        id="test-exec",
        kind="executor",
        capabilities={"backend": CapabilityDomain(score=0.8, confidence=0.5)},
    )
    reg.save(p)
    loaded = reg.load("test-exec")
    assert loaded.capabilities["backend"].score == 0.8
