"""Deterministic evaluation of the bounded execution trajectory."""

from __future__ import annotations

from collections import Counter
from typing import Any


def evaluate_trajectory(result: Any) -> tuple[bool, str, dict[str, Any]]:
    """Evaluate standardized runner metadata without exposing error text."""
    raw_metadata = getattr(result, "metadata", None)
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    issues: list[str] = []

    raw_chain = metadata.get("chain_timelog", [])
    if raw_chain and not isinstance(raw_chain, list):
        issues.append("malformed_chain_timelog")
        chain: list[Any] = []
    else:
        chain = raw_chain or []

    statuses: Counter[str] = Counter()
    for entry in chain:
        if not isinstance(entry, dict):
            issues.append("malformed_chain_entry")
            continue
        statuses[str(entry.get("status") or "unknown")] += 1

    rolled_back = metadata.get("safety_rolled_back", [])
    if rolled_back and not isinstance(rolled_back, list):
        issues.append("malformed_safety_rollback")
        rollback_count = 0
    else:
        rollback_count = len(rolled_back or [])

    if metadata.get("safety_violation"):
        issues.append("safety_policy_event")
    if rollback_count:
        issues.append("files_rolled_back")

    inner_retries = metadata.get("retry_count", 0)
    try:
        retry_count = max(0, int(inner_retries or 0))
    except (TypeError, ValueError):
        issues.append("malformed_retry_count")
        retry_count = 0

    detail: dict[str, Any] = {
        "attempt_count": max(1, len(chain)),
        "attempt_statuses": dict(sorted(statuses.items())),
        "executor_retry_count": retry_count,
        "fallback_used": len(chain) > 1,
        "rollback_count": rollback_count,
        "dry_run": bool(metadata.get("dry_run")),
        "tool_trace_available": bool(metadata.get("tool_trace")),
        "issues": sorted(set(issues)),
    }
    if issues:
        return False, f"{len(set(issues))} trajectory policy issue(s)", detail
    return True, "bounded execution trajectory is policy-clean", detail
