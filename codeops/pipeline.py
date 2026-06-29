"""
Pipeline — главный оркестратор CodeOps.

Объединяет все компоненты в единый конвейер:
    1. AG-UI Gateway: real-time связь с UI/пользователем
    2. A2A Orchestrator: меж-агентная коммуникация
    3. Agent Router: анализирует задачу и выбирает агента/модель/инструменты
    4. RTK: фильтрует вывод команд перед отправкой в модель
    5. Headroom: сжимает контекст для снижения расхода токенов
    6. Memory: сохраняет и извлекает долгосрочную память
    7. Model: вызывает LLM через выбранного провайдера
    8. Tools: предоставляет доступ к внешним инструментам через MCP

Пример использования:
    pipeline = Pipeline(config)
    result = pipeline.run("Исправь баг с авторизацией в auth.py")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from codeops.automation import compute_automation_metrics
from codeops.config import CodeOpsConfig, load_config
from codeops.cost_policy import apply_cost_policy, budget_status, detect_task_type
from codeops.executor.base import ExecutorResult
from codeops.memory.store import MemoryStore
from codeops.models.providers import (
    ModelProvider,
    ModelResponse,
    ModelUsage,
    ProviderRegistry,
    create_provider,
)
from codeops.router import AgentRouter, RouteDecision, TaskAnalysis
from codeops.rtk.installer import RTKManager
from codeops.telemetry import (
    GatewayMetrics,
    TaskEvent,
    TokenMetrics,
    _estimate_cost,
    emit_event_from_config,
    new_task_id,
)
from codeops.tools.mcp import MCPManager


class PipelineStage(Enum):
    INIT = "init"
    AGUI_START = "agui_start"
    A2A_DISCOVER = "a2a_discover"
    A2A_DELEGATE = "a2a_delegate"
    ROUTE = "route"
    MEMORY_RETRIEVE = "memory_retrieve"
    RTK_FILTER = "rtk_filter"
    SKILL_INJECT = "skill_inject"
    HEADROOM_COMPRESS = "headroom_compress"
    DSPY_PROGRAM_CALL = "dspy_program_call"
    MODEL_CALL = "model_call"
    MEMORY_STORE = "memory_store"
    AGUI_DONE = "agui_done"
    DONE = "done"
    ERROR = "error"


@dataclass
class PipelineResult:
    success: bool
    stage: PipelineStage
    response: ModelResponse | None = None
    route: RouteDecision | None = None
    analysis: TaskAnalysis | None = None
    memory_hits: list = field(default_factory=list)
    tokens_saved_by_rtk: int = 0
    tokens_saved_by_headroom: int = 0
    duration_ms: float = 0.0
    a2a_tasks: list = field(default_factory=list)
    agui_session_id: str = ""
    error: str = ""
    injected_skills: list[str] = field(default_factory=list)
    event: TaskEvent | None = None
    dspy_used: bool = False
    dspy_mode: str = ""
    dspy_program_id: str | None = None
    dspy_program_version: int | None = None
    dspy_program_tag: str | None = None
    dspy_optimizer: str | None = None
    dspy_dataset: str | None = None
    dspy_compile_id: str | None = None
    dspy_score: float | None = None
    dspy_shadow_delta: float | None = None


@dataclass
class PipelineMetrics:
    total_tasks: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_tokens_saved_rtk: int = 0
    total_tokens_saved_headroom: int = 0
    avg_duration_ms: float = 0.0
    route_distribution: dict[str, int] = field(default_factory=dict)


class Pipeline:
    def __init__(self, config: CodeOpsConfig | None = None):
        self.config = config or load_config()
        self.router = AgentRouter(self.config)
        self.memory = MemoryStore(
            self.config.memory.db_path,
            self.config.memory.embedding_model,
            remote_url=self.config.memory.remote_url,
        )
        self.rtk = RTKManager(self.config.rtk.binary_path)
        self.headroom_mgr: Any = None
        self._a2a_orchestrator: Any = None
        self._agui_gateway: Any = None
        self._workflow_engine: Any = None
        self._agent_registry: Any = None
        self._skill_registry: Any = None
        self._scanner: Any = None
        self._model_router: Any = None
        self._project_profile: Any = None
        self.mcp = MCPManager()
        self._provider: ModelProvider | None = None
        self._metrics = PipelineMetrics()

        self._stage_hooks: dict[PipelineStage, list[Callable]] = {
            stage: [] for stage in PipelineStage
        }
        self._ai_gateway: Any = None
        self._dspy_runner: Any = None
        self._inference_manager: Any = None

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    @property
    def a2a(self) -> Any:
        if self._a2a_orchestrator is None:
            from codeops.a2a import create_a2a_orchestrator

            self._a2a_orchestrator = create_a2a_orchestrator(self.config.a2a.federation_url)
        return self._a2a_orchestrator

    @property
    def agui(self) -> Any:
        if self._agui_gateway is None:
            from codeops.agui import create_agui_gateway

            self._agui_gateway = create_agui_gateway(self.config.agui.remote_url)
        return self._agui_gateway

    @property
    def workflow(self) -> Any:
        if self._workflow_engine is None:
            from codeops.workflow import create_workflow_engine

            self._workflow_engine = create_workflow_engine(self.config.workflow.remote_url)
        return self._workflow_engine

    @property
    def agent_registry(self) -> Any:
        if self._agent_registry is None:
            from codeops.registry.agents import AgentRegistry

            self._agent_registry = AgentRegistry()
        return self._agent_registry

    @property
    def skill_registry(self) -> Any:
        if self._skill_registry is None:
            from codeops.registry.skills import create_skill_registry

            config_dir = None
            if hasattr(self, "_config_path") and self._config_path:
                config_dir = Path(self._config_path).parent
            self._skill_registry = create_skill_registry(
                skills_path=self.config.registry.skills_path,
                marketplace_url=self.config.registry.marketplace_url,
                config_dir=config_dir,
            )
        return self._skill_registry

    @property
    def model_router(self) -> Any:
        if self._model_router is None:
            from codeops.model_router import ModelRouter

            self._model_router = ModelRouter()
        return self._model_router

    @property
    def gateway(self) -> Any:
        if self._ai_gateway is None:
            from codeops.ai_gateway import AIGateway

            gw = AIGateway(
                account_id=self.config.ai_gateway.account_id,
                gateway_id=self.config.ai_gateway.gateway_id,
                api_token=self.config.ai_gateway.api_token,
            )
            gw.cache.enabled = self.config.ai_gateway.cache_enabled
            gw.cache.ttl_seconds = self.config.ai_gateway.cache_ttl_seconds
            gw.cache.max_entries = self.config.ai_gateway.cache_max_entries
            gw.rate_limit.enabled = self.config.ai_gateway.rate_limits_enabled
            gw.rate_limit.requests_per_minute = self.config.ai_gateway.rate_requests_per_minute
            gw.spend_limit.enabled = self.config.ai_gateway.spend_limits_enabled
            gw.spend_limit.daily_budget_usd = self.config.ai_gateway.spend_daily_budget_usd
            gw.spend_limit.per_agent_budget = self.config.ai_gateway.spend_per_agent_budget
            gw.fallback.enabled = self.config.ai_gateway.fallback_enabled
            gw.fallback.chain = self.config.ai_gateway.fallback_chain
            gw.fallback.retries = self.config.ai_gateway.fallback_retries
            gw.dlp.enabled = self.config.ai_gateway.dlp_enabled
            gw.dlp.block_secrets = self.config.ai_gateway.dlp_block_secrets
            gw.dlp.block_pii = self.config.ai_gateway.dlp_block_pii
            gw._enabled = self.config.ai_gateway.enabled
            self._ai_gateway = gw
        return self._ai_gateway

    @property
    def dspy_runner(self) -> Any:
        if self._dspy_runner is None and self.config.dspy.enabled:
            try:
                from codeops.dspy.runner import DSPyRunner

                self._dspy_runner = DSPyRunner(self.config, self.gateway)
            except ImportError:
                pass
        return self._dspy_runner

    @property
    def inference_manager(self) -> Any:
        if self._inference_manager is None:
            from codeops.inference import InferenceManager

            self._inference_manager = InferenceManager(self.config, self.gateway, self.dspy_runner)
        return self._inference_manager

    def scan_project(self) -> Any:
        if self._project_profile is None:
            from codeops.scanner import ProjectScanner

            self._scanner = ProjectScanner()
            self._project_profile = self._scanner.scan()
        return self._project_profile

    def on(self, stage: PipelineStage, hook: Callable) -> None:
        self._stage_hooks[stage].append(hook)

    def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
        agui_session_id: str | None = None,
        delegate_to_a2a: bool = False,
        force_model: str | None = None,
        force_agent: str | None = None,
    ) -> PipelineResult:
        started = time.monotonic()
        context = context or {}
        task_id = new_task_id()

        try:
            self._fire(PipelineStage.INIT, task=task)

            if self.config.agui.enabled and agui_session_id:
                self._stage_agui_start(agui_session_id)

            if self.config.a2a.enabled and delegate_to_a2a:
                result = self._stage_a2a(task, agui_session_id, started)
                if result is not None:
                    return result

            route, analysis, task_type = self._stage_route(task, context, force_model, force_agent)

            spend_result = self._stage_spend_check(route, task_id, analysis, agui_session_id, started)
            if spend_result is not None:
                return spend_result

            memory_messages = self._stage_memory_retrieve(task)
            rtk_stats = self._stage_rtk()
            injected_skills, skills_system = self._stage_skill_inject(task, route.agent)

            model = self._resolve_model(route)
            msgs = self._build_messages(memory_messages, messages, task)
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=msgs[:])

            base_system = route.config.get("system_prompt") or ""
            system_prompt = (base_system + "\n\n" + skills_system).strip() if skills_system else base_system or None

            inference_outcome = self.inference_manager.run(
                task=task,
                messages=msgs,
                route=route,
                model=model,
                tool_specs=self._build_tools(route.tools),
                system_prompt=system_prompt,
            )
            gw_result = inference_outcome.response
            dspy_result = inference_outcome.dspy_result
            dspy_used = inference_outcome.used_dspy

            error_result = self._check_gateway_errors(
                gw_result, route, analysis, task_id, model, agui_session_id, started
            )
            if error_result is not None:
                return error_result

            response = self._build_model_response(gw_result, model)
            self._fire(PipelineStage.MODEL_CALL, response=response)
            self._metrics.total_tokens_in += response.usage.input_tokens
            self._metrics.total_tokens_out += response.usage.output_tokens

            if self.config.memory.enabled:
                self._stage_memory_store(task, response, route)

            if self.config.agui.enabled and agui_session_id:
                self._stage_agui_done(agui_session_id, response)

            duration = (time.monotonic() - started) * 1000
            self._metrics.total_tasks += 1
            self._metrics.avg_duration_ms = (
                (self._metrics.avg_duration_ms * (self._metrics.total_tasks - 1) + duration)
                / self._metrics.total_tasks
            )
            self._fire(PipelineStage.DONE)

            ev, status, cost_usd = self._emit_task_event(
                task_id, route, response, gw_result, rtk_stats, task_type, dspy_result, duration, task,
                injected_skills=injected_skills,
            )
            self._metrics.total_tokens_saved_rtk += rtk_stats.get("total_saved", 0)

            dspy_fields = self._extract_dspy_fields(dspy_result)
            return PipelineResult(
                success=status == "completed",
                stage=PipelineStage.DONE,
                response=response,
                route=route,
                analysis=analysis,
                memory_hits=memory_messages,
                tokens_saved_by_rtk=rtk_stats.get("total_saved", 0),
                agui_session_id=agui_session_id or "",
                duration_ms=duration,
                event=ev,
                injected_skills=injected_skills,
                dspy_used=dspy_used,
                dspy_mode=self.config.dspy.mode if self.config.dspy.enabled else "",
                **dspy_fields,
            )

        except Exception as e:
            self._fire(PipelineStage.ERROR, error=str(e))
            _dur = (time.monotonic() - started) * 1000
            ev = TaskEvent(
                task_id=task_id,
                agent="unknown",
                status="failed",
                duration_ms=_dur,
                error=str(e),
            )
            emit_event_from_config(ev, self.config)
            return PipelineResult(
                success=False,
                stage=PipelineStage.ERROR,
                error=str(e),
                agui_session_id=agui_session_id or "",
                duration_ms=_dur,
                event=ev,
            )

    # ── Pipeline stage helpers ────────────────────────────────────────────────

    def _stage_agui_start(self, session_id: str) -> None:
        from codeops.agui import AGUIContext

        if not self.agui._event_queues.get(session_id):
            ctx = AGUIContext(conversation_id=session_id, session_id=session_id)
            self.agui.create_session(ctx)
        self._fire(PipelineStage.AGUI_START, session_id=session_id)

    def _stage_a2a(
        self, task: str, agui_session_id: str | None, started: float
    ) -> PipelineResult | None:
        self._fire(PipelineStage.A2A_DISCOVER, task=task)
        a2a_task = self.a2a.create_task(title=task[:100], description=task)
        self.a2a.route_and_delegate(a2a_task)
        self._fire(PipelineStage.A2A_DELEGATE, a2a_task=a2a_task)

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

    def _stage_route(
        self,
        task: str,
        context: dict[str, Any],
        force_model: str | None,
        force_agent: str | None,
    ) -> tuple[RouteDecision, TaskAnalysis, str | None]:
        analysis = self.router.analyze_task(task)
        route = self.router.route(task, context)
        if force_model:
            model_cfg = self.config.get_model_config(force_model)
            route.model = force_model
            route.provider = model_cfg.provider
        if force_agent:
            route.agent = force_agent
        policy = apply_cost_policy(route, task, self.config)
        if policy.model_override:
            route.model = policy.model_override
            route.provider = policy.provider_override or route.provider
        task_type = policy.task_type or detect_task_type(task)
        self._fire(PipelineStage.ROUTE, route=route, analysis=analysis, policy=policy)
        self._metrics.route_distribution[route.agent] = (
            self._metrics.route_distribution.get(route.agent, 0) + 1
        )
        return route, analysis, task_type

    def _stage_spend_check(
        self,
        route: RouteDecision,
        task_id: str,
        analysis: TaskAnalysis,
        agui_session_id: str | None,
        started: float,
    ) -> PipelineResult | None:
        if not (self.config.spend.enabled and self.config.ai_gateway.spend_limits_enabled):
            return None
        from codeops.spend import check_agent_spend_limit

        spend_check = check_agent_spend_limit(route.agent, self.config)
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
        emit_event_from_config(ev, self.config)
        return PipelineResult(
            success=False,
            stage=PipelineStage.ERROR,
            route=route,
            analysis=analysis,
            error=error_msg,
            agui_session_id=agui_session_id or "",
            duration_ms=duration,
        )

    def _stage_memory_retrieve(self, task: str) -> list[dict[str, Any]]:
        if not self.config.memory.enabled:
            return []
        memory_results = self.memory.search(task, limit=5)
        messages = [
            {"role": "user", "content": f"[MEMORY: {m.category}] {m.title}: {m.content}"}
            for m in memory_results
        ]
        self._fire(PipelineStage.MEMORY_RETRIEVE, hits=memory_results)
        return messages

    def _stage_rtk(self) -> dict[str, Any]:
        if self.config.rtk.enabled and self.rtk.is_installed():
            stats = self.rtk.get_stats(scope="project")
            self._fire(PipelineStage.RTK_FILTER, stats=stats)
            return stats
        return {}

    def _stage_skill_inject(
        self, task: str, agent_name: str | None
    ) -> tuple[list[str], str]:
        """Match skills for task and build a skills system-prompt block.

        Returns (skill_ids, system_prompt_addition).
        skill_ids is empty and system_prompt_addition is "" when no skills match
        or when there are no skills with content installed.
        """
        skills = self.match_skills_for_task(task, agent_name)
        skills_with_content = [s for s in skills if s.content and s.content.strip()]

        if not skills_with_content:
            self._fire(PipelineStage.SKILL_INJECT, skill_ids=[], injected=0)
            return [], ""

        lines: list[str] = ["# Loaded skills\n"]
        for skill in skills_with_content:
            lines.append(f"### {skill.name} ({skill.id})")
            lines.append(skill.content.strip()[:4000])
            lines.append("")

        block = "\n".join(lines).strip()
        ids = [s.id for s in skills_with_content]
        self._fire(PipelineStage.SKILL_INJECT, skill_ids=ids, injected=len(ids))
        return ids, block

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

    def _check_gateway_errors(
        self,
        gw_result: dict[str, Any],
        route: RouteDecision,
        analysis: TaskAnalysis,
        task_id: str,
        model: str,
        agui_session_id: str | None,
        started: float,
    ) -> PipelineResult | None:
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
            emit_event_from_config(ev, self.config)
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

    def _build_model_response(self, gw_result: dict[str, Any], model: str) -> ModelResponse:
        usage = gw_result.get("usage", {})
        return ModelResponse(
            content=gw_result.get("content", ""),
            usage=ModelUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
            model=gw_result.get("model", model),
        )

    def _stage_memory_store(
        self, task: str, response: ModelResponse, route: RouteDecision
    ) -> None:
        self.memory.add(
            title=f"Task: {task[:100]}",
            content=response.content[:2000],
            category="history",
            metadata={"agent": route.agent, "model": route.model, "provider": route.provider},
            importance=0.6,
            tags=[route.agent, "task"],
        )
        self._fire(PipelineStage.MEMORY_STORE)

    def _stage_agui_done(self, session_id: str, response: ModelResponse) -> None:
        self.agui.stream_text(session_id, response.content)
        self._fire(PipelineStage.AGUI_DONE, session_id=session_id)

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
        route: RouteDecision,
        response: ModelResponse,
        gw_result: dict[str, Any],
        rtk_stats: dict[str, Any],
        task_type: str | None,
        dspy_result: Any,
        duration: float,
        task: str,
        injected_skills: list[str] | None = None,
    ) -> tuple[TaskEvent, str, float]:
        skill_ids = injected_skills if injected_skills else [s.id for s in self.match_skills_for_task(task, route.agent)]
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
        status = budget_status(cost_usd, self.config)
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
                f"Budget exceeded: ${cost_usd:.4f} > ${self.config.cost_policy.max_task_cost_usd:.2f}"
                if status == "budget_exceeded" else None
            ),
            dspy_enabled=self.config.dspy.enabled,
            dspy_mode=self.config.dspy.mode if self.config.dspy.enabled else None,
            **dspy_fields,
        )
        emit_event_from_config(ev, self.config)
        return ev, status, cost_usd

    def setup_environment(self) -> bool:
        ok = True

        if self.config.rtk.enabled:
            try:
                self.rtk.ensure_installed(auto_install=self.config.rtk.auto_install)
                self.rtk.register_hooks("claude")
            except Exception as e:
                self._fire(PipelineStage.ERROR, error=f"RTK setup failed: {e}")
                ok = False

        if self.config.headroom.enabled:
            try:
                from codeops.headroom.proxy import HeadroomManager

                self.headroom_mgr = HeadroomManager(
                    port=self.config.headroom.port,
                    savings_profile=self.config.headroom.savings_profile,
                    memory_enabled=self.config.headroom.memory_enabled,
                    code_graph=self.config.headroom.code_graph,
                )
                self.headroom_mgr.start(wait=True)
            except Exception as e:
                self._fire(PipelineStage.ERROR, error=f"Headroom setup failed: {e}")
                ok = False

        if self.config.a2a.enabled:
            try:
                for url in self.config.a2a.remote_agents:
                    self.a2a.register_remote_agent(url)
            except Exception as e:
                self._fire(PipelineStage.ERROR, error=f"A2A discovery failed: {e}")
                ok = False

        return ok

    def deploy_a2a_agents(self, agents_cards: list[dict[str, Any]]) -> list[str]:
        from codeops.a2a import AgentCard, A2AAgent

        deployed: list[str] = []
        for spec in agents_cards:
            card = AgentCard(
                name=spec["name"],
                description=spec.get("description", ""),
                url=spec.get("url", f"http://127.0.0.1:{self.config.a2a.port}/a2a/{spec['name']}"),
                version=spec.get("version", "1.0.0"),
            )
            self.a2a.register_local_agent(A2AAgent(card))
            deployed.append(card.name)
        return deployed

    def start_agui_gateway(self) -> str:
        from codeops.agui import AGUIContext

        ctx = AGUIContext(conversation_id=str(__import__("uuid").uuid4()))
        return self.agui.create_session(ctx)

    def run_workflow(
        self,
        workflow_name: str,
        task: str,
        inputs: dict[str, Any] | None = None,
        *,
        instance_id: str | None = None,
    ) -> str:
        from codeops.workflow import StepState, WorkflowState

        if instance_id:
            instance = self.workflow.get_instance(instance_id)
            if not instance:
                raise ValueError(f"Workflow instance not found: {instance_id}")
        else:
            instance_id = self.workflow.start(workflow_name, inputs, task=task)
            instance = self.workflow.get_instance(instance_id)
            if not instance:
                raise ValueError(f"Workflow instance not found: {instance_id}")

        instance.state = WorkflowState.RUNNING
        if not instance.started_at:
            instance.started_at = __import__("time").time()
        self.workflow.persist(instance, task=task)

        while True:
            ready = instance.pending_steps()
            if not ready:
                if instance.approvals_pending:
                    for step_name in list(instance.approvals_pending):
                        step = instance.steps[step_name]
                        step.state = StepState.WAITING_APPROVAL
                    instance.state = WorkflowState.PAUSED
                    self.workflow.persist(instance, task=task)
                    return instance_id
                break

            for step_name in ready:
                step = instance.steps[step_name]
                step.state = StepState.RUNNING
                self.workflow.persist(instance, task=task)

                step_task = step.task_template.replace("{task}", task)
                try:
                    result = self.run(step_task)
                    if result.success:
                        step.state = StepState.COMPLETED
                        step.result = result.response.content if result.response else ""
                    else:
                        if step.retries < step.max_retries:
                            step.retries += 1
                            step.state = StepState.PENDING
                        else:
                            step.state = StepState.FAILED
                            step.error = result.error
                except Exception as e:
                    if step.retries < step.max_retries:
                        step.retries += 1
                        step.state = StepState.PENDING
                    else:
                        step.state = StepState.FAILED
                        step.error = str(e)
                self.workflow.persist(instance, task=task)

        self._check_workflow_done(instance)
        self.workflow.persist(instance, task=task)
        return instance_id

    def approve_workflow_step(self, instance_id: str, step_name: str) -> bool:
        instance = self.workflow.get_instance(instance_id)
        if not instance:
            return False
        approved = instance.approve(step_name)
        if approved:
            backend = getattr(self.workflow, "_persistent", None)
            if backend:
                backend.approve_remote(instance_id, step_name)
                refreshed = self.workflow.get_instance(instance_id)
                if refreshed:
                    instance = refreshed
            self.workflow.persist(instance)
        return approved

    def resume_workflow(self, instance_id: str, task: str | None = None) -> str | None:
        from codeops.workflow import WorkflowState

        instance = self.workflow.get_instance(instance_id)
        if not instance or instance.state != WorkflowState.PAUSED:
            return None
        backend = getattr(self.workflow, "_persistent", None)
        resolved_task = task or (backend.task_for(instance_id) if backend else "") or ""
        if not resolved_task:
            return None
        instance.state = WorkflowState.RUNNING
        self.workflow.persist(instance, task=resolved_task)
        return self.run_workflow(
            instance.definition.name,
            resolved_task,
            instance.inputs,
            instance_id=instance_id,
        )

    def match_skills_for_task(self, task: str, agent_name: str | None = None) -> list[Any]:
        from codeops.registry.skills import Skill

        profile = self.scan_project() if self.config.scanner.enabled else None

        skills: list[Skill] = []

        if agent_name:
            skills.extend(self.skill_registry.search(agent=agent_name))

        if profile:
            for lang in profile.languages:
                skills.extend(self.skill_registry.search(language=lang.name))
            for fw in profile.frameworks:
                skills.extend(self.skill_registry.search(framework=fw.name))

        skills.extend(self.skill_registry.search(query=task[:80], tags=[]))

        seen: set[str] = set()
        unique: list[Skill] = []
        for s in skills:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)

        return unique[:10]

    def match_agent_for_task(self, task: str) -> Any:
        from codeops.model_router import TaskCategory

        route = self.router.route(task)
        agent_def = self.agent_registry.get(route.agent)

        if agent_def:
            model_name = agent_def.preferred_model or route.model
        else:
            category = self.model_router._infer_category(task)
            model_info = self.model_router.route(category=category)
            model_name = model_info.name

        return {
            "agent": route.agent,
            "agent_def": agent_def,
            "model": model_name,
            "provider": route.provider,
            "skills": self.match_skills_for_task(task, route.agent),
            "tools": route.tools,
        }

    def _check_workflow_done(self, instance: Any) -> None:
        from codeops.workflow import StepState, WorkflowState

        all_done = all(
            s.state in (StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED)
            for s in instance.steps.values()
        )
        if all_done:
            has_failure = any(s.state == StepState.FAILED for s in instance.steps.values())
            instance.state = WorkflowState.FAILED if has_failure else WorkflowState.COMPLETED
            instance.finished_at = __import__("time").time()

    def shutdown(self) -> None:
        if self.headroom_mgr:
            self.headroom_mgr.stop()
        self.memory.close()

    def _get_provider(self, name: str) -> ModelProvider:
        if self._provider is None:
            model_cfg = self.config.get_model_config()
            self._provider = create_provider(
                name, api_key=model_cfg.api_key, base_url=model_cfg.base_url
            )
        return self._provider

    def _resolve_model(self, route: RouteDecision) -> str:
        model_cfg = self.config.get_model_config(route.model)
        return model_cfg.model

    def _build_tools(self, tool_names: list[str]) -> list[dict[str, Any]] | None:
        if not tool_names:
            return None

        tools: list[dict[str, Any]] = []
        for name in tool_names:
            server = self.mcp.get(name)
            if server:
                for tool in server.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    })
            elif name in self.mcp.BUILTIN_SERVERS:
                self.mcp.register_builtin(name)
        return tools if tools else None

    def _fire(self, stage: PipelineStage, **kwargs: Any) -> None:
        for hook in self._stage_hooks.get(stage, []):
            try:
                hook(stage=stage, **kwargs)
            except Exception as exc:
                logger.debug("pipeline hook error at stage %s: %s", stage.value, exc)
