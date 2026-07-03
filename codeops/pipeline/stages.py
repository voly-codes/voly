"""_PipelineStageMixin: all _stage_* helpers + build/check/emit helpers."""

from __future__ import annotations

import time
from typing import Any

from voly.pipeline.types import PipelineResult, PipelineStage


class _PipelineStageMixin:
    """Mixin for Pipeline: individual stage implementations."""

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
    ) -> Any | None:
        if nested:
            return None
        import time as _time
        from voly.a2a.decomposer import TaskDecomposer
        from voly.a2a.merger import ResultMerger
        from voly.a2a.report import A2AReport
        from voly.pipeline.types import PipelineResult, PipelineStage
        from voly.router import RouteDecision

        decomposer = TaskDecomposer()
        subtasks = decomposer.decompose(task, analysis)
        if len(subtasks) < 2:
            return None

        self._fire(PipelineStage.A2A_DISCOVER, subtasks=subtasks)  # type: ignore[attr-defined]

        # Local mode: a strong lead orchestrator assigns model tier + skills per
        # sub-agent, then each runs in-process via AIGateway.chat(). No federation.
        if getattr(self.config.a2a, 'execution_mode', 'local') == 'local':
            return self._run_multiagent_local(task, subtasks, agui_session_id, started, task_id)

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
            status='completed',
            model='multi-agent',
            executor='a2a',
            duration_ms=duration_ms,
            a2a_dispatched=True,
            a2a_subtask_count=len(subtasks),
            a2a_agents_used=agents_used,
            task_prompt=task[:2000],
            result=merged[:8000],
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]

        return PipelineResult(
            success=True,
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
    ) -> Any | None:
        """Lead orchestrator assigns model tier + skills per sub-agent; run in-process."""
        import time as _time

        from voly.a2a.multiagent import LeadOrchestrator, merge_report, run_local
        from voly.pipeline.types import PipelineResult, PipelineStage
        from voly.router import RouteDecision
        from voly.telemetry import GatewayMetrics, TaskEvent, TokenMetrics, emit_event_from_config

        lead = LeadOrchestrator(
            gateway=self.gateway,  # type: ignore[attr-defined]
            skill_matcher=self.match_skills_for_task,  # type: ignore[attr-defined]
            lead_model=getattr(self.config.a2a, 'lead_model', ''),  # type: ignore[attr-defined]
        )
        assignments = lead.assign(task, subtasks)
        self._fire(PipelineStage.A2A_DELEGATE, a2a_tasks=assignments)  # type: ignore[attr-defined]

        # Savings on the multi-agent path: deterministic (temp=0) → gateway cache
        # hits on repeat; semantic memory injected/stored per sub-agent; optional
        # Headroom compression when the proxy is running.
        memory = self.memory if self.config.memory.enabled else None  # type: ignore[attr-defined]
        run_local(
            task, assignments, self.gateway, self.match_skills_for_task,  # type: ignore[attr-defined]
            memory=memory, headroom=getattr(self, 'headroom_mgr', None),
        )

        merged = merge_report(task, assignments)
        duration_ms = (_time.monotonic() - started) * 1000
        total_in = sum(a.input_tokens for a in assignments)
        total_out = sum(a.output_tokens for a in assignments)
        total_cost = sum(a.cost_usd for a in assignments)
        total_saved = sum(a.saved_tokens for a in assignments)
        cache_hits = sum(1 for a in assignments if a.cache_hit)
        mem_hits = sum(a.mem_hits for a in assignments)
        skill_ids = sorted({s for a in assignments for s in a.skills})
        agents_used = [a.role for a in assignments]

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
            status='completed' if any(a.ok for a in assignments) else 'failed',
            tokens=TokenMetrics(input=total_in, output=total_out, saved_headroom=total_saved),
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
            result=merged[:8000],
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
            success=any(a.ok for a in assignments),
            stage=PipelineStage.DONE,
            response=_FakeResponse(),
            route=route,
            agui_session_id=agui_session_id or '',
            duration_ms=duration_ms,
            event=ev,
            injected_skills=skill_ids,
            memory_hits=[{}] * mem_hits,
            tokens_saved_by_headroom=total_saved,
        )

    # ── Route ─────────────────────────────────────────────────────────────────

    def _stage_route(
        self,
        task: str,
        context: dict[str, Any],
        force_model: str | None,
        force_agent: str | None,
    ) -> tuple[Any, Any, str | None]:
        from voly.cost_policy import apply_cost_policy, detect_task_type

        analysis = self.router.analyze_task(task)  # type: ignore[attr-defined]
        route = self.router.route(task, context)  # type: ignore[attr-defined]
        if force_model:
            model_cfg = self.config.get_model_config(force_model)  # type: ignore[attr-defined]
            route.model = force_model
            route.provider = model_cfg.provider
        if force_agent:
            route.agent = force_agent
        policy = apply_cost_policy(route, task, self.config)  # type: ignore[attr-defined]
        if policy.model_override:
            route.model = policy.model_override
            route.provider = policy.provider_override or route.provider
        task_type = policy.task_type or detect_task_type(task)
        self._fire(PipelineStage.ROUTE, route=route, analysis=analysis, policy=policy)  # type: ignore[attr-defined]
        self._metrics.route_distribution[route.agent] = (  # type: ignore[attr-defined]
            self._metrics.route_distribution.get(route.agent, 0) + 1  # type: ignore[attr-defined]
        )
        return route, analysis, task_type

    # ── Spend check ───────────────────────────────────────────────────────────

    def _stage_spend_check(
        self,
        route: Any,
        task_id: str,
        analysis: Any,
        agui_session_id: str | None,
        started: float,
    ) -> PipelineResult | None:
        if not (self.config.spend.enabled and self.config.ai_gateway.spend_limits_enabled):  # type: ignore[attr-defined]
            return None
        from voly.spend import check_agent_spend_limit
        from voly.telemetry import TaskEvent, emit_event_from_config

        spend_check = check_agent_spend_limit(route.agent, self.config)  # type: ignore[attr-defined]
        if not spend_check or spend_check.get("ok"):
            return None

        duration = (time.monotonic() - started) * 1000
        error_msg = (
            f"Daily spend limit exceeded: ${spend_check.get('spent', 0):.4f} "
            f"/ ${spend_check.get('limit', 0):.2f}"
        )
        ev = TaskEvent(
            task_id=task_id,
            agent=route.agent,
            status="spend_limited",
            model=route.model,
            provider=route.provider,
            error=error_msg,
            duration_ms=duration,
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]
        return PipelineResult(
            success=False,
            stage=PipelineStage.ERROR,
            route=route,
            analysis=analysis,
            error=error_msg,
            agui_session_id=agui_session_id or "",
            duration_ms=duration,
        )

    # ── Memory ────────────────────────────────────────────────────────────────

    def _stage_memory_retrieve(self, task: str) -> list[dict[str, Any]]:
        if not self.config.memory.enabled:  # type: ignore[attr-defined]
            return []
        memory_results = self.memory.search(task, limit=5)  # type: ignore[attr-defined]
        messages = [
            {"role": "user", "content": f"[MEMORY: {m.category}] {m.title}: {m.content}"}
            for m in memory_results
        ]
        self._fire(PipelineStage.MEMORY_RETRIEVE, hits=memory_results)  # type: ignore[attr-defined]
        return messages

    def _stage_memory_store(self, task: str, response: Any, route: Any) -> None:
        self.memory.add(  # type: ignore[attr-defined]
            title=f"Task: {task[:100]}",
            content=response.content[:2000],
            category="history",
            metadata={"agent": route.agent, "model": route.model, "provider": route.provider},
            importance=0.6,
            tags=[route.agent, "task"],
        )
        self._fire(PipelineStage.MEMORY_STORE)  # type: ignore[attr-defined]

    # ── Headroom compress ─────────────────────────────────────────────────────

    def _stage_headroom_compress(
        self, messages: list[dict[str, Any]], model: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Compress messages via Headroom when it's running. Returns (messages, tokens_saved)."""
        mgr = getattr(self, "headroom_mgr", None)
        if mgr is None or not mgr.is_running():
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=messages, tokens_saved=0)  # type: ignore[attr-defined]
            return messages, 0
        try:
            result = mgr.compress(messages, model=model)
            compressed = result.get("messages", messages)
            saved = result.get("tokens_saved", 0)
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=compressed, tokens_saved=saved)  # type: ignore[attr-defined]
            return compressed, saved
        except Exception:
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=messages, tokens_saved=0)  # type: ignore[attr-defined]
            return messages, 0

    # ── RTK ───────────────────────────────────────────────────────────────────

    def _stage_rtk(self) -> dict[str, Any]:
        if self.config.rtk.enabled and self.rtk.is_installed():  # type: ignore[attr-defined]
            stats = self.rtk.get_stats(scope="project")  # type: ignore[attr-defined]
            self._fire(PipelineStage.RTK_FILTER, stats=stats)  # type: ignore[attr-defined]
            return stats
        return {}

    # ── Skill inject ──────────────────────────────────────────────────────────

    def _stage_skill_inject(
        self, task: str, agent_name: str | None
    ) -> tuple[list[str], str]:
        """Match installed skills and build a system-prompt block.

        Returns (skill_ids, prompt_addition). Both empty when nothing matches.
        """
        skills = self.match_skills_for_task(task, agent_name)  # type: ignore[attr-defined]
        skills_with_content = [s for s in skills if s.content and s.content.strip()]

        if not skills_with_content:
            self._fire(PipelineStage.SKILL_INJECT, skill_ids=[], injected=0)  # type: ignore[attr-defined]
            return [], ""

        lines: list[str] = ["# Loaded skills\n"]
        for skill in skills_with_content:
            lines.append(f"### {skill.name} ({skill.id})")
            lines.append(skill.content.strip()[:4000])
            lines.append("")

        block = "\n".join(lines).strip()
        ids = [s.id for s in skills_with_content]
        self._fire(PipelineStage.SKILL_INJECT, skill_ids=ids, injected=len(ids))  # type: ignore[attr-defined]
        return ids, block

    # ── Build helpers ─────────────────────────────────────────────────────────

    def _build_messages(
        self,
        memory_messages: list[dict[str, Any]],
        extra_messages: list[dict[str, Any]] | None,
        task: str,
    ) -> list[dict[str, Any]]:
        msgs = list(memory_messages)
        if extra_messages:
            msgs.extend(extra_messages)
        if task:
            msgs.append({"role": "user", "content": task})
        return msgs

    def _build_tools(self, tool_names: list[str]) -> list[dict[str, Any]] | None:
        if not tool_names:
            return None
        tools: list[dict[str, Any]] = []
        for name in tool_names:
            server = self.mcp.get(name)  # type: ignore[attr-defined]
            if server:
                for tool in server.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    })
            elif name in self.mcp.BUILTIN_SERVERS:  # type: ignore[attr-defined]
                self.mcp.register_builtin(name)  # type: ignore[attr-defined]
        return tools if tools else None

    def _build_model_response(self, gw_result: dict[str, Any], model: str) -> Any:
        from voly.models.providers import ModelResponse, ModelUsage

        usage = gw_result.get("usage", {})
        return ModelResponse(
            content=gw_result.get("content", ""),
            usage=ModelUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
            model=gw_result.get("model", model),
        )

    def _resolve_model(self, route: Any) -> str:
        model_cfg = self.config.get_model_config(route.model)  # type: ignore[attr-defined]
        return model_cfg.model

    # ── Gateway error check ───────────────────────────────────────────────────

    def _check_gateway_errors(
        self,
        gw_result: dict[str, Any],
        route: Any,
        analysis: Any,
        task_id: str,
        model: str,
        agui_session_id: str | None,
        started: float,
    ) -> PipelineResult | None:
        from voly.telemetry import GatewayMetrics, TaskEvent, emit_event_from_config

        _GATEWAY_ERRORS: list[tuple[str, str, dict[str, Any]]] = [
            ("dlp_blocked",   "dlp_blocked",   {"gateway": GatewayMetrics(dlp_blocked=True)}),
            ("rate_limited",  "rate_limited",  {}),
            ("spend_limited", "spend_limited", {}),
        ]
        _MESSAGES = {
            "dlp_blocked":   lambda r: f"DLP blocked: {r.get('error')}",
            "rate_limited":  lambda _: "Rate limit exceeded",
            "spend_limited": lambda _: "Daily spend limit exceeded",
        }
        for flag, status, extra_gw in _GATEWAY_ERRORS:
            if not gw_result.get(flag):
                continue
            _dur = (time.monotonic() - started) * 1000
            error_msg = _MESSAGES[flag](gw_result)
            ev = TaskEvent(
                task_id=task_id,
                agent=route.agent,
                status=status,
                routing_score=route.routing_score,
                duration_ms=_dur,
                model=model,
                provider=route.provider,
                error=error_msg if flag != "dlp_blocked" else gw_result.get("error"),
                **extra_gw,
            )
            emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]
            return PipelineResult(
                success=False,
                stage=PipelineStage.ERROR,
                error=error_msg,
                route=route,
                analysis=analysis,
                agui_session_id=agui_session_id or "",
                duration_ms=_dur,
                event=ev,
            )

        if gw_result.get("error") and not gw_result.get("content"):
            raise RuntimeError(gw_result["error"])
        return None

    # ── Telemetry / event emission ────────────────────────────────────────────

    def _extract_dspy_fields(self, dspy_result: Any) -> dict[str, Any]:
        return {
            "dspy_used":            dspy_result.dspy_used if dspy_result else False,
            "dspy_program_id":      dspy_result.program_id if dspy_result else None,
            "dspy_program_version": dspy_result.program_version if dspy_result else None,
            "dspy_program_tag":     dspy_result.program_tag if dspy_result else None,
            "dspy_optimizer":       dspy_result.optimizer if dspy_result else None,
            "dspy_dataset":         dspy_result.dataset if dspy_result else None,
            "dspy_compile_id":      dspy_result.compile_id if dspy_result else None,
            "dspy_score":           dspy_result.score if dspy_result else None,
            "dspy_shadow_delta":    dspy_result.shadow_score_delta if dspy_result else None,
        }

    def _emit_task_event(
        self,
        task_id: str,
        route: Any,
        response: Any,
        gw_result: dict[str, Any],
        rtk_stats: dict[str, Any],
        task_type: str | None,
        dspy_result: Any,
        duration: float,
        task: str,
        injected_skills: list[str] | None = None,
        headroom_saved: int = 0,
        memory_hits: int = 0,
    ) -> tuple[Any, str, float]:
        from voly.automation import compute_automation_metrics
        from voly.cost_policy import budget_status
        from voly.executor.base import ExecutorResult
        from voly.telemetry import (
            GatewayMetrics, TaskEvent, TokenMetrics,
            _estimate_cost, emit_event_from_config,
        )

        skill_ids = injected_skills if injected_skills is not None else [
            s.id for s in self.match_skills_for_task(task, route.agent)  # type: ignore[attr-defined]
        ]
        fallback_used = gw_result.get("fallback_used", False)
        fallback_model = gw_result.get("fallback_model", "")
        fallback_provider = gw_result.get("fallback_provider", "")
        # When fallback succeeded, use the actual model that ran, not the primary
        resolved_model = fallback_model or gw_result.get("model", response.model)
        cost_usd = _estimate_cost(resolved_model, response.usage.input_tokens, response.usage.output_tokens)
        pseudo_result = ExecutorResult(
            success=True,
            num_turns=1,
            cost_usd=cost_usd,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        automation_score, manual_steps = compute_automation_metrics(
            "pipeline", pseudo_result, task_type=task_type, via_pipeline=True
        )
        status = budget_status(cost_usd, self.config)  # type: ignore[attr-defined]
        dspy_fields = self._extract_dspy_fields(dspy_result)
        ev = TaskEvent(
            task_id=task_id,
            agent=route.agent,
            status=status,
            tokens=TokenMetrics(
                input=response.usage.input_tokens,
                output=response.usage.output_tokens,
                saved_rtk=rtk_stats.get("total_saved", 0),
                saved_headroom=headroom_saved,
            ),
            gateway=GatewayMetrics(
                cache_hit=gw_result.get("cache_hit", False),
                fallback_used=fallback_used,
                fallback_model=fallback_model,
                fallback_provider=fallback_provider,
                fallback_reason=gw_result.get("fallback_reason", ""),
                dlp_blocked=False,
            ),
            skill_ids=skill_ids,
            memory_hits=memory_hits,
            routing_score=route.routing_score,
            cost_usd=cost_usd,
            duration_ms=duration,
            model=resolved_model,
            provider=route.provider,
            executor="pipeline",
            task_type=task_type,
            automation_score=automation_score,
            manual_steps_removed=manual_steps,
            error=(
                f"Budget exceeded: ${cost_usd:.4f} > ${self.config.cost_policy.max_task_cost_usd:.2f}"  # type: ignore[attr-defined]
                if status == "budget_exceeded" else None
            ),
            dspy_enabled=self.config.dspy.enabled,  # type: ignore[attr-defined]
            dspy_mode=self.config.dspy.mode if self.config.dspy.enabled else None,  # type: ignore[attr-defined]
            task_prompt=task[:2000] if task else None,
            result=response.content[:8000] if response.content else None,
            stage_log=list(getattr(self, "_run_stage_log", [])),  # type: ignore[attr-defined]
            **dspy_fields,
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]
        return ev, status, cost_usd
