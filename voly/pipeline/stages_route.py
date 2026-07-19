"""Route + spend-limit pipeline stage implementations."""

from __future__ import annotations

import time
from typing import Any

from voly.pipeline.types import PipelineResult, PipelineStage


class _RouteStageMixin:
    """Mixin: AgentRouter + pre-call spend check."""

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
