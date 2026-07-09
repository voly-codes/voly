"""Plan state-machine types (Rung B, PR1).

A plan is a DAG of steps with enforced statuses. Transitions are validated by
``voly.plan.engine.PlanEngine`` — agents and callers must not invent statuses.

See ``docs/proposals/plan-gate-verification.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Step statuses ────────────────────────────────────────────────────────────

PENDING = "pending"
RUNNING = "running"
DONE = "done"
VERIFYING = "verifying"
VERIFIED = "verified"
FAILED = "failed"
SKIPPED = "skipped"

STEP_STATUSES = frozenset({
    PENDING, RUNNING, DONE, VERIFYING, VERIFIED, FAILED, SKIPPED,
})

# (from, to) pairs allowed by the engine. Gate logic (deps) is separate.
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    (PENDING, RUNNING),
    (PENDING, SKIPPED),
    (RUNNING, DONE),
    (RUNNING, FAILED),
    (DONE, VERIFYING),
    (DONE, VERIFIED),       # empty acceptance → auto-pass
    (VERIFYING, VERIFIED),
    (VERIFYING, FAILED),
    (FAILED, RUNNING),      # retry
    (FAILED, SKIPPED),
    (FAILED, PENDING),      # reset for re-queue
})

# ── Plan-level statuses ──────────────────────────────────────────────────────

PLAN_PENDING = "pending"
PLAN_RUNNING = "running"
PLAN_COMPLETED = "completed"
PLAN_FAILED = "failed"
PLAN_ABORTED = "aborted"

PLAN_STATUSES = frozenset({
    PLAN_PENDING, PLAN_RUNNING, PLAN_COMPLETED, PLAN_FAILED, PLAN_ABORTED,
})

# Step modes (execution path; wiring in later PRs)
MODE_CHAT = "chat"
MODE_EXECUTOR = "executor"
STEP_MODES = frozenset({MODE_CHAT, MODE_EXECUTOR})

SCHEMA_VERSION = 1


class PlanError(Exception):
    """Base error for plan FSM / store."""


class IllegalTransition(PlanError):
    """Raised when a step status change is not in LEGAL_TRANSITIONS or fails the gate."""

    def __init__(
        self,
        step_id: str,
        from_status: str,
        to_status: str,
        reason: str = "",
    ) -> None:
        self.step_id = step_id
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        msg = f"illegal transition step={step_id!r}: {from_status!r} → {to_status!r}"
        if reason:
            msg = f"{msg} ({reason})"
        super().__init__(msg)


class PlanValidationError(PlanError):
    """Raised when a plan document is structurally invalid."""


@dataclass
class AcceptanceCheck:
    """Declared check for a step (executed in PR2; stored as data in PR1)."""

    type: str
    paths: list[str] = field(default_factory=list)
    run: str = ""
    expect_exit: int = 0
    pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.paths:
            d["paths"] = list(self.paths)
        if self.run:
            d["run"] = self.run
            d["expect_exit"] = self.expect_exit
        if self.pattern:
            d["pattern"] = self.pattern
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceCheck:
        if not isinstance(data, dict) or not data.get("type"):
            raise PlanValidationError(f"invalid acceptance check: {data!r}")
        return cls(
            type=str(data["type"]),
            paths=[str(p) for p in (data.get("paths") or [])],
            run=str(data.get("run") or ""),
            expect_exit=int(data.get("expect_exit", 0)),
            pattern=str(data.get("pattern") or ""),
        )


@dataclass
class PlanStep:
    id: str
    role: str = "developer"
    mode: str = MODE_CHAT
    status: str = PENDING
    depends_on: list[str] = field(default_factory=list)
    acceptance: list[AcceptanceCheck] = field(default_factory=list)
    # Instruction for this step (YAML/CLI). Empty → fall back to plan.task.
    task: str = ""
    # Filled by runners later; kept here for persistence shape stability.
    error: str = ""
    output: str = ""
    verify_log: list[dict[str, Any]] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    executor: str = ""
    model: str = ""
    provider: str = ""
    tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "mode": self.mode,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "acceptance": [a.to_dict() for a in self.acceptance],
            "task": self.task,
            "error": self.error,
            "output": self.output,
            "verify_log": list(self.verify_log),
            "files_touched": list(self.files_touched),
            "executor": self.executor,
            "model": self.model,
            "provider": self.provider,
            "tier": self.tier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        if not isinstance(data, dict) or not data.get("id"):
            raise PlanValidationError(f"invalid plan step: {data!r}")
        acceptance_raw = data.get("acceptance") or []
        if not isinstance(acceptance_raw, list):
            raise PlanValidationError(f"step {data.get('id')!r}: acceptance must be a list")
        # Accept legacy/alternate keys for step instruction.
        task = data.get("task") or data.get("description") or data.get("prompt") or ""
        return cls(
            id=str(data["id"]),
            role=str(data.get("role") or "developer"),
            mode=str(data.get("mode") or MODE_CHAT),
            status=str(data.get("status") or PENDING),
            depends_on=[str(x) for x in (data.get("depends_on") or [])],
            acceptance=[AcceptanceCheck.from_dict(a) for a in acceptance_raw],
            task=str(task),
            error=str(data.get("error") or ""),
            output=str(data.get("output") or ""),
            verify_log=list(data.get("verify_log") or []),
            files_touched=[str(p) for p in (data.get("files_touched") or [])],
            executor=str(data.get("executor") or ""),
            model=str(data.get("model") or ""),
            provider=str(data.get("provider") or ""),
            tier=str(data.get("tier") or ""),
        )


@dataclass
class Plan:
    plan_id: str
    task_id: str = ""
    cwd: str = ""
    status: str = PLAN_PENDING
    schema_version: int = SCHEMA_VERSION
    steps: list[PlanStep] = field(default_factory=list)
    task: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    error: str = ""

    def step_map(self) -> dict[str, PlanStep]:
        return {s.id: s for s in self.steps}

    def get_step(self, step_id: str) -> PlanStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise PlanValidationError(f"unknown step id: {step_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "cwd": self.cwd,
            "status": self.status,
            "task": self.task,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        if not isinstance(data, dict) or not data.get("plan_id"):
            raise PlanValidationError(f"invalid plan: missing plan_id in {type(data).__name__}")
        steps_raw = data.get("steps") or []
        if not isinstance(steps_raw, list):
            raise PlanValidationError("plan.steps must be a list")
        return cls(
            plan_id=str(data["plan_id"]),
            task_id=str(data.get("task_id") or ""),
            cwd=str(data.get("cwd") or ""),
            status=str(data.get("status") or PLAN_PENDING),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
            steps=[PlanStep.from_dict(s) for s in steps_raw],
            task=str(data.get("task") or ""),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
            error=str(data.get("error") or ""),
        )


def is_legal_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in LEGAL_TRANSITIONS
