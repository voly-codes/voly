"""Plan state machine + store (Rung B).

PR1: types, atomic store, engine (topo order, gates, transitions).
PR2+: verifiers, CLI, multi-agent bridge.

See ``docs/proposals/plan-gate-verification.md``.
"""

from voly.plan.engine import PlanEngine, create_plan
from voly.plan.store import PlanStore
from voly.plan.types import (
    DONE,
    FAILED,
    LEGAL_TRANSITIONS,
    MODE_CHAT,
    MODE_EXECUTOR,
    PENDING,
    PLAN_ABORTED,
    PLAN_COMPLETED,
    PLAN_FAILED,
    PLAN_PENDING,
    PLAN_RUNNING,
    RUNNING,
    SCHEMA_VERSION,
    SKIPPED,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    IllegalTransition,
    Plan,
    PlanError,
    PlanStep,
    PlanValidationError,
)

__all__ = [
    "AcceptanceCheck",
    "DONE",
    "FAILED",
    "IllegalTransition",
    "LEGAL_TRANSITIONS",
    "MODE_CHAT",
    "MODE_EXECUTOR",
    "PENDING",
    "PLAN_ABORTED",
    "PLAN_COMPLETED",
    "PLAN_FAILED",
    "PLAN_PENDING",
    "PLAN_RUNNING",
    "Plan",
    "PlanEngine",
    "PlanError",
    "PlanStep",
    "PlanStore",
    "PlanValidationError",
    "RUNNING",
    "SCHEMA_VERSION",
    "SKIPPED",
    "VERIFIED",
    "VERIFYING",
    "create_plan",
]
