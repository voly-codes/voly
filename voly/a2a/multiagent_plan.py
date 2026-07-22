"""Plan-gate helpers for local multi-agent runs."""
from __future__ import annotations

import logging

from voly.a2a.assignment import Assignment, apply_env_provider_exclusions

_log = logging.getLogger("voly.a2a.multiagent")


class _PlanGatesMixin:
    """Mixin: plan mirror setup + per-role verify transitions."""

    def finish_step_plan(self, a: Assignment, *, exec_ok: bool, git_before: dict) -> None:
        """After role execution: mark plan step done/verified/failed."""
        from voly.plan.bridge import assignment_step_id, sync_assignment_plan_fields
        from voly.plan.types import FAILED, RUNNING, VERIFIED, VERIFYING
        from voly.plan.verify import VerifyContext, complete_verification, git_porcelain

        if self.plan is None or self.engine is None:
            return
        sid = assignment_step_id(a.idx, a.role)
        step = self.plan.get_step(sid)
        step.output = a.content or ""
        step.files_touched = list(a.files_touched or [])
        if not exec_ok:
            if step.status == RUNNING:
                self.engine.transition(self.plan, sid, FAILED, error=a.error or "role failed")
            sync_assignment_plan_fields(a, self.plan.get_step(sid))
            if self.store is not None:
                self.store.save(self.plan)
            return

        self.engine.mark_execution_finished(
            self.plan, sid, success=True, output=a.content or "",
            files_touched=a.files_touched,
        )
        self.engine.advance_after_done(self.plan, sid)
        step = self.plan.get_step(sid)
        if step.status == VERIFYING:
            git_after = git_porcelain(self.cwd) if self.cwd else {}
            # Tester chat roles rarely touch files — scope pytest using prior
            # executor files_touched (greenfield: only new test_*.py).
            verify_files = list(a.files_touched or [])
            if not verify_files:
                for d in a.depends_on:
                    prior_a = self.done.get(d)
                    if prior_a is None:
                        continue
                    verify_files.extend(prior_a.files_touched or [])
            # de-dupe, drop .voly noise
            seen: set[str] = set()
            scoped: list[str] = []
            for f in verify_files:
                if not f or str(f).startswith(".voly/") or f in seen:
                    continue
                seen.add(f)
                scoped.append(f)
            ctx = VerifyContext(
                cwd=self.cwd or "",
                output=a.content or "",
                files_touched=scoped or list(a.files_touched or []),
                git_before=git_before,
                git_after=git_after,
                command_timeout=float(
                    getattr(self.plan_config, "command_timeout_seconds", 60.0) or 60.0
                ),
            )
            step, _results = complete_verification(
                self.plan, sid, ctx, engine=self.engine
            )
            if step.status == FAILED and self.plan_mode == "shadow":
                argv_hint = ""
                for entry in step.verify_log or []:
                    if entry.get("ok"):
                        continue
                    details = entry.get("details") or {}
                    argv = details.get("argv")
                    if argv:
                        argv_hint = f" argv={argv!r}"
                        break
                _log.warning(
                    "plan step %s verify failed (shadow → force verified): %s%s",
                    sid, step.error, argv_hint,
                )
                step.status = VERIFIED
                self.engine.recompute_plan_status(self.plan)
        step = self.plan.get_step(sid)
        sync_assignment_plan_fields(a, step)
        # Active: failed verify → not ok (dependents skip). Shadow soft-verify → keep ok.
        if step.status == FAILED:
            a.ok = False
            if not a.error:
                a.error = step.error or "plan verification failed"
        elif step.status == VERIFIED and self.plan_mode == "shadow":
            # Soft-opened after verify fail: process still counts as ok for dependents.
            if step.verify_log and not all(bool(e.get("ok")) for e in step.verify_log):
                a.ok = True
        if self.store is not None:
            self.store.save(self.plan)

    def setup_plan_and_modes(self) -> None:
        from voly.a2a.hybrid import hybrid_active, resolve_role_mode
        from voly.plan.bridge import assignments_to_plan, plan_gates_enabled
        from voly.plan.engine import PlanEngine
        from voly.plan.store import PlanStore

        excluded = apply_env_provider_exclusions()
        if excluded:
            _log.info(
                "[PIPELINE:A2A] pre-excluded providers before first chat: %s",
                ",".join(excluded),
            )

        has_cwd = bool((self.cwd or "").strip())
        hybrid_on = hybrid_active(
            hybrid_code_gen=self.hybrid_code_gen,
            has_cwd=has_cwd,
            hybrid_require_cwd=self.hybrid_require_cwd,
        )
        if self.hybrid_code_gen and not has_cwd:
            _log.warning(
                "multiagent hybrid: no cwd — all roles stay chat (hybrid_skipped_no_cwd)"
            )

        _log.info(
            "[PIPELINE:A2A] run_local roles=%s cwd=%s hybrid=%s task_id=%s",
            [a.role for a in self.assignments],
            self.cwd or "(none)",
            hybrid_on,
            self.task_id or "",
        )

        # Pre-resolve hybrid modes so the plan mirror matches execution.
        for a in self.assignments:
            mode, reason = resolve_role_mode(
                a.role,
                hybrid_enabled=hybrid_on,
                requires_code_gen=self.requires_code_gen,
                lead_execution=a.execution or None,
                executor_roles=self.executor_roles,
            )
            # Executors never run without an explicit project cwd, even when
            # hybrid_require_cwd is off — never invent a project path.
            if mode == "executor" and not has_cwd:
                mode, reason = "chat", "no_cwd"
            a.mode = mode
            a.mode_reason = reason
            self.role_modes[a.idx] = mode

        self.gates_on = plan_gates_enabled(self.plan_config)
        if self.gates_on:
            self.engine = PlanEngine()
            self.plan_mode = (
                getattr(self.plan_config, "mode", "shadow") or "shadow"
            ).lower()
            plan_id = (
                f"a2a-{self.task_id}"
                if self.task_id
                else f"a2a-{abs(hash(self.task)) % 10**10}"
            )
            self.plan = assignments_to_plan(
                self.task,
                self.assignments,
                plan_id=plan_id,
                task_id=self.task_id,
                cwd=self.cwd or "",
                plan_cfg=self.plan_config,
                role_modes=self.role_modes,
            )
            try:
                self.engine.validate(self.plan)
            except Exception as exc:  # noqa: BLE001
                _log.warning("plan gates disabled — invalid plan: %s", exc)
                self.plan = None
                self.engine = None
                self.gates_on = False
            else:
                self.store = self.plan_store or PlanStore(
                    getattr(self.plan_config, "store_dir", None) or ".voly/plans"
                )
                self.store.save(self.plan)
                _log.info(
                    "multiagent plan gates ON mode=%s plan_id=%s steps=%d",
                    self.plan_mode, self.plan.plan_id, len(self.plan.steps),
                )

        if self.tracker is not None and self.task_id:
            self.tracker.start(
                self.task_id,
                self.task,
                [a.role for a in self.assignments],
                plan_id=self.plan.plan_id if self.plan else "",
                graph_nodes=[self.graph_node(a) for a in self.assignments],
                graph_edges=[
                    {
                        "from": f"agent-{dependency}",
                        "to": f"agent-{a.idx}",
                        "status": "pending",
                    }
                    for a in self.assignments
                    for dependency in a.depends_on
                ],
            )
