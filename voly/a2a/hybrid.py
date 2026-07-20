"""Hybrid multi-agent mode: role → chat vs executor.

See ``docs/proposals/hybrid-multiagent-executor.md``.

PR1: policy map + ``run_local`` branch.
PR2: ``make_agent_runner_executor`` wires AgentRunner + billing fallback.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from voly.a2a.roles import ROLE_REGISTRY, RoleMode

# Default implement set when a2a.executor_roles is empty.
# tester writes pytest files on code-gen tasks (chat-only left empty trees).
DEFAULT_EXECUTOR_ROLES: frozenset[str] = frozenset({
    "developer",
    "bugfixer",
    "tester",
    "devops",
})

# Roles that may use hybrid executor mode (lead cannot promote others).
EXECUTOR_CAPABLE_ROLES: frozenset[str] = frozenset(
    r.id for r in ROLE_REGISTRY.values() if r.mode == "executor"
)

# Per-role executor when hybrid mode=executor.
# Env overrides (also listed for scripts/check_env_doc_sync.py):
# VOLY_A2A_EXECUTOR_DEVELOPER, VOLY_A2A_EXECUTOR_BUGFIXER,
# VOLY_A2A_EXECUTOR_TESTER, VOLY_A2A_EXECUTOR_DEVOPS.
_ROLE_EXECUTOR: dict[str, str] = {
    r.id: r.default_executor for r in ROLE_REGISTRY.values() if r.default_executor
}

# Roles that never default to executor (lead cannot promote to executor).
DEFAULT_CHAT_ROLES: frozenset[str] = frozenset({
    "architect",
    "reviewer",
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


_EXECUTOR_DEFAULT_SENTINEL = "claude-code"


def resolve_role_executor(role: str, fallback: str = "claude-code") -> str:
    """Pick the file-writing executor for a hybrid role.

    Priority: env override > explicit config (fallback != sentinel) > hardmap > sentinel.
    """
    import os

    role_key = (role or "").strip().lower()
    env_key = f"VOLY_A2A_EXECUTOR_{role_key.upper()}"
    override = os.environ.get(env_key, "").strip()
    if override:
        return override
    # Config-level executor_default beats the per-role hardmap only when the
    # caller explicitly set a non-default value (i.e. changed from "claude-code").
    if fallback and fallback != _EXECUTOR_DEFAULT_SENTINEL:
        return fallback
    return _ROLE_EXECUTOR.get(role_key, fallback or _EXECUTOR_DEFAULT_SENTINEL)


def resolve_role_mode(
    role: str,
    *,
    hybrid_enabled: bool,
    requires_code_gen: bool = True,
    lead_execution: str | None = None,
    executor_roles: list[str] | frozenset[str] | None = None,
) -> tuple[RoleMode, str]:
    """Return ``(mode, reason)`` for a sub-agent role.

    Policy (v2):
    - hybrid off → always chat
    - lead ``execution`` override only for EXECUTOR_CAPABLE_ROLES
    - default executor roles: developer, bugfixer, tester, devops
    - everything else → chat
    """
    role_key = (role or "").strip().lower()
    if not hybrid_enabled:
        return "chat", "hybrid_disabled"

    if lead_execution:
        lead = str(lead_execution).strip().lower()
        if lead in _VALID_LEAD_EXECUTION:
            if lead == "executor" and role_key not in EXECUTOR_CAPABLE_ROLES:
                return "chat", "lead_executor_denied"
            return lead, "lead_override"  # type: ignore[return-value]

    roles = (
        frozenset(executor_roles)
        if isinstance(executor_roles, frozenset)
        else effective_executor_roles(list(executor_roles) if executor_roles else None)
    )

    if role_key == "tester" and not requires_code_gen:
        return "chat", "tester_text_only"

    if role_key in roles and role_key in EXECUTOR_CAPABLE_ROLES:
        return "executor", "role_map"

    return "chat", "role_map_chat"


def make_agent_runner_executor(
    config: Any,
    *,
    max_turns: int = 30,
    timeout: int = 300,
    emit_event: bool = False,
) -> Callable[..., dict[str, Any]]:
    """Build an ``executor_runner`` for ``run_local`` using AgentRunner.

    Passes the configured executor name (e.g. ``claude-code``) so the billing
    fallback chain applies. Sub-role runs default to ``emit_event=False`` so the
    parent multi-agent ``TaskEvent`` remains the primary telemetry record.
    """
    from voly.runner.agent_runner import AgentRunner

    runner = AgentRunner(config)

    def executor_runner(
        *,
        role: str,
        task: str,
        cwd: str,
        executor: str,
        system: str,
        assignment: Any,
    ) -> dict[str, Any]:
        full_task = task
        if system and system.strip():
            full_task = (
                f"{system.strip()}\n\n---\n\n"
                f"## Sub-task ({role})\n\n{task}"
            )
        # Role-specific executor (developer→cursor, bugfixer→deepseek, …).
        agent_key = resolve_role_executor(role, (executor or "claude-code").strip() or "claude-code")
        from voly.a2a.cwd_lock import cwd_executor_lock

        with cwd_executor_lock(cwd or "", timeout=float(timeout or 900) + 30.0):
            rr = runner.run(
                full_task,
                agent_key,
                cwd=cwd or "",
                max_turns=max_turns,
                timeout=timeout,
                emit_event=emit_event,
                collect_evidence=False,
            )
        er = rr.result
        files: list[str] = []
        if er.report is not None:
            files = list(
                dict.fromkeys(
                    f
                    for f in (
                        list(er.report.files_changed or [])
                        + list(er.report.files_created or [])
                    )
                    if f and not str(f).startswith(".voly/")
                )
            )
        return {
            "ok": bool(rr.success),
            "success": bool(rr.success),
            "content": (er.output or er.error or ""),
            "error": (er.error or "") if not rr.success else "",
            "cost_usd": float(er.cost_usd or 0.0),
            "input_tokens": int(er.input_tokens or 0),
            "output_tokens": int(er.output_tokens or 0),
            "files_touched": files,
            "executor": rr.executor or agent_key,
        }

    return executor_runner
