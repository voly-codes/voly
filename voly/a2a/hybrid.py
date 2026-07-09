"""Hybrid multi-agent mode: role → chat vs executor.

See ``docs/proposals/hybrid-multiagent-executor.md``.

PR1 provides the policy map and resolution helpers. PR2 wires AgentRunner
for implement roles; until then ``run_local`` may inject a mock
``executor_runner`` or fall back to chat.
"""
from __future__ import annotations

from typing import Literal

RoleMode = Literal["chat", "executor"]

# Default implement set when a2a.executor_roles is empty.
DEFAULT_EXECUTOR_ROLES: frozenset[str] = frozenset({
    "developer",
    "bugfixer",
    "tester",
})

# Roles that never default to executor (lead override still allowed).
DEFAULT_CHAT_ROLES: frozenset[str] = frozenset({
    "architect",
    "reviewer",
    "devops",
    "security",
    "documenter",
})

_VALID_LEAD_EXECUTION = frozenset({"chat", "executor"})


def effective_executor_roles(executor_roles: list[str] | None) -> frozenset[str]:
    if executor_roles:
        return frozenset(r.strip() for r in executor_roles if r and str(r).strip())
    return DEFAULT_EXECUTOR_ROLES


def hybrid_active(
    *,
    hybrid_code_gen: bool,
    has_cwd: bool,
    hybrid_require_cwd: bool = True,
) -> bool:
    """Whether hybrid executor path is eligible for this run."""
    if not hybrid_code_gen:
        return False
    if hybrid_require_cwd and not has_cwd:
        return False
    return True


def resolve_role_mode(
    role: str,
    *,
    hybrid_enabled: bool,
    requires_code_gen: bool = True,
    lead_execution: str | None = None,
    executor_roles: list[str] | frozenset[str] | None = None,
) -> tuple[RoleMode, str]:
    """Return ``(mode, reason)`` for a sub-agent role.

    Policy (v1):
    - hybrid off → always chat
    - lead ``execution`` override when valid
    - ``tester`` is executor only when ``requires_code_gen``
    - default executor roles: developer, bugfixer, tester
    - everything else → chat
    """
    role_key = (role or "").strip().lower()
    if not hybrid_enabled:
        return "chat", "hybrid_disabled"

    if lead_execution:
        lead = str(lead_execution).strip().lower()
        if lead in _VALID_LEAD_EXECUTION:
            return lead, "lead_override"  # type: ignore[return-value]

    roles = (
        frozenset(executor_roles)
        if isinstance(executor_roles, frozenset)
        else effective_executor_roles(list(executor_roles) if executor_roles else None)
    )

    if role_key == "tester" and not requires_code_gen:
        return "chat", "tester_text_only"

    if role_key in roles:
        return "executor", "role_map"

    return "chat", "role_map_chat"
