"""Tests for capability matcher and scorer (Phase 4)."""

from __future__ import annotations


def test_routing_score_known_dimension():
    from voly.capability import CapabilityDomain, ExecutorCapabilityProfile
    from voly.capability.scorer import routing_score

    p = ExecutorCapabilityProfile(
        id="test",
        kind="executor",
        capabilities={"backend": CapabilityDomain(score=0.9, confidence=0.5)},
    )
    score = routing_score(p, "backend")
    assert 0.5 < score <= 1.0


def test_routing_score_unknown_dimension():
    from voly.capability import ExecutorCapabilityProfile
    from voly.capability.scorer import routing_score

    p = ExecutorCapabilityProfile.unknown("test")
    score = routing_score(p, "frontend")
    assert 0.3 <= score <= 0.7


def test_hard_exclude_no_file_tools():
    from voly.capability import ExecutorCapabilityProfile
    from voly.capability.schema import ConstraintsInfo
    from voly.capability.scorer import hard_exclude

    p = ExecutorCapabilityProfile(
        id="test",
        kind="executor",
        constraints=ConstraintsInfo(file_tools=False),
    )
    reason = hard_exclude(p, requires_file_tools=True)
    assert reason is not None


def test_hard_exclude_passes():
    from voly.capability import ExecutorCapabilityProfile
    from voly.capability.scorer import hard_exclude

    p = ExecutorCapabilityProfile.unknown("test")
    assert hard_exclude(p) is None


def test_local_match_returns_result(tmp_path):
    import os

    from voly.capability.matcher import ExecutorMatcher, MatchRequest
    from voly.capability.registry import CapabilityRegistry

    seeds = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds)
    matcher = ExecutorMatcher(reg)
    req = MatchRequest(
        dimension="backend",
        available_executors=None,
        project_features=["python"],
    )
    result = matcher.find_executors(req)
    assert result.recommended is not None
    assert result.score > 0.3


def test_feature_to_dimension():
    from voly.capability.scorer import feature_to_dimension

    assert feature_to_dimension("react") == "frontend"
    assert feature_to_dimension("pytest") == "testing"
    assert feature_to_dimension("unknown_pkg") is None
