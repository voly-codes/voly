"""Tests for capability-scored billing fallback chain (Phase 6)."""

from __future__ import annotations


def test_fallback_disabled_returns_static():
    from voly.capability.fallback import build_fallback_chain_or_static

    static = ["claude-code", "cursor", "zen"]
    chain, used = build_fallback_chain_or_static(
        "backend", static, enabled=False, static_chain=static
    )
    assert chain == static
    assert used is False


def test_fallback_empty_registry(tmp_path):
    from voly.capability.fallback import build_fallback_chain_or_static

    static = ["claude-code", "cursor", "zen"]
    chain, used = build_fallback_chain_or_static(
        "backend",
        static,
        enabled=True,
        profiles_dir=str(tmp_path / "profiles"),
        static_chain=static,
    )
    assert chain == static
    assert used is False


def test_fallback_with_seeds(tmp_path):
    import os

    from voly.capability.fallback import build_fallback_chain
    from voly.capability.registry import CapabilityRegistry

    seeds_dir = os.path.join(
        os.path.dirname(__file__), "..", "voly", "capability", "seeds"
    )
    reg = CapabilityRegistry(str(tmp_path / "profiles"), seeds_dir=seeds_dir)
    for eid in ["claude-code", "cursor", "zen"]:
        reg.load(eid)
    chain = build_fallback_chain(
        "backend",
        ["claude-code", "cursor", "zen"],
        profiles_dir=str(tmp_path / "profiles"),
        static_chain=["claude-code", "cursor", "zen"],
    )
    assert len(chain) >= 3
    assert "zen" in chain


def test_build_fallback_excludes_no_file_tools(tmp_path):
    from voly.capability import ExecutorCapabilityProfile
    from voly.capability.fallback import build_fallback_chain
    from voly.capability.registry import CapabilityRegistry
    from voly.capability.schema import ConstraintsInfo

    reg = CapabilityRegistry(str(tmp_path / "profiles"))
    profile = ExecutorCapabilityProfile(
        id="no-files",
        kind="executor",
        constraints=ConstraintsInfo(file_tools=False),
    )
    reg.save(profile)
    chain = build_fallback_chain(
        "backend",
        ["no-files"],
        requires_file_tools=True,
        profiles_dir=str(tmp_path / "profiles"),
        static_chain=["claude-code"],
    )
    assert "no-files" not in chain
