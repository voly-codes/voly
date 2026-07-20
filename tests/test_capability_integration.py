"""Full capability pipeline integration tests (Phase 9). No network calls."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _seeds_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "voly", "capability", "seeds")


def test_full_match_flow_with_seeds(tmp_path):
    from voly.capability.matcher import ExecutorMatcher, MatchRequest
    from voly.capability.registry import CapabilityRegistry

    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=_seeds_dir())
    matcher = ExecutorMatcher(reg)
    req = MatchRequest(
        dimension="backend",
        available_executors=None,
        project_features=["fastapi", "python"],
    )
    result = matcher.find_executors(req)
    assert result.recommended is not None
    assert result.score > 0.4
    assert result.recommended.id in [
        "claude-code",
        "cursor",
        "deepseek",
        "kimi-cli",
        "opencode",
        "wrangler",
        "zen",
    ]


def test_evidence_updates_local_ema(tmp_path):
    from voly.capability import CapabilityDomain, ExecutorCapabilityProfile
    from voly.capability.evidence import _update_local_ema
    from voly.capability.registry import CapabilityRegistry

    profiles_dir = str(tmp_path / "profiles")
    reg = CapabilityRegistry(profiles_dir)
    profile = ExecutorCapabilityProfile(
        id="test-exec",
        kind="executor",
        capabilities={"backend": CapabilityDomain(score=0.5, confidence=0.0)},
    )
    reg.save(profile)
    _update_local_ema(
        "test-exec", "backend", 0.75, True, profiles_dir=profiles_dir
    )
    updated = reg.load("test-exec")
    assert updated.capabilities["backend"].score > 0.5
    assert updated.capabilities["backend"].confidence > 0.0


def test_capability_fallback_chain_ordering(tmp_path):
    from voly.capability.fallback import build_fallback_chain_or_static
    from voly.capability.registry import CapabilityRegistry

    profiles_dir = str(tmp_path / "profiles")
    reg = CapabilityRegistry(profiles_dir, seeds_dir=_seeds_dir())
    for eid in ["claude-code", "cursor", "zen"]:
        reg.load(eid)
    static = ["zen", "cursor", "claude-code"]
    chain, used = build_fallback_chain_or_static(
        "backend",
        static,
        enabled=True,
        profiles_dir=profiles_dir,
        static_chain=static,
    )
    assert used is True
    zen_idx = chain.index("zen")
    assert zen_idx > 0


def test_evidence_skips_billing_error(tmp_path):
    from voly.capability.evidence import record_run, RunRecord

    profiles_dir = str(tmp_path / "profiles")
    rec = RunRecord("claude-code", "backend", success=False, billing_error=True)
    record_run(rec, worker_url="", profiles_dir=profiles_dir)
    assert not os.path.exists(os.path.join(profiles_dir, "claude-code.yaml"))


def test_frontend_dimension_prefers_kimi(tmp_path):
    from voly.capability.matcher import ExecutorMatcher, MatchRequest
    from voly.capability.registry import CapabilityRegistry

    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=_seeds_dir())
    matcher = ExecutorMatcher(reg)
    req = MatchRequest(
        dimension="frontend",
        available_executors=None,
        project_features=["react", "typescript"],
    )
    result = matcher.find_executors(req)
    assert result.recommended is not None
    assert result.recommended.id == "kimi-cli"


def test_sync_roles_payload():
    from voly.a2a.roles import ROLE_REGISTRY
    from voly.capability.sync import sync_roles_to_worker

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True, "upserted": 11}
        mock_post.return_value = mock_resp
        ok = sync_roles_to_worker("http://localhost:8787", timeout_s=1.0)
    assert ok is True
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
    assert "roles" in payload
    assert len(payload["roles"]) == len(ROLE_REGISTRY)
    assert len(payload["roles"]) >= 11


def test_intelligence_features_for_matcher():
    from voly.capability.scorer import feature_to_dimension
    from voly.intelligence.schema import (
        LicenseInfo,
        QualityInfo,
        RepositoryIntelligence,
        StackInfo,
    )

    intel = RepositoryIntelligence(
        repository="test/repo",
        commit="abc123",
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        api_enriched=False,
        license=LicenseInfo(
            spdx="mit",
            commercial_use=True,
            modification=True,
            distribution=True,
            notice_required=False,
            copyleft=False,
            risk="low",
        ),
        stack=StackInfo(
            languages=["python", "typescript"],
            frameworks=["fastapi", "react"],
            runtime=["python3", "node"],
            versions={},
        ),
        architecture={
            "style": "modular",
            "entrypoints": [],
            "modules": [],
            "ai_assisted": False,
        },
        quality=QualityInfo(
            tests="partial",
            ci=True,
            documentation="minimal",
            maintainability_score=0.65,
            test_types=[],
            coverage_configured=False,
            test_command=None,
            last_commit_days_ago=None,
            open_issues=None,
            open_prs=None,
        ),
        reuse_candidates=[],
        risks=[],
        architect_context={},
    )
    features = intel.stack.languages + intel.stack.frameworks
    assert "fastapi" in features
    assert "react" in features
    dims = {feature_to_dimension(f) for f in features if feature_to_dimension(f)}
    assert "backend" in dims
    assert "frontend" in dims
