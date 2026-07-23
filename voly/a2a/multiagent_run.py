"""Local multi-agent ``run_local`` orchestration (wave scheduling).

Public entry remains ``voly.a2a.multiagent.run_local``.
Layout:
- ``multiagent_plan.py``  — plan gates setup / finish_step_plan
- ``multiagent_roles.py`` — prepare / executor / chat
- ``multiagent_run.py``   — ``_LocalRun`` + wave loop
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from voly.a2a.assignment import Assignment, evaluate_multiagent_outcome
from voly.a2a.hybrid import resolve_role_executor
from voly.a2a.multiagent_plan import _PlanGatesMixin
from voly.a2a.multiagent_roles import _RoleExecMixin
from voly.a2a.waves import build_waves

_log = logging.getLogger("voly.a2a.multiagent")


@dataclass
class _LocalRun(_PlanGatesMixin, _RoleExecMixin):
    """Shared mutable state for one ``run_local`` invocation."""

    task: str
    assignments: list[Assignment]
    gateway: Any
    skill_matcher: Callable[[str, str], list[Any]] | None
    max_tokens: int
    architect_max_tokens: int
    memory: Any
    headroom: Any
    temperature: float
    task_id: str
    tracker: Any
    cwd: str
    hybrid_code_gen: bool
    hybrid_require_cwd: bool
    requires_code_gen: bool
    executor_default: str
    executor_roles: list[str] | None
    executor_runner: Callable[..., Any] | None
    skip_dependents_on_failure: bool
    parallel_waves: bool
    max_parallel_roles: int
    plan_config: Any
    plan_store: Any
    capability_worker_url: str = ""
    capability_profiles_dir: str = ".voly/capability/profiles"
    capability_worker_timeout_s: float = 3.0

    role_modes: dict[int, str] = field(default_factory=dict)
    plan: Any = None
    engine: Any = None
    store: Any = None
    plan_mode: str = "off"
    gates_on: bool = False
    done: dict[int, Assignment] = field(default_factory=dict)
    degraded_notes: dict[int, list[str]] = field(default_factory=dict)

    def step_snapshot(self) -> list[dict[str, Any]]:
        if self.plan is None:
            return []
        return [{"id": s.id, "status": s.status, "role": s.role} for s in self.plan.steps]

    def graph_node(self, assignment: Assignment, status: str | None = None) -> dict[str, Any]:
        if status is None:
            if assignment.idx in self.done:
                status = "completed" if assignment.ok else (
                    "blocked" if assignment.plan_status in ("blocked", "skipped") else "failed"
                )
            else:
                status = "pending"
        return {
            "id": f"agent-{assignment.idx}",
            "role": assignment.role,
            "status": status,
            "mode": assignment.mode or self.role_modes.get(assignment.idx, "chat"),
            "executor": assignment.executor or "",
            "provider": assignment.provider or "",
            "model": assignment.model or "",
            "tier": assignment.tier or "",
            "skills": list(assignment.skills or []),
            "input_tokens": assignment.input_tokens or 0,
            "output_tokens": assignment.output_tokens or 0,
            "cache_hit": bool(assignment.cache_hit),
            "duration_ms": round(assignment.duration_ms or 0.0, 1),
            "cost_usd": round(assignment.cost_usd or 0.0, 6),
            "files_touched": list(assignment.files_touched or []),
            "error": assignment.error or "",
        }

    def activate(self, assignment: Assignment, mode: str) -> None:
        if self.tracker is not None and self.task_id:
            node = self.graph_node(assignment, "running")
            node["mode"] = mode
            self.tracker.graph_update(
                self.task_id, node=node,
            )
            self.heartbeat(assignment, len(self.done), update_node=False)

    def heartbeat(
        self,
        assignment: Assignment,
        done_n: int,
        *,
        update_node: bool = True,
    ) -> None:
        if self.tracker is not None and self.task_id:
            if update_node:
                self.tracker.graph_update(
                    self.task_id, node=self.graph_node(assignment),
                )
            self.tracker.heartbeat(
                self.task_id, assignment.role, done_n,
                step_statuses=self.step_snapshot() if self.plan is not None else None,
            )

    def run_waves(self) -> list[Assignment]:
        """Wave scheduling: independent chat roles parallel; executors serial."""
        workers_cap = max(1, int(self.max_parallel_roles or 1))
        use_parallel = bool(self.parallel_waves) and workers_cap > 1
        waves = (
            build_waves(self.assignments)
            if use_parallel
            else [[a] for a in self.assignments]
        )

        spend_stop: dict[str, Any] | None = None
        for wave in waves:
            chat_items: list[tuple[Assignment, str, str, dict]] = []
            exec_items: list[tuple[Assignment, str, str, dict]] = []
            for a in wave:
                prep = self.prepare(a)
                if prep is None:
                    continue
                user, system, git_before = prep
                mode = a.mode or self.role_modes.get(a.idx, "chat")
                if mode == "executor":
                    # Prefer LeadOrchestrator / capability matcher assignment.
                    if not (a.executor or "").strip():
                        a.executor = resolve_role_executor(
                            a.role, self.executor_default or "claude-code",
                        )
                    if self.executor_runner is None:
                        # No runner yet — fall back to chat so production stays useful.
                        _log.info(
                            "multiagent[%d] %s mode=executor but no executor_runner — chat fallback",
                            a.idx, a.role,
                        )
                        a.mode_reason = f"{a.mode_reason}+chat_fallback_no_runner"
                        mode = "chat"
                if mode == "executor":
                    exec_items.append((a, user, system, git_before))
                else:
                    chat_items.append((a, user, system, git_before))
                self.activate(a, mode)

            resps: dict[int, dict[str, Any]] = {}
            if use_parallel and len(chat_items) > 1:
                from concurrent.futures import ThreadPoolExecutor

                _log.info(
                    "multiagent wave: %d chat roles in parallel (%s)",
                    len(chat_items), ", ".join(a.role for a, *_ in chat_items),
                )
                with ThreadPoolExecutor(
                    max_workers=min(len(chat_items), workers_cap),
                    thread_name_prefix="a2a-wave",
                ) as pool:
                    futures = {
                        pool.submit(self.chat_call, a, user, system): a.idx
                        for a, user, system, _ in chat_items
                    }
                    for fut, idx in futures.items():
                        resps[idx] = fut.result()
            else:
                for a, user, system, _ in chat_items:
                    resps[a.idx] = self.chat_call(a, user, system)

            for a, user, system, git_before in exec_items:
                self.run_executor(a, user, system, git_before)

            for a, _user, _system, git_before in chat_items:
                if self.finalize_chat(a, resps[a.idx], git_before):
                    spend_stop = resps[a.idx]

            # Spend limit is a hard stop for the WHOLE chain: remaining sub-agents
            # would only re-hit the same exhausted budget. Mark them spend-limited
            # (same observable outcome) but WITHOUT another gateway call, and stop —
            # early exit instead of walking every wave. (Budget isolation, Этап 4.)
            if spend_stop is not None:
                _log.info("multiagent: spend limit hit — stopping chain")
                for rest in self.assignments:
                    if rest.idx not in self.done:
                        rest.error = str(
                            spend_stop.get("error") or "Spend limit exceeded"
                        )
                        rest.ok = False
                        self.done[rest.idx] = rest
                break

        if self.plan is not None and self.engine is not None:
            self.engine.recompute_plan_status(self.plan)
            if self.store is not None:
                self.store.save(self.plan)

        if self.tracker is not None and self.task_id:
            _, ma_status = evaluate_multiagent_outcome(self.assignments)
            self.tracker.finish(
                self.task_id,
                status=ma_status,
                step_statuses=self.step_snapshot() if self.plan is not None else None,
            )
        return self.assignments


def run_local(
    task: str,
    assignments: list[Assignment],
    gateway: Any,
    skill_matcher: Callable[[str, str], list[Any]] | None = None,
    max_tokens: int = 4096,
    architect_max_tokens: int = 4096,
    *,
    memory: Any = None,
    headroom: Any = None,
    temperature: float = 0.0,
    task_id: str = "",
    tracker: Any = None,
    cwd: str = "",
    hybrid_code_gen: bool = True,
    hybrid_require_cwd: bool = True,
    requires_code_gen: bool = True,
    executor_default: str = "claude-code",
    executor_roles: list[str] | None = None,
    executor_runner: Callable[..., Any] | None = None,
    skip_dependents_on_failure: bool = True,
    parallel_waves: bool = True,
    max_parallel_roles: int = 3,
    plan_config: Any = None,
    plan_store: Any = None,
    capability_worker_url: str = "",
    capability_profiles_dir: str = ".voly/capability/profiles",
    capability_worker_timeout_s: float = 3.0,
) -> list[Assignment]:
    """Execute each sub-agent in dependency order. See ``multiagent.run_local`` docs."""
    run = _LocalRun(
        task=task,
        assignments=assignments,
        gateway=gateway,
        skill_matcher=skill_matcher,
        max_tokens=max_tokens,
        architect_max_tokens=architect_max_tokens,
        memory=memory,
        headroom=headroom,
        temperature=temperature,
        task_id=task_id,
        tracker=tracker,
        cwd=cwd,
        hybrid_code_gen=hybrid_code_gen,
        hybrid_require_cwd=hybrid_require_cwd,
        requires_code_gen=requires_code_gen,
        executor_default=executor_default,
        executor_roles=executor_roles,
        executor_runner=executor_runner,
        skip_dependents_on_failure=skip_dependents_on_failure,
        parallel_waves=parallel_waves,
        max_parallel_roles=max_parallel_roles,
        plan_config=plan_config,
        plan_store=plan_store,
        capability_worker_url=capability_worker_url,
        capability_profiles_dir=capability_profiles_dir,
        capability_worker_timeout_s=capability_worker_timeout_s,
    )
    run.setup_plan_and_modes()
    return run.run_waves()
