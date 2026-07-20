"""A2A + AG-UI pipeline stage implementations."""

from __future__ import annotations

import time
from typing import Any

from voly.pipeline.types import PipelineResult, PipelineStage


class _A2AStageMixin:
    """Mixin: AG-UI session + A2A federation / local multi-agent."""

    # ── AGUI ─────────────────────────────────────────────────────────────────

    def _stage_agui_start(self, session_id: str) -> None:
        from voly.agui import AGUIContext

        if not self.agui._event_queues.get(session_id):  # type: ignore[attr-defined]
            ctx = AGUIContext(conversation_id=session_id, session_id=session_id)
            self.agui.create_session(ctx)  # type: ignore[attr-defined]
        self._fire(PipelineStage.AGUI_START, session_id=session_id)  # type: ignore[attr-defined]

    def _stage_agui_done(self, session_id: str, response: Any) -> None:
        self.agui.stream_text(session_id, response.content)  # type: ignore[attr-defined]
        self._fire(PipelineStage.AGUI_DONE, session_id=session_id)  # type: ignore[attr-defined]

    # ── A2A ──────────────────────────────────────────────────────────────────

    def _stage_a2a(
        self, task: str, agui_session_id: str | None, started: float
    ) -> PipelineResult | None:
        from voly.router import RouteDecision

        self._fire(PipelineStage.A2A_DISCOVER, task=task)  # type: ignore[attr-defined]
        a2a_task = self.a2a.create_task(title=task[:100], description=task)  # type: ignore[attr-defined]
        self.a2a.route_and_delegate(a2a_task)  # type: ignore[attr-defined]
        self._fire(PipelineStage.A2A_DELEGATE, a2a_task=a2a_task)  # type: ignore[attr-defined]

        if a2a_task.state.value in ("completed", "working"):
            return PipelineResult(
                success=a2a_task.state.value == "completed",
                stage=PipelineStage.DONE,
                route=RouteDecision(
                    agent=a2a_task.metadata.get("routed_to", "a2a"),
                    model="auto",
                    provider="anthropic",
                ),
                a2a_tasks=[a2a_task],
                agui_session_id=agui_session_id or "",
                duration_ms=(time.monotonic() - started) * 1000,
            )
        return None

    def _should_dispatch_a2a(self, analysis: Any, *, nested: bool = False) -> bool:
        if nested:
            return False
        if not self.config.a2a.enabled or not getattr(self.config.a2a, 'auto_dispatch', True):
            return False
        flags = sum([
            bool(getattr(analysis, 'requires_code_gen', False)),
            bool(getattr(analysis, 'requires_review', False)),
            bool(getattr(analysis, 'requires_testing', False)),
            bool(getattr(analysis, 'requires_deployment', False)),
        ])
        min_flags = getattr(self.config.a2a, 'min_flags_for_dispatch', 2)
        return flags >= min_flags or getattr(analysis, 'complexity', '') == 'high'

    def _stage_a2a_auto(
        self,
        task: str,
        analysis: Any,
        agui_session_id: str | None,
        started: float,
        task_id: str,
        *,
        nested: bool = False,
        project_cwd: str = "",
        task_features: list[str] | None = None,
    ) -> Any | None:
        if nested:
            return None
        import time as _time
        from voly.a2a.decomposer import TaskDecomposer
        from voly.a2a.merger import ResultMerger
        from voly.a2a.report import A2AReport
        from voly.router import RouteDecision

        decomposer = TaskDecomposer()
        subtasks = decomposer.decompose(task, analysis)
        if len(subtasks) < 2:
            return None

        self._fire(PipelineStage.A2A_DISCOVER, subtasks=subtasks)  # type: ignore[attr-defined]

        # Local mode: a strong lead orchestrator assigns model tier + skills per
        # sub-agent, then each runs in-process via AIGateway.chat(). No federation.
        if getattr(self.config.a2a, 'execution_mode', 'local') == 'local':
            return self._run_multiagent_local(
                task, subtasks, agui_session_id, started, task_id,
                analysis=analysis,
                project_cwd=project_cwd,
                task_features=task_features,
            )

        timeout = getattr(self.config.a2a, 'task_timeout_seconds', 120.0)  # type: ignore[attr-defined]
        a2a_tasks = self.a2a.dispatch_parallel(subtasks, timeout_seconds=timeout)  # type: ignore[attr-defined]
        self._fire(PipelineStage.A2A_DELEGATE, a2a_tasks=a2a_tasks)  # type: ignore[attr-defined]

        # Poll until all tasks complete or timeout
        import logging as _logging
        _poll_log = _logging.getLogger('voly.pipeline')
        poll_deadline = _time.monotonic() + timeout
        poll_interval = 3.0
        from voly.a2a import TaskState as _TaskState
        terminal = {_TaskState.COMPLETED, _TaskState.FAILED, _TaskState.CANCELLED}
        while _time.monotonic() < poll_deadline:
            pending = [t for t in a2a_tasks if t.state not in terminal]
            if not pending:
                break
            _poll_log.debug("A2A polling: %d tasks pending", len(pending))
            _time.sleep(poll_interval)
            for t in pending:
                updated = self.a2a.collect_results(t)  # type: ignore[attr-defined]
                _poll_log.debug("A2A poll task_id=%s agent=%s state=%s",
                                t.id, t.metadata.get('agent'), updated.state)
        else:
            _poll_log.warning("A2A polling timed out after %.0fs", timeout)

        merged = ResultMerger().merge(task, a2a_tasks)
        duration_ms = (_time.monotonic() - started) * 1000

        # Honest status: completed only when every dispatched task completed
        # (mirrors evaluate_multiagent_outcome on the local path).
        completed_tasks = [t for t in a2a_tasks if t.state == _TaskState.COMPLETED]
        fed_success = bool(a2a_tasks) and len(completed_tasks) == len(a2a_tasks)
        fed_status = (
            'completed' if fed_success
            else ('partial' if completed_tasks else 'failed')
        )

        # Build and save report
        reports_dir = getattr(self.config.telemetry, 'events_dir', '.voly/events')  # type: ignore[attr-defined]
        report = A2AReport.from_a2a_tasks(task_id, task, a2a_tasks, merged, duration_ms)
        try:
            saved = report.save(__import__('pathlib').Path(reports_dir).parent)
            import logging; logging.getLogger('voly.pipeline').info('A2A report saved: %s', saved)
        except Exception as e:
            import logging; logging.getLogger('voly.pipeline').warning('A2A report save failed: %s', e)

        agents_used = [t.metadata.get('agent', 'unknown') for t in a2a_tasks]
        route = RouteDecision(agent='a2a', model='multi-agent', provider='a2a', routing_score=0.9)

        # Create a fake InferenceResponse-like object for PipelineResult
        class _FakeUsage:
            input_tokens = 0
            output_tokens = 0
        class _FakeResponse:
            content = merged
            model = 'a2a'
            usage = _FakeUsage()

        # Emit telemetry event
        from voly.telemetry import TaskEvent, emit_event_from_config
        ev = TaskEvent(
            task_id=task_id,
            agent='a2a',
            status=fed_status,
            model='multi-agent',
            executor='a2a',
            duration_ms=duration_ms,
            a2a_dispatched=True,
            a2a_subtask_count=len(subtasks),
            a2a_agents_used=agents_used,
            task_prompt=task[:2000],
            result=merged[:40000],
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]

        return PipelineResult(
            success=fed_success,
            stage=PipelineStage.DONE,
            response=_FakeResponse(),
            route=route,
            a2a_tasks=a2a_tasks,
            agui_session_id=agui_session_id or '',
            duration_ms=duration_ms,
            event=ev,
        )

    def _run_multiagent_local(
        self,
        task: str,
        subtasks: list[Any],
        agui_session_id: str | None,
        started: float,
        task_id: str,
        *,
        analysis: Any = None,
        project_cwd: str = "",
        task_features: list[str] | None = None,
    ) -> Any | None:
        """Lead orchestrator assigns model tier + skills per sub-agent; run in-process."""
        import os
        import time as _time

        from voly.a2a.hybrid import make_agent_runner_executor
        from voly.a2a.assignment import evaluate_multiagent_outcome
        from voly.a2a.multiagent import LeadOrchestrator, merge_report, run_local
        from voly.router import RouteDecision
        from voly.telemetry import GatewayMetrics, TaskEvent, TokenMetrics, emit_event_from_config

        matcher = None
        project_context = None
        cap_cfg = getattr(self.config, "capability", None)  # type: ignore[attr-defined]
        if cap_cfg is not None and bool(getattr(cap_cfg, "enabled", False)):
            try:
                from voly.capability.matcher import ExecutorMatcher
                from voly.capability.registry import CapabilityRegistry

                profiles_dir = str(
                    getattr(cap_cfg, "profiles_dir", None) or ".voly/capability/profiles"
                )
                worker_url = str(getattr(cap_cfg, "worker_url", "") or "")
                matcher = ExecutorMatcher(
                    CapabilityRegistry(profiles_dir),
                    worker_url=worker_url,
                )
                project_context = {"task_features": list(task_features or [])}
            except Exception:  # noqa: BLE001
                matcher = None
                project_context = None

        lead = LeadOrchestrator(
            gateway=self.gateway,  # type: ignore[attr-defined]
            skill_matcher=self.match_skills_for_task,  # type: ignore[attr-defined]
            lead_model=getattr(self.config.a2a, 'lead_model', ''),  # type: ignore[attr-defined]
            lead_mode=getattr(self.config.a2a, 'lead_mode', 'auto') or 'auto',  # type: ignore[attr-defined]
            role_tiers=dict(getattr(self.config.a2a, 'role_tiers', None) or {}),  # type: ignore[attr-defined]
            matcher=matcher,
            project_context=project_context,
        )
        # Same as single-model path: surface marketplace skills not yet installed.
        skill_suggestions = self._stage_skill_suggest(task)  # type: ignore[attr-defined]
        assignments = lead.assign(task, subtasks)
        self._fire(PipelineStage.A2A_DELEGATE, a2a_tasks=assignments)  # type: ignore[attr-defined]

        # Savings on the multi-agent path: deterministic (temp=0) → gateway cache
        # hits on repeat; semantic memory injected/stored per sub-agent; optional
        # Headroom compression when the proxy is running.
        memory = self.memory if self.config.memory.enabled else None  # type: ignore[attr-defined]

        # Rung A resilience: heartbeat a RunRecord per sub-agent so a watchdog can
        # spot a chain that crashed/hung mid-flight (TaskEvent only fires at the end).
        tracker = None
        if self.config.telemetry.enabled:  # type: ignore[attr-defined]
            try:
                from voly.runtime.runs import RunTracker

                tracker = RunTracker(self.config.telemetry.runs_dir)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                tracker = None

        a2a_cfg = self.config.a2a  # type: ignore[attr-defined]
        # Prefer per-request cwd (API / CLI), then config default_cwd / env.
        cwd = (
            (project_cwd or "").strip()
            or (getattr(self.config, "default_cwd", None) or "").strip()  # type: ignore[attr-defined]
            or os.environ.get("VOLY_PROJECT_CWD", "").strip()
        )
        if cwd:
            cwd = os.path.expanduser(cwd)
        requires_code_gen = bool(
            getattr(analysis, "requires_code_gen", True) if analysis is not None else True
        )
        if cwd and bool(getattr(a2a_cfg, "hybrid_code_gen", True)):
            from voly.plan.verify import ensure_git_repo

            ensure_git_repo(cwd)
        # Hybrid PR2: implement roles use AgentRunner + billing fallback (no per-role TaskEvent).
        timeout = int(getattr(a2a_cfg, "task_timeout_seconds", 120) or 120)
        executor_runner = None
        if bool(getattr(a2a_cfg, "hybrid_code_gen", True)) and cwd:
            executor_runner = make_agent_runner_executor(
                self.config,  # type: ignore[attr-defined]
                max_turns=30,
                timeout=max(timeout, 30),
                emit_event=False,
            )
        plan_cfg = getattr(self.config, "plan", None)  # type: ignore[attr-defined]
        # PR5: fill empty tester_command from project scan (does not enable plan gates).
        if plan_cfg is not None and cwd and getattr(plan_cfg, "enabled", False):
            try:
                from dataclasses import replace

                from voly.plan.suggest import apply_suggestions_to_plan_config, suggest_from_cwd

                plan_cfg = replace(plan_cfg)
                apply_suggestions_to_plan_config(plan_cfg, suggest_from_cwd(cwd))
            except Exception:  # noqa: BLE001
                pass
        run_local(
            task, assignments, self.gateway, self.match_skills_for_task,  # type: ignore[attr-defined]
            memory=memory, headroom=getattr(self, 'headroom_mgr', None),
            task_id=task_id, tracker=tracker,
            cwd=cwd,
            hybrid_code_gen=bool(getattr(a2a_cfg, "hybrid_code_gen", True)),
            hybrid_require_cwd=bool(getattr(a2a_cfg, "hybrid_require_cwd", True)),
            requires_code_gen=requires_code_gen,
            executor_default=getattr(a2a_cfg, "executor_default", "claude-code") or "claude-code",
            executor_roles=list(getattr(a2a_cfg, "executor_roles", None) or []),
            executor_runner=executor_runner,
            parallel_waves=bool(getattr(a2a_cfg, "parallel_waves", True)),
            max_parallel_roles=int(getattr(a2a_cfg, "max_parallel_roles", 3) or 3),
            architect_max_tokens=int(
                getattr(a2a_cfg, "architect_max_tokens", 4096) or 4096
            ),
            plan_config=plan_cfg,
            capability_worker_url=str(getattr(cap_cfg, "worker_url", "") or "") if cap_cfg else "",
            capability_profiles_dir=str(
                getattr(cap_cfg, "profiles_dir", None) or ".voly/capability/profiles"
            ) if cap_cfg else ".voly/capability/profiles",
            capability_worker_timeout_s=float(
                getattr(cap_cfg, "worker_timeout_s", 3.0) or 3.0
            ) if cap_cfg else 3.0,
        )

        merged = merge_report(task, assignments)
        ma_success, ma_status = evaluate_multiagent_outcome(
            assignments, requires_code_gen=requires_code_gen,
        )
        duration_ms = (_time.monotonic() - started) * 1000
        total_in = sum(a.input_tokens for a in assignments)
        total_out = sum(a.output_tokens for a in assignments)
        total_cost = sum(a.cost_usd for a in assignments)
        total_saved = sum(a.saved_tokens for a in assignments)
        cache_hits = sum(1 for a in assignments if a.cache_hit)
        mem_hits = sum(a.mem_hits for a in assignments)
        skill_ids = sorted({s for a in assignments for s in a.skills})
        agents_used = [a.role for a in assignments]
        # Multi-agent path previously skipped RTK stats → saved_rtk always 0.
        rtk_stats = self._stage_rtk()
        saved_rtk = int(
            rtk_stats.get("tokens_saved")
            or rtk_stats.get("saved_tokens")
            or rtk_stats.get("tokens_filtered")
            or 0
        )

        # Reflect multi-agent activity in the UI stage panel instead of defaults.
        self._fire(PipelineStage.MEMORY_RETRIEVE, hits=[{}] * mem_hits)  # type: ignore[attr-defined]
        self._fire(PipelineStage.SKILL_INJECT, skill_ids=skill_ids, injected=len(skill_ids))  # type: ignore[attr-defined]
        self._fire(PipelineStage.HEADROOM_COMPRESS, messages=[], tokens_saved=total_saved)  # type: ignore[attr-defined]

        self._metrics.total_tasks += 1  # type: ignore[attr-defined]
        self._metrics.total_tokens_in += total_in  # type: ignore[attr-defined]
        self._metrics.total_tokens_out += total_out  # type: ignore[attr-defined]
        self._metrics.total_tokens_saved_headroom += total_saved  # type: ignore[attr-defined]
        self._fire(PipelineStage.DONE)  # type: ignore[attr-defined]

        ev = TaskEvent(
            task_id=task_id,
            agent='a2a-local',
            status=ma_status,
            tokens=TokenMetrics(
                input=total_in, output=total_out,
                saved_headroom=total_saved, saved_rtk=saved_rtk,
            ),
            # Aggregate gateway view: cache hit only when the whole chain was cached.
            gateway=GatewayMetrics(cache_hit=bool(assignments) and cache_hits == len(assignments)),
            cost_usd=total_cost,
            duration_ms=duration_ms,
            model='multi-agent',
            provider='a2a-local',
            executor='a2a-local',
            skill_ids=skill_ids,
            memory_hits=mem_hits,
            a2a_dispatched=True,
            a2a_subtask_count=len(assignments),
            a2a_agents_used=agents_used,
            a2a_assignments=[a.to_event_dict() for a in assignments],
            task_prompt=task[:2000],
            result=merged[:40000],
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]

        route = RouteDecision(agent='a2a-local', model='multi-agent', provider='a2a-local', routing_score=0.9)

        class _FakeUsage:
            input_tokens = total_in
            output_tokens = total_out
        class _FakeResponse:
            content = merged
            model = 'multi-agent'
            usage = _FakeUsage()

        return PipelineResult(
            success=ma_success,
            stage=PipelineStage.DONE,
            response=_FakeResponse(),
            route=route,
            agui_session_id=agui_session_id or '',
            duration_ms=duration_ms,
            event=ev,
            injected_skills=skill_ids,
            skill_suggestions=skill_suggestions,
            memory_hits=[{}] * mem_hits,
            tokens_saved_by_headroom=total_saved,
        )
