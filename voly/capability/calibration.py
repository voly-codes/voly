"""Benchmark → VOLY capability dimension mapping."""

from __future__ import annotations

from voly.capability.schema import CapabilityDomain

_BENCHMARK_TO_DIMS: dict[str, dict[str, float]] = {
    "swe_bench": {
        "backend": 0.95,
        "testing": 0.85,
        "frontend": 0.55,
        "architecture": 0.70,
    },
    "terminal_bench": {
        "devops": 0.90,
        "backend": 0.75,
        "testing": 0.70,
    },
    "livecode_bench": {
        "backend": 0.85,
        "testing": 0.80,
        "architecture": 0.65,
    },
}

_BENCHMARK_CONFIDENCE = 0.25


def calibrate(executor_id: str, benchmarks: list[dict]) -> dict[str, CapabilityDomain]:
    """Map benchmark raw scores to VOLY capability domains."""
    _ = executor_id
    domains: dict[str, CapabilityDomain] = {}
    for bench in benchmarks:
        name = str(bench.get("name") or "")
        mapping = _BENCHMARK_TO_DIMS.get(name)
        if not mapping:
            continue
        raw_score = float(bench.get("raw_score", 0.0))
        for dim, weight in mapping.items():
            score = weight * raw_score
            existing = domains.get(dim)
            if existing is None or score > existing.score:
                domains[dim] = CapabilityDomain(
                    score=score,
                    confidence=_BENCHMARK_CONFIDENCE,
                )
    return domains
