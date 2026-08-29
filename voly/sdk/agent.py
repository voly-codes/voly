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

Tool-calling (``tools=[...]``), structured output (``output_schema=...``) and
capability-registry routing all build on existing machinery rather than
introducing a second implementation:

- tool-calling's transport (OpenAI-style ``tools`` schemas, ``tool_calls`` in
  the response) is already wired end-to-end in ``AIGateway.chat()`` — see
  ``voly/ai_gateway/providers.py``. ``_run_chat``'s bounded tool loop mirrors
  ``voly.a2a.agentic_judge.AgenticJudgeAgent``'s proven shape; tool names are
  resolved against ``voly.sdk.tools``'s explicit allowlist registry, not
  accepted as raw callables.
- structured output is prompt-based validation (system-prompt schema
  instruction + parse/validate the text response), the same pattern
  ``voly.a2a.agentic_judge`` already uses for its JSON verdict — no new
  gateway-level ``response_format`` parameter was added.
- capability routing delegates to ``voly.capability.routing.capability_route``,
  the same ``ExecutorMatcher`` wiring ``voly.decisions._build_business_executor``
  and ``voly.a2a.lead.LeadOrchestrator`` already use for business actions and
  A2A dispatch — best-effort, and only consulted when the caller left
  ``model``/``tier``/``executor`` unset (explicit always wins) and
  ``config.capability.enabled`` is true (default false — no behavior change
  for anyone who hasn't opted in).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

_VALID_MODES = ("chat", "executor")
_DEFAULT_MAX_TOOL_STEPS = 6


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
    # Populated only when Agent(tools=[...]) triggered at least one tool
    # call: [{"name", "arguments", "result", "ok"}, ...] in call order.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Populated only when Agent(output_schema=...) validated successfully —
    # a pydantic model instance (type schema) or plain dict (dict schema).
    # `content` always stays the raw text response regardless.
    parsed: Any = None

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
        max_tool_steps: int = _DEFAULT_MAX_TOOL_STEPS,
    ) -> None:
        if mode not in _VALID_MODES:
            raise AgentError(f"Agent mode must be one of {_VALID_MODES}, got {mode!r}")
        if tools:
            from voly.sdk.tools import ToolError, resolve_tools

            try:
                resolve_tools(tools)  # fail-closed: every name must already be registered
            except ToolError as exc:
                raise AgentError(str(exc)) from exc
        if output_schema is not None and not _is_supported_output_schema(output_schema):
            raise AgentError(
                "Agent(output_schema=...) must be a dict (raw JSON schema) or a "
                f"pydantic BaseModel subclass, got {output_schema!r}"
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
        self.max_tool_steps = max(1, int(max_tool_steps))

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
        if self.model:
            model_cfg = self.config.get_model_config(self.model)
            return self.model, self.provider or model_cfg.provider or "anthropic"
        if self.tier:
            from voly.a2a.assignment import resolve_tier_model

            return resolve_tier_model(self.tier)
        from voly.capability.routing import capability_route

        hint = capability_route(self.name, mode="chat", config=self.config)
        if hint and hint[1]:
            return hint[1], hint[2] or self.provider or "anthropic"
        model_cfg = self.config.get_model_config(self.model)
        return model_cfg.model or self.config.default_model, self.provider or model_cfg.provider or "anthropic"

    def _build_system_prompt(self) -> str | None:
        parts = []
        if self.instructions:
            parts.append(self.instructions)
        if self.output_schema is not None:
            parts.append(
                "Respond with ONLY a single valid JSON value matching this "
                "JSON Schema — no prose, no markdown code fences:\n"
                + json.dumps(self._output_json_schema(), ensure_ascii=False)
            )
        return "\n\n".join(parts) if parts else None

    def _output_json_schema(self) -> dict[str, Any]:
        schema = self.output_schema
        return schema if isinstance(schema, dict) else schema.model_json_schema()

    def _parse_structured_output(self, content: str) -> tuple[Any, str]:
        """Returns ``(parsed_value, error)`` — ``error`` is empty on success."""
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text[:4].lower() == "json":
                text = text[4:].strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"structured output is not valid JSON: {exc}"
        schema = self.output_schema
        if isinstance(schema, dict):
            # Best-effort structural check only (no jsonschema dependency):
            # object-ness + declared top-level `required` keys. Not full
            # JSON Schema draft validation — see docs/backend/sdk.md.
            if not isinstance(data, dict):
                return None, "structured output is not a JSON object"
            missing = [k for k in (schema.get("required") or []) if k not in data]
            if missing:
                return None, f"structured output missing required fields: {missing}"
            return data, ""
        try:
            instance = schema.model_validate(data)
        except Exception as exc:  # noqa: BLE001 — pydantic.ValidationError and friends
            return None, f"structured output failed schema validation: {exc}"
        return instance, ""

    def _run_chat(self, task: str) -> AgentResult:
        from voly.ai_gateway import gateway_from_config
        from voly.sdk.tools import resolve_tools
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
        system = self._build_system_prompt()
        tool_objs = resolve_tools(self.tools) if self.tools else []
        tool_schemas = [t.schema() for t in tool_objs] if tool_objs else None
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tool_call_log: list[dict[str, Any]] = []
        total_input = total_output = 0
        resolved_model, content, error, response = model, "", "", {}
        t0 = time.monotonic()

        for _ in range(self.max_tool_steps):
            response = gateway.chat(
                messages=messages, model=model, provider_name=provider,
                system=system, agent=self.name, tools=tool_schemas,
            )
            usage = response.get("usage") or {}
            total_input += int(usage.get("input_tokens", 0))
            total_output += int(usage.get("output_tokens", 0))
            resolved_model = str(response.get("model") or model)
            error = str(response.get("error") or "")
            content = str(response.get("content") or "")
            if error:
                break
            calls = response.get("tool_calls") or []
            if not calls or not tool_objs:
                break
            messages.append({"role": "assistant", "content": content or "Requested tool use."})
            results = []
            for call in calls:
                cname = str(call.get("name") or "")
                args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                tool = next((t for t in tool_objs if t.name == cname), None)
                if tool is None:
                    result_text, ok = f"tool not in allowlist: {cname!r}", False
                else:
                    try:
                        result_text, ok = str(tool.fn(**args)), True
                    except Exception as exc:  # noqa: BLE001 — a tool failure is data, not a crash
                        result_text, ok = str(exc), False
                entry = {"name": cname, "arguments": args, "result": result_text[:2000], "ok": ok}
                tool_call_log.append(entry)
                results.append(entry)
            messages.append({
                "role": "user",
                "content": "Tool results:\n" + json.dumps(results, ensure_ascii=False),
            })
        else:
            if not error:
                error = (
                    f"tool-call loop exceeded max_tool_steps={self.max_tool_steps} "
                    "without a final answer"
                )

        duration_ms = (time.monotonic() - t0) * 1000
        cost_usd = _estimate_cost(resolved_model, total_input, total_output)

        parsed: Any = None
        if not error and self.output_schema is not None:
            parsed, schema_error = self._parse_structured_output(content)
            error = schema_error

        emit_event_from_config(
            TaskEvent(
                task_id=task_id,
                agent=self.name,
                status="failed" if error else "completed",
                model=resolved_model,
                provider=provider,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                tokens=TokenMetrics(input=total_input, output=total_output),
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
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            task_id=task_id,
            tool_calls=tool_call_log,
            parsed=parsed,
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

        instruction = f"{self.instructions}\n\n{task}".strip() if self.instructions else task
        agent_id = self.executor
        if not agent_id:
            from voly.capability.routing import capability_route
            from voly.runner.executor_factory import EXECUTOR_NAMES

            hint = capability_route(
                self.name, mode="executor", config=self.config,
                available_executors=list(EXECUTOR_NAMES),
            )
            if hint and hint[0]:
                agent_id = hint[0]
        agent_id = agent_id or self.name
        runner = AgentRunner(self.config)
        runner_result = runner.run(
            instruction,
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


def _is_supported_output_schema(schema: Any) -> bool:
    if isinstance(schema, dict):
        return True
    return (
        isinstance(schema, type)
        and hasattr(schema, "model_json_schema")
        and hasattr(schema, "model_validate")
    )
