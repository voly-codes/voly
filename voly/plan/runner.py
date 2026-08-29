"""Execute a Plan with gates + acceptance checks (PR3).

Chat steps → AIGateway (injectable); executor steps → AgentRunner (injectable).
Modes: active (hard gate on verify fail) | shadow (log fail, still open gate).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from voly.config import PlanConfig, VOLYConfig
from voly.plan.engine import PlanEngine
from voly.plan.loader import plan_summary
from voly.plan.store import PlanStore
from voly.plan.types import (
    DONE,
    FAILED,
    MODE_BUSINESS,
    MODE_CHAT,
    MODE_EXECUTOR,
    PENDING,
    PLAN_ABORTED,
    PLAN_COMPLETED,
    PLAN_FAILED,
    PLAN_RUNNING,
    RUNNING,
    SKIPPED,
    VERIFIED,
    VERIFYING,
    Plan,
    PlanStep,
)
from voly.plan.verify import (
    VerifyContext,
    all_passed,
    complete_verification,
    git_porcelain,
    verify_step,
)
from voly.plan.verify_types import CHECK_ACTION_SUCCEEDED, CHECK_HUMAN_REVIEW
from voly.telemetry import TaskEvent, emit_event_from_config, new_task_id

_log = logging.getLogger("voly.plan.runner")

# Acceptance types resolved out-of-band (human_review by an explicit decision
# API call, action_succeeded by a business Executor result) — see
# voly/plan/verify_checks.py. The synchronous dispatch these run through
# always fails them closed, and shadow mode's soft-open must not apply to a
# human/action gate the way it does to a quality/regression check — so
# PlanRunner special-cases them: park the step in `verifying` rather than
# transitioning it to `failed`, and never force it `verified`.
_EXTERNALLY_RESOLVED_CHECK_TYPES = frozenset({CHECK_HUMAN_REVIEW, CHECK_ACTION_SUCCEEDED})

# Optional injectables for tests / alternate runtimes.
ChatFn = Callable[[PlanStep, Plan, str], tuple[bool, str, str]]
# Returns (success, output, error)
ExecutorFn = Callable[[PlanStep, Plan, str], tuple[bool, str, str, list[str]]]
# Returns (success, output, error, files_touched)

_DEPENDENCY_CONTEXT_CHARS = 4000


def _with_dependency_context(plan: Plan, step: PlanStep, instruction: str) -> str:
    """Prepend each verified dependency's output as context.

    A step's own ``task``/``instruction`` never references upstream results —
    PlanStep carries no template/interpolation syntax — so without this, a
    dependent step (e.g. a "review" node depending on "research") would run
    blind to what its dependency actually produced. Only ``depends_on`` is
    used, not the full step graph, so unrelated sibling output never leaks in.
    """
    if not step.depends_on:
        return instruction
    blocks = []
    for dep_id in step.depends_on:
        try:
            dep = plan.get_step(dep_id)
        except Exception:  # noqa: BLE001
            continue
        if not dep.output:
            continue
        blocks.append(f"### {dep_id}\n{dep.output[:_DEPENDENCY_CONTEXT_CHARS]}")
    if not blocks:
        return instruction
    context = "\n\n".join(blocks)
    return f"Context from completed steps:\n\n{context}\n\n---\n\n{instruction}"


@dataclass
class PlanRunResult:
    plan: Plan
    success: bool
    task_id: str = ""
    duration_ms: float = 0.0
    error: str = ""
    summary: dict[str, Any] = field(default_factory=dict)


class PlanRunner:
    """Run plans step-by-step with dependency gates and verification."""

    def __init__(
        self,
        config: VOLYConfig,
        *,
        store: PlanStore | None = None,
        engine: PlanEngine | None = None,
        chat_fn: ChatFn | None = None,
        executor_fn: ExecutorFn | None = None,
        emit_event: bool = True,
    ) -> None:
        self.config = config
        self.plan_cfg: PlanConfig = getattr(config, "plan", None) or PlanConfig()
        self.store = store or PlanStore(self.plan_cfg.store_dir)
        self.engine = engine or PlanEngine()
        self.chat_fn = chat_fn
        self.executor_fn = executor_fn
        self.emit_event = emit_event

    def run(
        self,
        plan: Plan,
        *,
        mode: str | None = None,
        cwd: str | None = None,
    ) -> PlanRunResult:
        """Execute all steps until completed, failed, or aborted."""
        t0 = time.monotonic()
        run_mode = (mode or self.plan_cfg.mode or "shadow").lower()
        if run_mode == "off":
            run_mode = "shadow"

        if cwd:
            plan.cwd = cwd
        elif not plan.cwd:
            plan.cwd = getattr(self.config, "default_cwd", "") or ""

        if not plan.task_id:
            plan.task_id = new_task_id()

        self.engine.validate(plan)
        plan.status = PLAN_RUNNING
        self.store.save(plan)

        max_retries = max(0, int(self.plan_cfg.max_step_retries))
        retries: dict[str, int] = {s.id: 0 for s in plan.steps}
        on_fail = (self.plan_cfg.default_on_verify_fail or "stop").lower()

        try:
            while True:
                if plan.status == PLAN_ABORTED:
                    break

                runnable = self.engine.runnable_steps(plan)
                if not runnable:
                    # Done, blocked on failed deps, paused on an in-flight
                    # step, or stuck.
                    if self.engine.all_steps_terminal(plan):
                        self.engine.recompute_plan_status(plan)
                        break
                    if any(s.status in (RUNNING, DONE, VERIFYING) for s in plan.steps):
                        # A step is still in flight — most notably one parked
                        # in `verifying` awaiting an out-of-band decision
                        # (human_review/action_succeeded, see _verify()). Not
                        # a failure: nothing new can start right now, but a
                        # later resume() continues once that step resolves.
                        self.engine.recompute_plan_status(plan)
                        break
                    # Pending steps with failed deps → plan failed
                    if any(s.status == PENDING for s in plan.steps):
                        plan.status = PLAN_FAILED
                        plan.error = plan.error or "blocked: unmet verified dependencies"
                    else:
                        self.engine.recompute_plan_status(plan)
                    break

                # Sequential in topo order (first runnable). Parallel later.
                step_id = runnable[0]
                ok = self._run_one_step(plan, step_id, run_mode=run_mode)
                self.store.save(plan)

                if ok:
                    continue

                step = plan.get_step(step_id)
                if step.status != FAILED:
                    continue

                # Retry policy
                if on_fail == "retry" and retries[step_id] < max_retries:
                    retries[step_id] += 1
                    _log.info(
                        "plan %s step %s retry %d/%d",
                        plan.plan_id, step_id, retries[step_id], max_retries,
                    )
                    self.engine.transition(plan, step_id, RUNNING)
                    # fall through: next loop iteration will not re-pick if running
                    # Actually status is RUNNING but can_start only pending/failed —
                    # so we need to re-execute immediately without waiting for runnable.
                    ok2 = self._run_one_step(
                        plan, step_id, run_mode=run_mode, already_running=True
                    )
                    self.store.save(plan)
                    if ok2:
                        continue

                if on_fail == "continue" or run_mode == "shadow":
                    # Soft: skip remaining enforcement for this branch — open gate
                    # only if we force-verify; for execution fail, leave failed.
                    if step.status == FAILED and step.verify_log:
                        # verify failed under shadow → already handled in _verify
                        pass
                    if on_fail == "continue" and step.status == FAILED:
                        # Allow dependents? only if we skip or force verify.
                        # Policy continue: mark skipped so topo can proceed? No —
                        # dependents need verified. Soft-open: force verified.
                        self.engine.transition(
                            plan, step_id, VERIFIED, force=True
                        )
                        step.error = (step.error or "continue after fail")[:2000]
                        self.store.save(plan)
                        continue

                # stop (default active)
                plan.status = PLAN_FAILED
                plan.error = step.error or f"step {step_id} failed"
                break
        except Exception as exc:  # noqa: BLE001
            plan.status = PLAN_FAILED
            plan.error = str(exc)[:2000]
            _log.exception("plan %s crashed: %s", plan.plan_id, exc)

        self.engine.recompute_plan_status(plan)
        if plan.status not in (PLAN_COMPLETED, PLAN_FAILED, PLAN_ABORTED):
            if self.engine.all_steps_terminal(plan) and any(
                s.status == VERIFIED for s in plan.steps
            ):
                plan.status = PLAN_COMPLETED
            elif any(s.status == FAILED for s in plan.steps):
                plan.status = PLAN_FAILED

        self.store.save(plan)
        duration_ms = (time.monotonic() - t0) * 1000
        summary = plan_summary(plan)
        success = plan.status == PLAN_COMPLETED

        if self.emit_event:
            self._emit_telemetry(plan, summary, duration_ms, success)

        return PlanRunResult(
            plan=plan,
            success=success,
            task_id=plan.task_id,
            duration_ms=duration_ms,
            error=plan.error,
            summary=summary,
        )

    def resume(self, plan_id: str, *, mode: str | None = None) -> PlanRunResult:
        """Reload a persisted Plan and continue running it.

        No special "paused" state to restore: run() always recomputes
        runnable steps from whatever status is currently persisted. This
        exists so a step parked in `verifying` by an externally-resolved
        acceptance check (human_review/action_succeeded — see _verify()) has
        a documented way back in once voly.plan.approval.decide() (or a
        business Executor result) has moved it to verified/failed.
        """
        plan = self.store.load(plan_id)
        if plan is None:
            raise FileNotFoundError(plan_id)
        return self.run(plan, mode=mode, cwd=plan.cwd or None)

    def _run_one_step(
        self,
        plan: Plan,
        step_id: str,
        *,
        run_mode: str,
        already_running: bool = False,
    ) -> bool:
        """Execute + verify one step. Returns True if step ends verified/skipped."""
        step = plan.get_step(step_id)
        if not already_running:
            self.engine.transition(plan, step_id, RUNNING)
            self.store.save(plan)

        instruction = (step.task or plan.task or "").strip()
        if not instruction:
            instruction = f"Perform role={step.role} for plan {plan.plan_id}"
        instruction = _with_dependency_context(plan, step, instruction)

        git_before = git_porcelain(plan.cwd) if plan.cwd else {}
        mode = (step.mode or MODE_CHAT).lower()

        if mode == MODE_BUSINESS:
            # Business Plans are driven exclusively by
            # voly.decisions.DecisionService (human approval, then a real
            # business Executor). Running one through this generic
            # chat/executor loop would either prompt a chat model with a
            # business action's task text or skip the mandatory human
            # checkpoint — fail closed instead.
            self.engine.transition(
                plan, step_id, FAILED,
                error="mode=business steps must run via DecisionService, not PlanRunner",
            )
            return False

        try:
            if mode == MODE_EXECUTOR:
                success, output, error, files = self._exec_executor(step, plan, instruction)
            else:
                success, output, error = self._exec_chat(step, plan, instruction)
                files = []
        except Exception as exc:  # noqa: BLE001
            success, output, error, files = False, "", str(exc), []

        step.output = (output or "")[:50_000]
        if files:
            step.files_touched = list(files)

        git_after = git_porcelain(plan.cwd) if plan.cwd else {}
        if not step.files_touched and git_before is not None:
            from voly.plan.verify import changed_paths

            step.files_touched = sorted(changed_paths(git_before, git_after))

        if not success:
            self.engine.transition(
                plan, step_id, FAILED, error=error or "step execution failed"
            )
            return False

        self.engine.mark_execution_finished(
            plan,
            step_id,
            success=True,
            output=output or "",
            files_touched=step.files_touched,
        )

        # done → verifying | verified
        self.engine.advance_after_done(plan, step_id)
        step = plan.get_step(step_id)

        if step.status == VERIFIED:
            return True

        if step.status == VERIFYING:
            return self._verify(
                plan,
                step_id,
                run_mode=run_mode,
                git_before=git_before,
                git_after=git_after,
            )

        return step.status in (VERIFIED, SKIPPED)

    def _verify(
        self,
        plan: Plan,
        step_id: str,
        *,
        run_mode: str,
        git_before: dict[str, str],
        git_after: dict[str, str],
    ) -> bool:
        step = plan.get_step(step_id)
        ctx = VerifyContext(
            cwd=plan.cwd,
            output=step.output,
            files_touched=list(step.files_touched),
            git_before=git_before,
            git_after=git_after,
            command_timeout=float(self.plan_cfg.command_timeout_seconds),
        )

        if any(c.type in _EXTERNALLY_RESOLVED_CHECK_TYPES for c in step.acceptance):
            # Populate verify_log for visibility but do not transition: an
            # external decision (voly.plan.approval.decide / a business
            # Executor result) owns this step's verifying → verified|failed
            # move. Leaving it in `verifying` lets run() stop cleanly — a
            # later resume() (same Plan, reloaded from the store) picks back
            # up once that decision lands.
            verify_step(plan, step_id, ctx)
            return False

        step, results = complete_verification(
            plan, step_id, ctx, engine=self.engine
        )

        if all_passed(results) or not results:
            return step.status == VERIFIED

        # Verification failed
        if run_mode == "shadow":
            # Soft gate: keep verify_log + error, force verified so dependents can run.
            _log.warning(
                "plan %s step %s verify failed (shadow → force verified): %s",
                plan.plan_id, step_id, step.error,
            )
            step.status = VERIFIED
            self.engine.recompute_plan_status(plan)
            return True

        return False

    def _exec_chat(
        self, step: PlanStep, plan: Plan, instruction: str
    ) -> tuple[bool, str, str]:
        if self.chat_fn is not None:
            return self.chat_fn(step, plan, instruction)

        from voly.ai_gateway import gateway_from_config
        from voly.telemetry import _estimate_cost

        gateway = gateway_from_config(self.config)
        system = (
            f"You are the '{step.role}' agent in a multi-step VOLY plan "
            f"(step id={step.id}). Complete only this step. Be concise."
        )
        model_cfg = self.config.get_model_config(step.model or None)
        model = step.model or model_cfg.model or self.config.default_model
        provider = step.provider or model_cfg.provider or "anthropic"
        t0 = time.monotonic()
        resp = gateway.chat(
            messages=[{"role": "user", "content": instruction}],
            model=model,
            provider_name=provider,
            system=system,
            agent=step.role or "plan",
            max_tokens=4096,
            temperature=0.0,
        )
        step.duration_ms = (time.monotonic() - t0) * 1000
        usage = resp.get("usage") if isinstance(resp, dict) else getattr(resp, "usage", None)
        if usage:
            resolved_model = str(
                resp.get("model") if isinstance(resp, dict) else getattr(resp, "model", "")
            ) or model
            in_tok = int(usage.get("input_tokens", 0)) if isinstance(usage, dict) else 0
            out_tok = int(usage.get("output_tokens", 0)) if isinstance(usage, dict) else 0
            step.cost_usd = _estimate_cost(resolved_model, in_tok, out_tok)
        if isinstance(resp, dict):
            if resp.get("error"):
                return False, "", str(resp["error"])
            content = resp.get("content") or ""
            return True, str(content), ""
        # GatewayResponse-like
        err = getattr(resp, "error", None)
        if err:
            return False, "", str(err)
        content = getattr(resp, "content", "") or ""
        return True, str(content), ""

    def _exec_executor(
        self, step: PlanStep, plan: Plan, instruction: str
    ) -> tuple[bool, str, str, list[str]]:
        if self.executor_fn is not None:
            return self.executor_fn(step, plan, instruction)

        from voly.runner.agent_runner import AgentRunner

        runner = AgentRunner(self.config)
        agent = step.executor or step.role or self.plan_cfg.executor_default
        result = runner.run(
            instruction,
            agent,
            cwd=plan.cwd or "",
            max_turns=int(self.plan_cfg.max_turns),
            timeout=int(self.plan_cfg.step_timeout_seconds),
            model=step.model or "",
            emit_event=False,
        )
        er = result.result
        step.cost_usd = er.cost_usd
        step.duration_ms = er.duration_ms
        files: list[str] = []
        if er.report is not None:
            files = list(
                (er.report.files_created or [])
                + (er.report.files_changed or [])
            )
        if er.success:
            return True, er.output or "", "", files
        return False, er.output or "", er.error or "executor failed", files

    def _emit_telemetry(
        self,
        plan: Plan,
        summary: dict[str, Any],
        duration_ms: float,
        success: bool,
    ) -> None:
        try:
            stage_log = [
                {
                    "stage": f"plan:{s['id']}",
                    "status": s["status"],
                    "elapsed_ms": 0,
                }
                for s in summary.get("steps", [])
            ]
            # Nested plan blob in result text (avoid TaskEvent schema bump).
            import json

            ev = TaskEvent(
                task_id=plan.task_id or new_task_id(),
                agent="plan",
                status="completed" if success else "failed",
                workflow=f"plan:{plan.plan_id}",
                duration_ms=duration_ms,
                task_prompt=(plan.task or plan.plan_id)[:2000],
                result=json.dumps(summary, ensure_ascii=False)[:8000],
                stage_log=stage_log,
                error=plan.error or None,
                executor="plan-runner",
            )
            emit_event_from_config(ev, self.config)
        except Exception as exc:  # noqa: BLE001
            _log.debug("plan telemetry emit failed: %s", exc)
