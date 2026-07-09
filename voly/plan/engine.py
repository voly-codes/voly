"""Plan state machine: topo order, dep gate, legal transitions (PR1).

No agent I/O and no verifiers here — pure structure + status rules.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from voly.plan.types import (
    DONE,
    FAILED,
    PENDING,
    PLAN_ABORTED,
    PLAN_COMPLETED,
    PLAN_FAILED,
    PLAN_PENDING,
    PLAN_RUNNING,
    PLAN_STATUSES,
    RUNNING,
    SKIPPED,
    STEP_MODES,
    STEP_STATUSES,
    VERIFIED,
    VERIFYING,
    IllegalTransition,
    Plan,
    PlanStep,
    PlanValidationError,
    is_legal_transition,
)


class PlanEngine:
    """Validates plans and enforces step-status transitions + dependency gates."""

    # ── Structure ────────────────────────────────────────────────────────────

    def validate(self, plan: Plan) -> None:
        """Raise PlanValidationError if the plan document is invalid."""
        if not plan.plan_id or not str(plan.plan_id).strip():
            raise PlanValidationError("plan_id is required")
        if plan.status not in PLAN_STATUSES:
            raise PlanValidationError(f"invalid plan status: {plan.status!r}")
        if not plan.steps:
            raise PlanValidationError("plan must have at least one step")

        seen: set[str] = set()
        for step in plan.steps:
            self._validate_step(step, seen)
            seen.add(step.id)

        ids = seen
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in ids:
                    raise PlanValidationError(
                        f"step {step.id!r} depends on unknown step {dep!r}"
                    )
                if dep == step.id:
                    raise PlanValidationError(f"step {step.id!r} depends on itself")

        # Cycle detection via topo_order
        try:
            self.topo_order(plan)
        except PlanValidationError:
            raise

    def _validate_step(self, step: PlanStep, seen: set[str]) -> None:
        if not step.id or not str(step.id).strip():
            raise PlanValidationError("step id is required")
        if step.id in seen:
            raise PlanValidationError(f"duplicate step id: {step.id!r}")
        if step.status not in STEP_STATUSES:
            raise PlanValidationError(
                f"step {step.id!r}: invalid status {step.status!r}"
            )
        if step.mode not in STEP_MODES:
            raise PlanValidationError(
                f"step {step.id!r}: invalid mode {step.mode!r}"
            )

    def topo_order(self, plan: Plan) -> list[str]:
        """Return step ids in dependency order (Kahn). Raises on cycles."""
        ids = [s.id for s in plan.steps]
        id_set = set(ids)
        indegree: dict[str, int] = {i: 0 for i in ids}
        children: dict[str, list[str]] = {i: [] for i in ids}

        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in id_set:
                    raise PlanValidationError(
                        f"step {step.id!r} depends on unknown step {dep!r}"
                    )
                indegree[step.id] += 1
                children[dep].append(step.id)

        queue: deque[str] = deque(i for i in ids if indegree[i] == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for child in children[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if len(order) != len(ids):
            stuck = [i for i, d in indegree.items() if d > 0]
            raise PlanValidationError(f"plan has a dependency cycle involving: {stuck}")
        return order

    # ── Gate ─────────────────────────────────────────────────────────────────

    def unmet_deps(self, plan: Plan, step_id: str) -> list[str]:
        """Dependency step ids that are not yet ``verified``."""
        step = plan.get_step(step_id)
        smap = plan.step_map()
        unmet: list[str] = []
        for dep in step.depends_on:
            dep_step = smap.get(dep)
            if dep_step is None or dep_step.status != VERIFIED:
                unmet.append(dep)
        return unmet

    def can_start(self, plan: Plan, step_id: str) -> bool:
        """True if step may enter ``running`` (status pending/failed + deps verified)."""
        step = plan.get_step(step_id)
        if step.status not in (PENDING, FAILED):
            return False
        return not self.unmet_deps(plan, step_id)

    def runnable_steps(self, plan: Plan) -> list[str]:
        """Step ids that currently pass ``can_start`` (topo order)."""
        return [sid for sid in self.topo_order(plan) if self.can_start(plan, sid)]

    def is_terminal_step(self, status: str) -> bool:
        return status in (VERIFIED, SKIPPED)

    def all_steps_terminal(self, plan: Plan) -> bool:
        return all(self.is_terminal_step(s.status) for s in plan.steps)

    def any_step_failed(self, plan: Plan) -> bool:
        return any(s.status == FAILED for s in plan.steps)

    # ── Transitions ──────────────────────────────────────────────────────────

    def transition(
        self,
        plan: Plan,
        step_id: str,
        to_status: str,
        *,
        error: str = "",
        allow_skip: bool = False,
        force: bool = False,
    ) -> PlanStep:
        """Apply a legal status change. Mutates ``plan`` in place; returns the step.

        Gate: ``→ running`` requires all depends_on to be ``verified`` (unless
        ``force=True``, reserved for recovery tooling).

        ``→ skipped`` requires ``allow_skip=True`` (policy; agents cannot skip freely).
        """
        step = plan.get_step(step_id)
        from_status = step.status

        if to_status not in STEP_STATUSES:
            raise IllegalTransition(step_id, from_status, to_status, "unknown target status")

        if to_status == SKIPPED and not allow_skip and not force:
            raise IllegalTransition(
                step_id, from_status, to_status, "skip not allowed (allow_skip=False)"
            )

        if not force and not is_legal_transition(from_status, to_status):
            raise IllegalTransition(step_id, from_status, to_status)

        if to_status == RUNNING and not force:
            unmet = self.unmet_deps(plan, step_id)
            if unmet:
                raise IllegalTransition(
                    step_id,
                    from_status,
                    to_status,
                    f"unmet dependencies (not verified): {unmet}",
                )
            if from_status not in (PENDING, FAILED):
                # covered by LEGAL_TRANSITIONS, but keep explicit message
                raise IllegalTransition(
                    step_id, from_status, to_status, "only pending/failed may start"
                )

        if to_status == VERIFIED and from_status == DONE and step.acceptance and not force:
            # Empty acceptance may auto-verify; non-empty must go through verifying.
            raise IllegalTransition(
                step_id,
                from_status,
                to_status,
                "step has acceptance checks; use done → verifying first",
            )

        if to_status == VERIFYING and from_status == DONE and not step.acceptance and not force:
            raise IllegalTransition(
                step_id,
                from_status,
                to_status,
                "no acceptance checks; use done → verified",
            )

        step.status = to_status
        if to_status == FAILED:
            step.error = (error or step.error or "failed")[:2000]
        elif error:
            step.error = error[:2000]
        elif to_status in (RUNNING, PENDING, VERIFIED, DONE, SKIPPED):
            # Clear stale failure text when the step progresses or is reset.
            step.error = ""

        self.recompute_plan_status(plan)
        return step

    def mark_execution_finished(
        self,
        plan: Plan,
        step_id: str,
        *,
        success: bool,
        error: str = "",
        output: str = "",
        files_touched: Iterable[str] | None = None,
    ) -> PlanStep:
        """Helper: running → done (success) or running → failed.

        Does not run verifiers (PR2). For success with empty acceptance, callers
        may then ``transition(..., VERIFIED)``; with acceptance, ``VERIFYING``.
        """
        step = plan.get_step(step_id)
        if output:
            step.output = output[:50_000]
        if files_touched is not None:
            step.files_touched = [str(p) for p in files_touched]
        if success:
            return self.transition(plan, step_id, DONE)
        return self.transition(plan, step_id, FAILED, error=error or "execution failed")

    def advance_after_done(self, plan: Plan, step_id: str) -> PlanStep:
        """From ``done``: go to ``verifying`` if acceptance else ``verified``."""
        step = plan.get_step(step_id)
        if step.status != DONE:
            raise IllegalTransition(
                step_id, step.status, VERIFYING if step.acceptance else VERIFIED,
                "advance_after_done requires status=done",
            )
        if step.acceptance:
            return self.transition(plan, step_id, VERIFYING)
        return self.transition(plan, step_id, VERIFIED)

    def recompute_plan_status(self, plan: Plan) -> str:
        """Update plan.status from step statuses. Returns new status.

        Does not override PLAN_ABORTED (set only by abort()).
        """
        if plan.status == PLAN_ABORTED:
            return plan.status

        statuses = [s.status for s in plan.steps]
        if not statuses:
            plan.status = PLAN_PENDING
            return plan.status

        if all(s in (VERIFIED, SKIPPED) for s in statuses):
            # completed only if at least one verified (all-skipped is failed-ish)
            if any(s == VERIFIED for s in statuses):
                plan.status = PLAN_COMPLETED
            else:
                plan.status = PLAN_FAILED
            return plan.status

        if any(s in (RUNNING, DONE, VERIFYING) for s in statuses):
            plan.status = PLAN_RUNNING
            return plan.status

        if any(s == FAILED for s in statuses) and not any(
            s in (RUNNING, DONE, VERIFYING, PENDING) for s in statuses
        ):
            # all remaining are failed/verified/skipped and at least one failed
            # with no pending work left
            if not any(s == PENDING for s in statuses):
                plan.status = PLAN_FAILED
                return plan.status

        if any(s == FAILED for s in statuses):
            # failed step but other work still pending — still running/failed hybrid
            plan.status = PLAN_RUNNING
            return plan.status

        if all(s == PENDING for s in statuses):
            plan.status = PLAN_PENDING
            return plan.status

        plan.status = PLAN_RUNNING
        return plan.status

    def abort(self, plan: Plan, error: str = "aborted") -> None:
        plan.status = PLAN_ABORTED
        plan.error = (error or "aborted")[:2000]


def create_plan(
    plan_id: str,
    steps: list[PlanStep],
    *,
    task_id: str = "",
    cwd: str = "",
    task: str = "",
    validate: bool = True,
) -> Plan:
    """Build a Plan and optionally validate structure."""
    plan = Plan(
        plan_id=plan_id,
        task_id=task_id,
        cwd=cwd,
        task=task,
        steps=list(steps),
        status=PLAN_PENDING,
    )
    engine = PlanEngine()
    if validate:
        engine.validate(plan)
        engine.recompute_plan_status(plan)
    return plan
