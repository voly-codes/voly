"""Capability-scored billing fallback chain."""

from __future__ import annotations

import logging
from pathlib import Path

from voly.capability.registry import CapabilityRegistry
from voly.capability.scorer import hard_exclude, routing_score

_log = logging.getLogger("voly.capability.fallback")

_MINIMUM_SCORE = 0.30


def _profiles_only_registry(profiles_dir: str) -> CapabilityRegistry:
    """Registry that reads materialized profiles only (no seed fallback)."""
    disabled_seeds = str(Path(profiles_dir) / ".seeds_disabled")
    return CapabilityRegistry(profiles_dir, seeds_dir=disabled_seeds)


def _has_materialized_profiles(profiles_dir: str) -> bool:
    path = Path(profiles_dir)
    if not path.is_dir():
        return False
    return any(path.glob("*.yaml")) or any(path.glob("*.yml"))


def build_fallback_chain(
    dimension: str,
    available_executors: list[str],
    project_features: list[str] | None = None,
    requires_file_tools: bool = True,
    profiles_dir: str = ".voly/capability/profiles",
    static_chain: list[str] | None = None,
) -> list[str]:
    """
    Return ordered list of executor IDs for billing fallback.

    Algorithm:
    1. Load profiles for all executors in available_executors.
    2. Apply hard_exclude() — excluded executors dropped from scored list.
    3. Score remaining with routing_score(profile, dimension, project_features).
    4. Sort descending by score.
    5. Append static_chain at the end (deduped, not already in scored list) as safety net.
    6. If no scored executors OR top score < _MINIMUM_SCORE → log degraded warning,
       return static_chain as-is.

    degraded=True is communicated via log, not via exception.
    """
    static = list(static_chain or available_executors)
    registry = _profiles_only_registry(profiles_dir)
    order = {executor_id: idx for idx, executor_id in enumerate(available_executors)}

    scored: list[tuple[str, float]] = []
    for executor_id in available_executors:
        profile = registry.load(executor_id)
        reason = hard_exclude(profile, requires_file_tools=requires_file_tools)
        if reason:
            continue
        score = routing_score(profile, dimension, project_features)
        scored.append((executor_id, score))

    scored.sort(key=lambda item: (-item[1], order.get(item[0], 999)))

    if not scored or scored[0][1] < _MINIMUM_SCORE:
        top = scored[0][1] if scored else None
        _log.warning(
            "capability fallback degraded: dimension=%s top_score=%s — using static chain",
            dimension,
            top,
        )
        return static

    chain = [executor_id for executor_id, _ in scored]
    seen = set(chain)
    for executor_id in static:
        if executor_id not in seen:
            chain.append(executor_id)
            seen.add(executor_id)
    return chain


def build_fallback_chain_or_static(
    dimension: str,
    available_executors: list[str],
    *,
    enabled: bool = False,
    project_features: list[str] | None = None,
    requires_file_tools: bool = True,
    profiles_dir: str = ".voly/capability/profiles",
    static_chain: list[str],
) -> tuple[list[str], bool]:
    """
    Returns (chain, capability_used).
    If enabled=False or registry is empty → return (static_chain, False).
    Otherwise → return (build_fallback_chain(...), True).
    """
    static = list(static_chain)
    if not enabled or not _has_materialized_profiles(profiles_dir):
        return static, False
    chain = build_fallback_chain(
        dimension,
        available_executors,
        project_features=project_features,
        requires_file_tools=requires_file_tools,
        profiles_dir=profiles_dir,
        static_chain=static,
    )
    return chain, True
