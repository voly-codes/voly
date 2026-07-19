"""Build helpers, gateway error checks, and TaskEvent emission."""

from __future__ import annotations

import time
from typing import Any

from voly.pipeline.types import PipelineResult, PipelineStage


class _EmitStageMixin:
    """Mixin: message/tool builders, gateway error handling, telemetry emit."""

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
