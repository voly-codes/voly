"""Root-cause attribution for executor outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from voly.evidence.schema import RepositoryBaseline


@dataclass(frozen=True)
class RootCause:
    failure_class: str
    state: str
    penalize_agent: bool


def classify_root_cause(
    *,
    success: bool,
    error_class: str = "",
    error: str = "",
    baseline: RepositoryBaseline,
) -> RootCause:
    """Classify failures without blaming the agent for upstream conditions."""
    if success:
        return RootCause("", "execution_success", False)

    normalized = (error_class or "").strip().lower()
    lowered_error = (error or "").lower()
    if normalized == "billing":
        return RootCause("provider_failure", "hard_failure", False)
    if normalized == "not_available":
        return RootCause("tool_failure", "hard_failure", False)
    if normalized == "timeout":
        return RootCause("tool_failure", "soft_failure", False)
    if "safety:" in lowered_error:
        return RootCause("policy_violation", "policy_violation", False)
    if baseline.health == "environment_failure":
        return RootCause("environment_failure", "environment_failure", False)
    if baseline.health == "preexisting_failure":
        return RootCause("repository_failure", "environment_failure", False)
    return RootCause("agent_failure", "hard_failure", True)
