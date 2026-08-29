"""Shared capability-registry routing helper for the Agent/Workflow SDK.

Generalizes the evidence-based executor/model selection pattern
``voly.decisions._build_business_executor`` (business actions) and
``voly.a2a.lead.LeadOrchestrator._capability_hint`` (A2A auto-dispatch) each
implement separately, so ``voly.sdk.agent.Agent`` and the default
(non-injected) ``voly.plan.runner.PlanRunner._exec_chat``/``_exec_executor``
paths — covering both standalone ``Agent.run()`` calls and any
``Workflow``-compiled or hand-written Plan — get the same behavior without a
third copy of the ``ExecutorMatcher`` wiring.

Lives in ``voly.capability`` (not ``voly.sdk``) so ``voly.plan.runner`` (a
lower layer than ``voly.sdk``) can import it without a backwards dependency
on the SDK package.

Best-effort by design, matching ``_build_business_executor``'s convention:
disabled by default (``config.capability.enabled`` is ``False`` unless a
deployment opts in), and any registry/matcher error or "no match" falls back
to the caller's existing static resolution rather than raising — capability
routing must never be the reason a chat call or executor run fails.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("voly.capability.routing")


def capability_route(
    role: str,
    *,
    mode: str,
    config: Any,
    available_executors: list[str] | None = None,
) -> tuple[str, str, str] | None:
    """Resolve ``role`` to a capability-ranked hint, or ``None``.

    Returns ``(executor_id, model, provider)`` with exactly one side
    populated depending on ``mode``: ``mode="executor"`` populates
    ``executor_id`` only; any other ``mode`` (chat) populates
    ``model``/``provider`` only. Returns ``None`` when capability routing is
    disabled, the registry/matcher raises, or no profile is recommended —
    callers must have their own static fallback ready either way.
    """
    cap_cfg = getattr(config, "capability", None)
    if cap_cfg is None or not bool(getattr(cap_cfg, "enabled", False)):
        return None
    role_key = (role or "").strip().lower()
    if not role_key:
        return None
    try:
        from voly.a2a.lead import role_to_dimension
        from voly.capability.matcher import ExecutorMatcher, MatchRequest
        from voly.capability.registry import CapabilityRegistry

        registry = CapabilityRegistry(
            str(getattr(cap_cfg, "profiles_dir", "") or ".voly/capability/profiles")
        )
        matcher = ExecutorMatcher(
            registry, worker_url=str(getattr(cap_cfg, "worker_url", "") or "")
        )
        kind = "executor" if mode == "executor" else "model_provider"
        result = matcher.find_executors(MatchRequest(
            dimension=role_to_dimension(role_key),
            kind=kind,
            available_executors=available_executors,
            project_features=None,
            requires_file_tools=(kind == "executor"),
            routing_policy=str(getattr(cap_cfg, "routing_policy", "") or "balanced"),
            worker_timeout_s=float(getattr(cap_cfg, "worker_timeout_s", 5.0) or 5.0),
        ))
        if result.recommended is None:
            return None
        prof = result.recommended
        if kind == "executor":
            return (prof.id, "", "")
        if prof.model or prof.provider:
            return ("", prof.model or "", prof.provider or "")
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort, never break the caller
        _log.debug("capability routing failed for role=%s mode=%s: %s", role, mode, exc)
        return None
