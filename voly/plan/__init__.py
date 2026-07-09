"""Plan state machine + store + verifiers + runner (Rung B).

PR1: types, atomic store, engine (topo order, gates, transitions).
PR2: acceptance verifiers (command, files, git, output).
PR3: PlanRunner + CLI (voly plan run|list|show|status|validate).
PR4: multi-agent A2A bridge (assignments → plan gates in run_local).
PR5: criteria compiler + scanner suggestions + user guide.

See ``docs/proposals/plan-gate-verification.md`` and ``docs/backend/plan.md``.
"""

from voly.plan.bridge import (
    assignment_step_id,
    assignments_to_plan,
    default_acceptance_for_role,
    plan_gates_enabled,
)
from voly.plan.criteria import CriteriaDraft, compile_success_criteria, criteria_to_acceptance
from voly.plan.engine import PlanEngine, create_plan
from voly.plan.loader import load_plan_dict, load_plan_file, plan_summary
from voly.plan.runner import PlanRunResult, PlanRunner
from voly.plan.store import PlanStore
from voly.plan.suggest import PlanSuggestions, suggest_from_cwd, suggest_test_command
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
    "PlanRunResult",
    "PlanRunner",
    "CriteriaDraft",
    "PlanSuggestions",
    "all_passed",
    "assignment_step_id",
    "assignments_to_plan",
    "compile_success_criteria",
    "complete_verification",
    "create_plan",
    "criteria_to_acceptance",
    "default_acceptance_for_role",
    "load_plan_dict",
    "load_plan_file",
    "plan_gates_enabled",
    "plan_summary",
    "run_acceptance",
    "run_check",
    "suggest_from_cwd",
    "suggest_test_command",
    "verify_step",
]
