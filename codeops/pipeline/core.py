"""Pipeline — главный оркестратор CodeOps."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from codeops.pipeline.skills import _SkillsMixin
from codeops.pipeline.stages import _PipelineStageMixin
from codeops.pipeline.types import PipelineMetrics, PipelineResult, PipelineStage
from codeops.pipeline.workflow import _WorkflowMixin

logger = logging.getLogger(__name__)


class Pipeline(_PipelineStageMixin, _WorkflowMixin, _SkillsMixin):
    """CodeOps pipeline: INIT → ROUTE → SKILL_INJECT → MODEL_CALL → DONE."""

    def __init__(self, config: Any = None):
        from codeops.config import load_config
        from codeops.memory.store import MemoryStore
        from codeops.router import AgentRouter
        from codeops.rtk.installer import RTKManager
        from codeops.tools.mcp import MCPManager

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
        self._provider: Any = None
        self._metrics = PipelineMetrics()
        self._stage_hooks: dict[PipelineStage, list[Callable]] = {
            stage: [] for stage in PipelineStage
        }
        self._ai_gateway: Any = None
        self._dspy_runner: Any = None
        self._inference_manager: Any = None

    # ── Lazy-loaded subsystems ────────────────────────────────────────────────

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

    # ── Public API ────────────────────────────────────────────────────────────

    def on(self, stage: PipelineStage, hook: Callable) -> None:
        self._stage_hooks[stage].append(hook)

    def scan_project(self) -> Any:
        if self._project_profile is None:
            from codeops.scanner import ProjectScanner
            self._scanner = ProjectScanner()
            self._project_profile = self._scanner.scan()
        return self._project_profile

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

    def shutdown(self) -> None:
        if self.headroom_mgr:
            self.headroom_mgr.stop()
        self.memory.close()

    def start_agui_gateway(self) -> str:
        from codeops.agui import AGUIContext
        ctx = AGUIContext(conversation_id=str(__import__("uuid").uuid4()))
        return self.agui.create_session(ctx)

    def deploy_a2a_agents(self, agents_cards: list[dict[str, Any]]) -> list[str]:
        from codeops.a2a import A2AAgent, AgentCard
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

    # ── Main run ──────────────────────────────────────────────────────────────

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
        from codeops.telemetry import TaskEvent, emit_event_from_config, new_task_id

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

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_provider(self, name: str) -> Any:
        if self._provider is None:
            from codeops.models.providers import create_provider
            model_cfg = self.config.get_model_config()
            self._provider = create_provider(name, api_key=model_cfg.api_key, base_url=model_cfg.base_url)
        return self._provider

    def _fire(self, stage: PipelineStage, **kwargs: Any) -> None:
        for hook in self._stage_hooks.get(stage, []):
            try:
                hook(stage=stage, **kwargs)
            except Exception as exc:
                logger.debug("pipeline hook error at stage %s: %s", stage.value, exc)
