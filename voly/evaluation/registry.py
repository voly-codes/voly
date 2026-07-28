"""Built-in EvalPolicy registry and deterministic task-policy selection."""

from __future__ import annotations

from voly.evaluation.schema import EvalPolicy, EvalRequirement

_BASE_REQUIREMENTS = (
    EvalRequirement("executor", "executor_success"),
    EvalRequirement("safety", "safety_policy"),
    EvalRequirement("changes", "file_changes"),
    EvalRequirement("post_checks", "baseline_replay"),
)

_POLICIES = {
    policy.id: policy
    for policy in (
        EvalPolicy(
            id="executor-basic",
            version="1",
            task_types=("unknown", "backend", "frontend", "refactoring"),
            requirements=_BASE_REQUIREMENTS,
        ),
        EvalPolicy(
            id="documentation-basic",
            version="1",
            task_types=("docs", "documentation"),
            requirements=_BASE_REQUIREMENTS,
        ),
        EvalPolicy(
            id="testing-basic",
            version="1",
            task_types=("tests", "testing"),
            requirements=_BASE_REQUIREMENTS,
        ),
    )
}


def list_policies() -> list[EvalPolicy]:
    return sorted(_POLICIES.values(), key=lambda policy: policy.id)


def get_policy(policy_id: str) -> EvalPolicy:
    try:
        return _POLICIES[policy_id]
    except KeyError as exc:
        raise ValueError(f"unknown eval policy: {policy_id}") from exc


def select_policy(task_type: str | None, policy_id: str = "auto") -> EvalPolicy:
    requested = (policy_id or "auto").strip()
    if requested != "auto":
        return get_policy(requested)
    normalized = (task_type or "unknown").strip().lower()
    for policy in list_policies():
        if normalized in policy.task_types:
            return policy
    return get_policy("executor-basic")
