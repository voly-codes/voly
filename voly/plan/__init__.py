"""Plan state machine + store + verifiers (Rung B).

PR1: types, atomic store, engine (topo order, gates, transitions).
PR2: acceptance verifiers (command, files, git, output).
PR3+: CLI, multi-agent bridge.

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
from voly.plan.verify import (
    KNOWN_CHECK_TYPES,
    VerifyContext,
    VerifyResult,
    all_passed,
    complete_verification,
    run_acceptance,
    run_check,
    verify_step,
)

__all__ = [
    "AcceptanceCheck",
    "DONE",
    "FAILED",
    "IllegalTransition",
    "KNOWN_CHECK_TYPES",
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
    "VerifyContext",
    "VerifyResult",
    "all_passed",
    "complete_verification",
    "create_plan",
    "run_acceptance",
    "run_check",
    "verify_step",
]
