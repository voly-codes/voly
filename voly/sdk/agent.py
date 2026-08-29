"""Public Agent SDK facade (Phase 1 of docs/proposals/agent-workflow-sdk.md).

``Agent`` is a thin, typed wrapper — it is not a second runtime:

- chat mode delegates exclusively to ``AIGateway.chat()`` (via
  ``voly.ai_gateway.gateway_from_config``, the same governed wiring
  ``Pipeline.gateway`` builds — DLP, spend limits, cache, rate limits and the
  configured fallback chain all apply);
- executor mode delegates exclusively to ``voly.runner.agent_runner.AgentRunner``
  (billing fallback chain, evidence collection, WorkReport all apply as they
  do for ``voly run``/``voly runner``).

No provider SDK is constructed here, and no state machine is introduced —
``Agent`` never calls a provider directly and never tracks Plan-shaped state.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

_VALID_MODES = ("chat", "executor")


class AgentError(RuntimeError):
    """Raised for Agent usage errors (not provider/executor failures — those
    are reported on ``AgentResult.success``/``AgentResult.error``)."""


@dataclass
class AgentResult:
    """Typed result of ``Agent.run()``/``Agent.arun()``.

    Every field is populated from an underlying ``AIGateway.chat()`` response
    or ``AgentRunner`` ``RunnerResult`` — never fabricated by this facade.
    """

    content: str = ""
    success: bool = True
    error: str = ""
    provider: str = ""
    model: str = ""
    executor: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    files_touched: list[str] = field(default_factory=list)
    task_id: str = ""
    evidence_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Agent:
    def __init__(
        self,
        name: str,
        instructions: str = "",
        model: str | None = None,
        provider: str | None = None,
        tier: str | None = None,
        tools: list[str] | None = None,
        output_schema: type | dict | None = None,
        mode: Literal["chat", "executor"] = "chat",
        executor: str | None = None,
        *,
        config: Any = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise AgentError(f"Agent mode must be one of {_VALID_MODES}, got {mode!r}")
        if tools:
            # Design principle: safe defaults — no tool execution in this
            # phase. Accepting the field keeps the public constructor stable
            # for the phase that implements it; silently dropping tools would
            # let a caller believe they were honored.
            raise NotImplementedError(
                "Agent(tools=...) is not implemented yet — see "
                "docs/proposals/agent-workflow-sdk.md Phase 1 scope"
            )
        if output_schema is not None:
            raise NotImplementedError(
                "Agent(output_schema=...) is not implemented yet — see "
                "docs/proposals/agent-workflow-sdk.md Phase 1 scope"
            )

        self.name = name
        self.instructions = instructions
        self.model = model
        self.provider = provider
        self.tier = tier
        self.tools = list(tools or [])
        self.output_schema = output_schema
        self.mode = mode
        self.executor = executor

        from voly.config import VOLYConfig

        self.config = config or VOLYConfig()

    def run(
        self,
        task: str,
        *,
        cwd: str | None = None,
        timeout: int = 300,
        max_turns: int = 30,
    ) -> AgentResult:
        if self.mode == "executor":
            return self._run_executor(task, cwd=cwd, timeout=timeout, max_turns=max_turns)
        return self._run_chat(task)

    async def arun(
        self,
        task: str,
        *,
        cwd: str | None = None,
        timeout: int = 300,
        max_turns: int = 30,
    ) -> AgentResult:
        """Async equivalent of ``run()``.

        Neither ``AIGateway.chat()`` nor ``AgentRunner.run()`` has a native
        async implementation (both make blocking HTTP/subprocess calls), so
        this offloads the synchronous call to a worker thread rather than
        duplicating gateway/executor logic with a second, async-native path.
        """
        return await asyncio.to_thread(
            self.run, task, cwd=cwd, timeout=timeout, max_turns=max_turns
        )

    def _resolve_model_provider(self) -> tuple[str, str]:
        if self.tier:
            from voly.a2a.assignment import resolve_tier_model

            return resolve_tier_model(self.tier)
        model_cfg = self.config.get_model_config(self.model)
        model = self.model or model_cfg.model or self.config.default_model
        provider = self.provider or model_cfg.provider or "anthropic"
        return model, provider

    def _run_chat(self, task: str) -> AgentResult:
        from voly.ai_gateway import gateway_from_config
        from voly.telemetry import (
            TaskEvent,
            TokenMetrics,
            _estimate_cost,
            emit_event_from_config,
            new_task_id,
        )

        model, provider = self._resolve_model_provider()
        gateway = gateway_from_config(self.config)
        task_id = new_task_id()
        t0 = time.monotonic()
        response = gateway.chat(
            messages=[{"role": "user", "content": task}],
            model=model,
            provider_name=provider,
            system=self.instructions or None,
            agent=self.name,
        )
        duration_ms = (time.monotonic() - t0) * 1000

        error = str(response.get("error") or "")
        usage = response.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        resolved_model = str(response.get("model") or model)
        cost_usd = _estimate_cost(resolved_model, input_tokens, output_tokens)
        content = str(response.get("content") or "")

        emit_event_from_config(
            TaskEvent(
                task_id=task_id,
                agent=self.name,
                status="failed" if error else "completed",
                model=resolved_model,
                provider=provider,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                tokens=TokenMetrics(input=input_tokens, output=output_tokens),
                task_prompt=task[:2000],
                result=(content or error)[:8000],
                error=error or None,
                workflow="sdk-agent",
            ),
            self.config,
        )

        return AgentResult(
            content=content,
            success=not error,
            error=error,
            provider=provider,
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            task_id=task_id,
            raw=response,
        )

    def _run_executor(
        self, task: str, *, cwd: str | None, timeout: int, max_turns: int
    ) -> AgentResult:
        if not cwd:
            raise AgentError(
                f"Agent(name={self.name!r}, mode='executor') requires an explicit "
                "cwd for file work"
            )
        from voly.runner.agent_runner import AgentRunner

        agent_id = self.executor or self.name
        runner = AgentRunner(self.config)
        runner_result = runner.run(
            task,
            agent_id,
            cwd=cwd,
            max_turns=max_turns,
            timeout=timeout,
            model=self.model or "",
        )
        er = runner_result.result
        files: list[str] = []
        if er.report is not None:
            files = list((er.report.files_created or []) + (er.report.files_changed or []))

        evidence_enabled = bool(getattr(getattr(self.config, "evidence", None), "enabled", False))

        return AgentResult(
            content=er.output or "",
            success=er.success,
            error=er.error or "",
            model=self.model or "",
            executor=runner_result.executor,
            input_tokens=er.input_tokens,
            output_tokens=er.output_tokens,
            cost_usd=er.cost_usd,
            duration_ms=er.duration_ms,
            files_touched=files,
            task_id=runner_result.task_id,
            evidence_id=runner_result.task_id if evidence_enabled else "",
            raw=dict(er.metadata or {}),
        )
