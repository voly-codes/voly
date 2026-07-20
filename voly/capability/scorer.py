"""Pure routing score and hard-gate functions — no I/O."""

from __future__ import annotations

from voly.capability.schema import ExecutorCapabilityProfile

ROUTING_SCORE_WEIGHTS = {
    "capability_match": 0.40,
    "historical_success": 0.20,
    "tool_compatibility": 0.15,
    "project_stack_match": 0.10,
    "availability": 0.05,
    "cost_efficiency": 0.05,
    "latency": 0.05,
}

# routing_policy → weight overrides (must still sum to ~1.0)
ROUTING_POLICY_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": dict(ROUTING_SCORE_WEIGHTS),
    "quality_first": {
        "capability_match": 0.50,
        "historical_success": 0.25,
        "tool_compatibility": 0.10,
        "project_stack_match": 0.10,
        "availability": 0.03,
        "cost_efficiency": 0.01,
        "latency": 0.01,
    },
    "budget_first": {
        "capability_match": 0.20,
        "historical_success": 0.10,
        "tool_compatibility": 0.10,
        "project_stack_match": 0.10,
        "availability": 0.05,
        "cost_efficiency": 0.35,
        "latency": 0.10,
    },
}

VALID_ROUTING_POLICIES = frozenset(ROUTING_POLICY_WEIGHTS)

_FEATURE_MAP: dict[str, str] = {
    "react": "frontend",
    "svelte": "frontend",
    "vue": "frontend",
    "next.js": "frontend",
    "fastapi": "backend",
    "django": "backend",
    "flask": "backend",
    "pytest": "testing",
    "jest": "testing",
    "vitest": "testing",
    "docker": "devops",
    "kubernetes": "devops",
    "terraform": "devops",
    "typescript": "frontend",
    "python": "backend",
    "go": "backend",
}

_LATENCY_CAP_MS = 120_000


def feature_to_dimension(feature: str) -> str | None:
    """Map a detected project feature/framework to a capability dimension."""
    return _FEATURE_MAP.get(feature.strip().lower())


def routing_score(
    profile: ExecutorCapabilityProfile,
    dimension: str,
    project_features: list[str] | None = None,
    *,
    routing_policy: str = "balanced",
) -> float:
    """
    Compute weighted routing score.

    - capability_match: profile.capabilities[dimension].score (or 0.5 if unknown)
    - historical_success: successful_runs / max(1, internal_runs)
    - tool_compatibility: 1.0 if file_tools else 0.0
    - project_stack_match: 0.5 neutral if no features; else fraction matching dimension
    - availability: 1.0 (always available, Phase 5 will update)
    - cost_efficiency: max(0, 1 - cost_per_task_usd) clamped 0..1; 1.0 if free
    - latency: max(0, 1 - avg_latency_ms / 120000) clamped 0..1

    ``routing_policy`` selects weight sets: balanced | quality_first | budget_first.

    Return score clamped to [0.0, 1.0].
    """
    domain = profile.capabilities.get(dimension)
    capability_match = domain.score if domain else 0.5

    internal_runs = profile.evidence.internal_runs
    successful_runs = profile.evidence.successful_runs
    historical_success = successful_runs / max(1, internal_runs)

    tool_compatibility = 1.0 if profile.constraints.file_tools else 0.0

    if not project_features:
        project_stack_match = 0.5
    else:
        matches = sum(
            1
            for feature in project_features
            if feature_to_dimension(feature) == dimension
        )
        project_stack_match = matches / len(project_features)

    availability = 1.0

    cost = profile.operational.cost_per_task_usd
    if cost == 0:
        cost_efficiency = 1.0
    else:
        cost_efficiency = max(0.0, min(1.0, 1.0 - cost))

    latency_ms = profile.operational.avg_latency_ms
    latency = max(0.0, min(1.0, 1.0 - latency_ms / _LATENCY_CAP_MS))

    policy = (routing_policy or "balanced").strip().lower()
    weights = ROUTING_POLICY_WEIGHTS.get(policy) or ROUTING_SCORE_WEIGHTS
    total = (
        capability_match * weights["capability_match"]
        + historical_success * weights["historical_success"]
        + tool_compatibility * weights["tool_compatibility"]
        + project_stack_match * weights["project_stack_match"]
        + availability * weights["availability"]
        + cost_efficiency * weights["cost_efficiency"]
        + latency * weights["latency"]
    )
    return max(0.0, min(1.0, total))


def hard_exclude(
    profile: ExecutorCapabilityProfile,
    requires_file_tools: bool = False,
    requires_browser_tools: bool = False,
) -> str | None:
    """Return exclusion reason string, or None if profile passes all hard gates."""
    if requires_file_tools and not profile.constraints.file_tools:
        return "missing_file_tools"
    if requires_browser_tools and not profile.constraints.browser_tools:
        return "missing_browser_tools"
    return None
