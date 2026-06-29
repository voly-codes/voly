"""_PipelineStageMixin: all _stage_* helpers + build/check/emit helpers."""

from __future__ import annotations

import time
from typing import Any

from codeops.pipeline.types import PipelineResult, PipelineStage


class _PipelineStageMixin:
    """Mixin for Pipeline: individual stage implementations."""

    # ── AGUI ─────────────────────────────────────────────────────────────────

    def _stage_agui_start(self, session_id: str) -> None:
        from codeops.agui import AGUIContext

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
        from codeops.router import RouteDecision

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

    # ── Route ─────────────────────────────────────────────────────────────────

    def _stage_route(
        self,
        task: str,
        context: dict[str, Any],
        force_model: str | None,
        force_agent: str | None,
    ) -> tuple[Any, Any, str | None]:
        from codeops.cost_policy import apply_cost_policy, detect_task_type

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
        from codeops.spend import check_agent_spend_limit
        from codeops.telemetry import TaskEvent, emit_event_from_config

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
        from codeops.models.providers import ModelResponse, ModelUsage

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
        from codeops.telemetry import GatewayMetrics, TaskEvent, emit_event_from_config

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
    ) -> tuple[Any, str, float]:
        from codeops.automation import compute_automation_metrics
        from codeops.cost_policy import budget_status
        from codeops.executor.base import ExecutorResult
        from codeops.telemetry import (
            GatewayMetrics, TaskEvent, TokenMetrics,
            _estimate_cost, emit_event_from_config,
        )

        skill_ids = injected_skills if injected_skills is not None else [
            s.id for s in self.match_skills_for_task(task, route.agent)  # type: ignore[attr-defined]
        ]
        resolved_model = gw_result.get("model", response.model)
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
                saved_headroom=0,
            ),
            gateway=GatewayMetrics(
                cache_hit=gw_result.get("cache_hit", False),
                fallback_used=gw_result.get("fallback_used", False),
                dlp_blocked=False,
            ),
            skill_ids=skill_ids,
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
            **dspy_fields,
        )
        emit_event_from_config(ev, self.config)  # type: ignore[attr-defined]
        return ev, status, cost_usd
