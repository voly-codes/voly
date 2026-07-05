"""Общее управление инференсом (классический вызов + DSPy)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from voly.dspy.runner import DSPyResult, DSPyRunner
else:
    DSPyResult = Any
    DSPyRunner = Any


@dataclass
class RuntimeResult:
    response: Optional[dict[str, Any]]
    runtime: str
    used: bool
    dspy_result: Optional[DSPyResult] = None


@dataclass
class InferenceOutcome:
    response: dict[str, Any]
    runtime: str
    dspy_result: Optional[DSPyResult] = None
    used_dspy: bool = False


class ClassicRuntime:
    """Вызов через AIGateway без оптимизаторов."""

    def __init__(self, config: Any, gateway: Any) -> None:
        self.config = config
        self.gateway = gateway

    def run(
        self,
        *,
        messages: list[dict[str, Any]],
        route: Any,
        model: str,
        tool_specs: list[Any] | None,
        system_prompt: str | None,
    ) -> RuntimeResult:
        response = self.gateway.chat(
            messages=messages,
            model=model,
            provider_name=route.provider,
            max_tokens=self.config.get_model_config(route.model).max_tokens,
            tools=tool_specs or [],
            system=system_prompt,
            agent=getattr(route, "agent", None),
        )
        return RuntimeResult(response=response, runtime="classic", used=True)


class DSPyRuntime:
    """Обёртка над DSPyRunner."""

    def __init__(self, runner: Optional[DSPyRunner]) -> None:
        self.runner = runner

    def is_available(self) -> bool:
        return self.runner is not None and self.runner.is_enabled()

    def run(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
        model: str,
    ) -> RuntimeResult:
        if not self.is_available():
            return RuntimeResult(response=None, runtime="dspy", used=False)

        assert self.runner is not None  # for mypy
        dspy_result = self.runner.run(
            task=task,
            messages=messages,
            route=route,
            model=model,
        )

        if dspy_result is None:
            return RuntimeResult(response=None, runtime="dspy", used=False)

        if dspy_result.dspy_used and dspy_result.content:
            response = {
                "content": dspy_result.content,
                "usage": {},
                "model": model,
                "dspy_used": True,
                "dspy_mode": dspy_result.mode,
                "dspy_program": dspy_result.program_id,
                "dspy_program_version": dspy_result.program_version,
                "dspy_program_tag": dspy_result.program_tag,
                "dspy_structured": dspy_result.structured,
            }
            return RuntimeResult(
                response=response,
                runtime="dspy",
                used=True,
                dspy_result=dspy_result,
            )

        return RuntimeResult(
            response=None,
            runtime="dspy",
            used=False,
            dspy_result=dspy_result,
        )


class InferenceManager:
    """Выбирает подходящий рантайм (DSPy/классика) и возвращает результат."""

    def __init__(self, config: Any, gateway: Any, dspy_runner: Optional[DSPyRunner] = None) -> None:
        self.config = config
        self.gateway = gateway
        self._classic_runtime = ClassicRuntime(config, gateway)
        self._dspy_runtime = DSPyRuntime(dspy_runner)

    def run(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        route: Any,
        model: str,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> InferenceOutcome:
        dspy_result: Optional[DSPyResult] = None

        if self._dspy_runtime.is_available():
            dspy_response = self._dspy_runtime.run(
                task=task,
                messages=messages,
                route=route,
                model=model,
            )
            dspy_result = dspy_response.dspy_result
            if dspy_response.response is not None and dspy_response.used:
                return InferenceOutcome(
                    response=dspy_response.response,
                    runtime="dspy",
                    dspy_result=dspy_result,
                    used_dspy=True,
                )

        classic_response = self._classic_runtime.run(
            messages=messages,
            route=route,
            model=model,
            tool_specs=tool_specs,
            system_prompt=system_prompt,
        )

        response = classic_response.response or {
            "content": "",
            "usage": {},
            "model": model,
        }
        if dspy_result:
            response.setdefault("dspy_mode", dspy_result.mode)
            response.setdefault("dspy_program", dspy_result.program_id)
            response.setdefault("dspy_program_version", dspy_result.program_version)
            response.setdefault("dspy_program_tag", dspy_result.program_tag)
            response.setdefault("dspy_used", dspy_result.dspy_used)

        return InferenceOutcome(
            response=response,
            runtime=classic_response.runtime,
            dspy_result=dspy_result,
            used_dspy=bool(dspy_result and dspy_result.dspy_used),
        )
