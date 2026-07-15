"""Pipeline — главный оркестратор VOLY."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from voly.pipeline.skills import _SkillsMixin
from voly.pipeline.stages import _PipelineStageMixin
from voly.pipeline.types import PipelineMetrics, PipelineResult, PipelineStage

logger = logging.getLogger(__name__)


class Pipeline(_PipelineStageMixin, _SkillsMixin):
    """VOLY pipeline: INIT → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE → MEMORY_RETRIEVE → RTK_FILTER → SKILL_INJECT → HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL → MEMORY_STORE → AGUI_DONE → DONE / ERROR."""

    def __init__(self, config: Any = None):
        from voly.config import load_config
        from voly.memory.store import MemoryStore
        from voly.router import AgentRouter
        from voly.rtk.installer import RTKManager
        from voly.tools.mcp import MCPManager

        self.config = config or load_config()
        self.router = AgentRouter(self.config)
        self.memory = MemoryStore(
            self.config.memory.db_path,
            self.config.memory.embedding_model,
            remote_url=self.config.memory.remote_url,
            backend=self.config.memory.backend,
            agent_memory_account_id=self.config.memory.agent_memory_account_id,
            agent_memory_namespace=self.config.memory.agent_memory_namespace,
            agent_memory_profile=self.config.memory.agent_memory_profile,
        )
        self.rtk = RTKManager(self.config.rtk.binary_path)
        self.headroom_mgr: Any = None
        self._a2a_orchestrator: Any = None
        self._agui_gateway: Any = None
        self._agent_registry: Any = None
        self._skill_registry: Any = None
        self._scanner: Any = None
        self._model_router: Any = None
        self._project_profile: Any = None
        self.mcp = MCPManager()
        self._metrics = PipelineMetrics()
        self._stage_hooks: dict[PipelineStage, list[Callable]] = {
            stage: [] for stage in PipelineStage
        }
        self._ai_gateway: Any = None
        self._dspy_runner: Any = None
        self._inference_manager: Any = None
        self._run_started: float = 0.0
        self._run_stage_log: list[dict] = []

    # ── Lazy-loaded subsystems ────────────────────────────────────────────────

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    @property
    def a2a(self) -> Any:
        if self._a2a_orchestrator is None:
            from voly.a2a import create_a2a_orchestrator
            self._a2a_orchestrator = create_a2a_orchestrator(
                self.config.a2a.federation_url,
                token=self.config.a2a.token,
            )
        return self._a2a_orchestrator

    @property
    def agui(self) -> Any:
        if self._agui_gateway is None:
            from voly.agui import create_agui_gateway
            self._agui_gateway = create_agui_gateway(self.config.agui.remote_url)
        return self._agui_gateway

    @property
    def agent_registry(self) -> Any:
        if self._agent_registry is None:
            from voly.registry.agents import AgentRegistry
            self._agent_registry = AgentRegistry()
        return self._agent_registry

    @property
    def skill_registry(self) -> Any:
        if self._skill_registry is None:
            from voly.registry.skills import create_skill_registry
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
            from voly.model_router import ModelRouter
            self._model_router = ModelRouter()
        return self._model_router

    @property
    def gateway(self) -> Any:
        if self._ai_gateway is None:
            from voly.ai_gateway import AIGateway
            gw = AIGateway(
                account_id=self.config.ai_gateway.account_id,
                gateway_id=self.config.ai_gateway.gateway_id,
                api_token=self.config.ai_gateway.api_token,
            )
            gw.cache.enabled = self.config.ai_gateway.cache_enabled
            gw.cache.ttl_seconds = self.config.ai_gateway.cache_ttl_seconds
            gw.cache.max_entries = self.config.ai_gateway.cache_max_entries
            gw.cache.persist_dir = getattr(self.config.ai_gateway, "cache_persist_dir", "")
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
            gw.upstream = self.config.ai_gateway.upstream
            gw.upstream_model = self.config.ai_gateway.upstream_model
            gw.upstream_fallback_direct = self.config.ai_gateway.upstream_fallback_direct
            gw.byok_enabled = getattr(self.config.ai_gateway, "byok_enabled", False)
            gw.byok_providers = list(getattr(self.config.ai_gateway, "byok_providers", None) or [])
            # Health checker must see BYOK providers as configured even without
            # env keys — otherwise a2a tier resolution demotes premium roles.
            from voly.ai_gateway.health import get_checker
            get_checker().configure_byok(gw.byok_enabled, gw.byok_providers)
            gw._enabled = self.config.ai_gateway.enabled
            # Scope the persistent cache to the project's repo state (R1): the same
            # task text on a changed repo — or a different project — must miss.
            project_cwd = getattr(self.config, "default_cwd", "")
            if project_cwd:
                from voly.ai_gateway.project_state import project_fingerprint
                gw.cache_scope = project_fingerprint(project_cwd)
            self._ai_gateway = gw
        return self._ai_gateway

    @property
    def dspy_runner(self) -> Any:
        if self._dspy_runner is None and self.config.dspy.enabled:
            try:
                from voly.dspy.runner import DSPyRunner
                self._dspy_runner = DSPyRunner(self.config, self.gateway)
            except ImportError:
                pass
        return self._dspy_runner

    @property
    def inference_manager(self) -> Any:
        if self._inference_manager is None:
            from voly.inference import InferenceManager
            self._inference_manager = InferenceManager(self.config, self.gateway, self.dspy_runner)
        return self._inference_manager

    # ── Public API ────────────────────────────────────────────────────────────

    def on(self, stage: PipelineStage, hook: Callable) -> None:
        self._stage_hooks[stage].append(hook)

    def scan_project(self) -> Any:
        if self._project_profile is None:
            from voly.scanner import ProjectScanner
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
                from voly.headroom.proxy import HeadroomManager
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
        from voly.agui import AGUIContext
        ctx = AGUIContext(conversation_id=str(__import__("uuid").uuid4()))
        return self.agui.create_session(ctx)

    def deploy_a2a_agents(self, agents_cards: list[dict[str, Any]]) -> list[str]:
        from voly.a2a import A2AAgent, AgentCard
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

    def _is_a2a_nested(self, context: dict[str, Any]) -> bool:
        """True when this run is an A2A subtask — skip auto-dispatch to avoid recursion."""
        import os

        if os.environ.get("VOLY_A2A_NESTED") == "1":
            return True
        return bool(context.get("a2a_parent_task_id"))

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
        from voly.telemetry import TaskEvent, emit_event_from_config, new_task_id

        started = time.monotonic()
        self._run_started = started
        self._run_stage_log = []
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

            # Auto A2A dispatch for complex multi-capability tasks (skip when nested subtask)
            a2a_nested = self._is_a2a_nested(context)
            if (
                not delegate_to_a2a
                and not a2a_nested
                and self._should_dispatch_a2a(analysis, nested=a2a_nested)
            ):
                a2a_auto_result = self._stage_a2a_auto(
                    task, analysis, agui_session_id, started, task_id,
                    nested=a2a_nested,
                    project_cwd=str(context.get("cwd") or context.get("project_cwd") or ""),
                )
                if a2a_auto_result is not None:
                    return a2a_auto_result

            spend_result = self._stage_spend_check(route, task_id, analysis, agui_session_id, started)
            if spend_result is not None:
                return spend_result

            memory_messages = self._stage_memory_retrieve(task)
            rtk_stats = self._stage_rtk()
            skill_suggestions = self._stage_skill_suggest(task)
            injected_skills, skills_system = self._stage_skill_inject(task, route.agent)

            model = self._resolve_model(route)
            msgs = self._build_messages(memory_messages, messages, task)
            msgs, headroom_saved = self._stage_headroom_compress(msgs, model)

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
                headroom_saved=headroom_saved,
                memory_hits=len(memory_messages),
            )
            self._metrics.total_tokens_saved_rtk += rtk_stats.get("total_saved", 0)
            self._metrics.total_tokens_saved_headroom += headroom_saved

            dspy_fields = self._extract_dspy_fields(dspy_result)
            return PipelineResult(
                success=status == "completed",
                stage=PipelineStage.DONE,
                response=response,
                route=route,
                analysis=analysis,
                memory_hits=memory_messages,
                tokens_saved_by_rtk=rtk_stats.get("total_saved", 0),
                tokens_saved_by_headroom=headroom_saved,
                agui_session_id=agui_session_id or "",
                duration_ms=duration,
                event=ev,
                injected_skills=injected_skills,
                skill_suggestions=skill_suggestions,
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

    def _fire(self, stage: PipelineStage, **kwargs: Any) -> None:
        elapsed = round((time.monotonic() - self._run_started) * 1000) if self._run_started else 0
        self._run_stage_log.append({"stage": stage.value, "elapsed_ms": elapsed})
        for hook in self._stage_hooks.get(stage, []):
            try:
                hook(stage=stage, **kwargs)
            except Exception as exc:
                logger.debug("pipeline hook error at stage %s: %s", stage.value, exc)
