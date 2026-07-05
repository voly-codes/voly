"""
DSPyRunner — the integration point between Pipeline and DSPy.

Pipeline inserts DSPyRunner between Headroom and AIGateway.chat():

    HEADROOM_COMPRESS
          ↓
    DSPyRunner.run()    ← this module
          ↓
    AIGateway.chat      ← unchanged single exit to models

Modes:
  off:    DSPy disabled — runner returns None, pipeline uses gateway directly.
  shadow: DSPy runs in parallel; result logged to telemetry but NOT returned.
          Gateway result is always returned to the caller.
  active: DSPy result replaces gateway for agents listed in config.dspy.agents.
          If DSPy fails → automatic fallback to gateway.

Thread safety: runner is stateless per call; DSPy program instances are cached
per-agent and loaded lazily from store on first use.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401
    _DSPY_AVAILABLE = True
except ImportError:
    pass


@dataclass
class DSPyResult:
    """Result returned by DSPyRunner.run()."""

    content: str
    agent: str
    program_id: str
    program_version: int = 0
    program_tag: str | None = None
    duration_ms: float = 0.0
    dspy_used: bool = False
    mode: str = "off"
    # Structured fields from the Signature (if available)
    structured: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    optimizer: str | None = None
    dataset: str | None = None
    compile_id: str | None = None
    score: float | None = None
    shadow_score_delta: float | None = None


class DSPyRunner:
    """Интеграция DSPy с учётом реестра программ и менеджера версий."""

    def __init__(self, config: Any, gateway: Any) -> None:
        from voly.dspy.programs import get_registry
        from voly.dspy.store import DSPyProgramStore
        from voly.dspy.versioning import ProgramVersionManager

        self.config = config
        self.gateway = gateway
        self.registry = get_registry()
        self.store = DSPyProgramStore(self.config.dspy.programs_dir)
        self.version_manager = ProgramVersionManager(self.config.dspy.programs_dir)
        self._program_cache: dict[tuple[str, str], Any] = {}
        self._program_meta: dict[tuple[str, str], dict[str, Any]] = {}
        self._lm_cache: dict[tuple[str, str, str], Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return (
            _DSPY_AVAILABLE
            and self.config.dspy.enabled
            and self.config.dspy.mode != "off"
        )

    def should_use_for_agent(self, agent: str) -> bool:
        """Return True if DSPy should be applied to this agent in active mode."""
        if not self.is_enabled():
            return False
        cfg = self.config.dspy
        if cfg.mode == "shadow":
            return True  # shadow always runs (but result ignored)
        # active mode: check agent allowlist
        if cfg.agents and agent not in cfg.agents:
            return False
        return True

    def run(
        self,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
        model: str,
    ) -> DSPyResult | None:
        """
        Run DSPy program for the agent.

        Returns:
          - DSPyResult with dspy_used=True if DSPy produced a response
          - DSPyResult with dspy_used=False if mode is shadow or DSPy failed
          - None if DSPy is disabled or agent not opted in
        """
        if not self.is_enabled():
            return None

        agent = getattr(route, "agent", "unknown")
        if not self.should_use_for_agent(agent):
            return None

        cfg = self.config.dspy
        started = time.monotonic()
        program_def = self._select_program(agent)
        if program_def is None:
            logger.debug("dspy.runner: программа для агента %s не найдена", agent)
            return None
        tag = self._resolve_tag(cfg)

        try:
            # Configure DSPy LM to use our AIGateway
            lm = self._get_lm(model, route.provider, agent)
            dspy.configure(lm=lm)  # type: ignore[name-defined]

            program, program_version, metadata, effective_tag = self._load_program(program_def, tag)

            inputs = self._build_inputs(program_def, task, messages, route)
            prediction = program(**inputs)

            duration_ms = (time.monotonic() - started) * 1000
            content, structured = self._extract_output(prediction)

            dspy_result = DSPyResult(
                content=content,
                agent=agent,
                program_id=program_def.program_id,
                program_version=program_version,
                program_tag=effective_tag,
                duration_ms=duration_ms,
                dspy_used=(cfg.mode == "active"),
                mode=cfg.mode,
                structured=structured,
            )

            if metadata:
                dspy_result.optimizer = getattr(metadata, "optimizer", None)
                dspy_result.dataset = getattr(metadata, "dataset", None)
                dspy_result.compile_id = getattr(metadata, "compile_id", None)
                dspy_result.score = getattr(metadata, "score", None)
                dspy_result.shadow_score_delta = getattr(metadata, "shadow_score_delta", None)

            if cfg.mode == "shadow":
                logger.debug(
                    "dspy.runner: shadow result for %s/%s (%.0fms): %s",
                    agent,
                    program_def.program_id,
                    duration_ms,
                    content[:120],
                )
                dspy_result.dspy_used = True  # DSPy ran; mode="shadow" = result not returned
                return dspy_result

            return dspy_result

        except Exception as exc:
            duration_ms = (time.monotonic() - started) * 1000
            logger.warning("dspy.runner: error for %s: %s", agent, exc)
            return DSPyResult(
                content="",
                agent=agent,
                program_id=program_def.program_id,
                duration_ms=duration_ms,
                dspy_used=False,
                mode=cfg.mode,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lm(self, model: str, provider: str, agent: str) -> Any:
        """Return cached VOLYDSPyLM instance.

        Uses config.dspy.model/provider if set — avoids routing model's provider
        (which may have no balance). Falls back to route model/provider only when
        no DSPy-specific model is configured.
        """
        cfg_dspy = self.config.dspy
        effective_model = cfg_dspy.model or model
        effective_provider = cfg_dspy.provider or provider

        # If provider still empty, resolve from model config
        if not effective_provider:
            mc = self.config.get_model_config(effective_model)
            effective_provider = mc.provider or "workers-ai"

        key = (effective_model, effective_provider, agent)
        if key not in self._lm_cache:
            from voly.dspy.adapter import VOLYDSPyLM

            mc = self.config.get_model_config(effective_model)
            self._lm_cache[key] = VOLYDSPyLM(
                gateway=self.gateway,
                model=mc.model or effective_model,
                provider=effective_provider,
                agent=agent,
                max_tokens=mc.max_tokens,
                temperature=mc.temperature,
            )
        return self._lm_cache[key]

    def _select_program(self, agent: str) -> Optional[Any]:
        overrides = getattr(self.config.dspy, "program_overrides", {}) or {}
        if agent in overrides:
            program = self.registry.get(overrides[agent])
            if program:
                return program
        return self.registry.get_primary(agent)

    def _resolve_tag(self, cfg: Any) -> Optional[str]:
        if cfg.mode == "active":
            return getattr(cfg, "active_tag", None) or "production"
        if cfg.mode == "shadow":
            return (
                getattr(cfg, "shadow_tag", None)
                or getattr(cfg, "active_tag", None)
                or "candidate"
            )
        return None

    def _load_program(
        self,
        program_def: Any,
        tag: Optional[str],
    ) -> tuple[Any, int, Optional[Any], Optional[str]]:
        cache_tag = tag or "__raw__"
        cache_key = (program_def.program_id, cache_tag)
        if cache_key in self._program_cache:
            program = self._program_cache[cache_key]
            meta = self._program_meta.get(cache_key, {})
            return (
                program,
                int(meta.get("version", 0)),
                meta.get("metadata"),
                meta.get("tag"),
            )

        program = program_def.factory()
        aliases = tuple(program_def.agents)

        resolved_version: Optional[int] = None
        effective_tag: Optional[str] = None

        if tag:
            resolved_version = self.version_manager.resolve_tag(program_def.program_id, tag)
            if resolved_version:
                loaded, resolved_version = self.store.load(
                    program_def.program_id,
                    program,
                    version=resolved_version,
                    aliases=aliases,
                )
                if not loaded:
                    resolved_version = None
                else:
                    effective_tag = tag

        if resolved_version is None:
            loaded, resolved_version = self.store.load(
                program_def.program_id,
                program,
                aliases=aliases,
            )
            if not loaded:
                resolved_version = 0

        metadata = (
            self.version_manager.metadata(program_def.program_id, resolved_version)
            if resolved_version
            else None
        )

        self._program_cache[cache_key] = program
        self._program_meta[cache_key] = {
            "version": resolved_version or 0,
            "metadata": metadata,
            "tag": effective_tag,
        }
        return program, resolved_version or 0, metadata, effective_tag

    def _build_inputs(
        self,
        program_def: Any,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
    ) -> dict[str, Any]:
        try:
            return program_def.inputs_builder(task, messages, route)
        except Exception as exc:
            logger.debug(
                "dspy.runner: inputs_builder failed for %s: %s",
                program_def.program_id,
                exc,
            )
            return {"task": task, "source_context": self._fallback_code_context(messages)}

    def _fallback_code_context(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for msg in messages[-5:]:
            content = msg.get("content")
            if isinstance(content, str) and len(content.strip()) > 20:
                parts.append(content[:800])
        return "\n---\n".join(parts)[:3000]

    def _extract_output(self, prediction: Any) -> tuple[str, dict[str, Any]]:
        """
        Extract plain text content and structured fields from a DSPy prediction.

        Returns:
            (content_str, structured_dict)
        """
        structured: dict[str, Any] = {}

        # Collect all output fields
        for attr in ("summary", "overview", "diagnosis", "root_cause",
                     "content", "title", "fix_description"):
            val = getattr(prediction, attr, None)
            if val is not None:
                structured[attr] = val

        for attr in ("risks", "bugs", "security_issues", "migration_plan", "tools"):
            val = getattr(prediction, attr, None)
            if val is not None:
                structured[attr] = val

        for attr in ("suggested_patch", "patch", "architecture", "proposed_design",
                     "usage", "limitations", "agent", "complexity", "confidence",
                     "reason", "test_suggestion"):
            val = getattr(prediction, attr, None)
            if val is not None:
                structured[attr] = val

        # Build human-readable content string from structured fields
        content_parts = []

        # Primary narrative
        for key in ("summary", "overview", "diagnosis", "fix_description", "title"):
            if key in structured and structured[key]:
                content_parts.append(str(structured[key]))
                break

        # Lists
        for key in ("bugs", "risks", "security_issues", "migration_plan"):
            if key in structured and structured[key]:
                content_parts.append(f"\n**{key.replace('_', ' ').title()}**:")
                for item in structured[key]:
                    content_parts.append(f"- {item}")

        # Extended prose
        for key in ("architecture", "proposed_design", "usage", "limitations"):
            if key in structured and structured[key]:
                content_parts.append(f"\n**{key.replace('_', ' ').title()}**:\n{structured[key]}")

        # Patches
        for key in ("suggested_patch", "patch"):
            if key in structured and structured[key]:
                content_parts.append(f"\n**Patch**:\n```diff\n{structured[key]}\n```")
                break

        content = "\n".join(content_parts).strip()
        if not content:
            # Last resort: repr of prediction
            content = str(prediction)

        return content, structured
