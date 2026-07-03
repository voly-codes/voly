"""
CursorExecutor — agentic code executor via Cursor Agent API (cursor-sdk).

Запускает локальный Cursor Agent с доступом к инструментам (Read/Write/Bash)
в указанном cwd. Используется для реализации кода и задач с большим выводом.

Требования:
  - pip install cursor-sdk  (или pip install -e ".[cursor]")
  - CURSOR_API_KEY в .env

Использование:
  executor = CursorExecutor()
  result = executor.run("Implement CustomFieldRenderer", cwd="/path/to/smarty-crm-next")
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from voly.executor.base import Executor, ExecutorResult

_SUCCESS_STATUSES = frozenset({"finished", "completed", "success", "succeeded"})
_FAILURE_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "timeout"})


def _status_name(status: object) -> str:
    if status is None:
        return ""
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.lower()
    return str(status).lower().split(".")[-1]


class CursorExecutor(Executor):
    """Run tasks via Cursor Agent API (local runtime, full tool access)."""

    DEFAULT_MODEL = "composer-2.5"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or os.getenv("CURSOR_API_KEY", "")
        self._model = model or os.getenv("CURSOR_MODEL", self.DEFAULT_MODEL)

    @property
    def name(self) -> str:
        return "cursor"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
        timeout: int = 600,
        system: str | None = None,
    ) -> ExecutorResult:
        del allowed_tools, max_turns  # Cursor Agent manages tools internally

        if not self._api_key:
            return ExecutorResult(
                success=False,
                error="CURSOR_API_KEY is not set. Add it to voly/.env",
            )

        work_dir = cwd or os.getcwd()
        if not Path(work_dir).is_dir():
            return ExecutorResult(success=False, error=f"Working directory not found: {work_dir}")

        try:
            from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
        except ImportError:
            return ExecutorResult(
                success=False,
                error="cursor-sdk not installed. Run: pip install cursor-sdk",
            )

        prompt = task
        if system:
            prompt = f"{system.strip()}\n\n---\n\n{task}"

        started = time.monotonic()
        stream_timeout = float(timeout) if timeout and timeout > 0 else 900.0
        try:
            from cursor_sdk import Agent, AgentOptions, Client, LocalAgentOptions
            from cursor_sdk._client import close_default_client

            # Drop any stale global bridge from a prior crashed combat step.
            close_default_client()

            with Client.launch_bridge(
                workspace=work_dir,
                client_timeout=stream_timeout,
            ) as client:
                result = Agent.prompt(
                    prompt,
                    AgentOptions(
                        api_key=self._api_key,
                        model=self._model,
                        local=LocalAgentOptions(cwd=work_dir),
                    ),
                    client=client,
                )
        except Exception as exc:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(exc), duration_ms=duration_ms)

        duration_ms = (time.monotonic() - started) * 1000
        status = _status_name(getattr(result, "status", None))
        output = getattr(result, "result", "") or ""

        if status in _FAILURE_STATUSES:
            return ExecutorResult(
                success=False,
                output=output,
                error=output or f"Cursor agent finished with status: {status or 'unknown'}",
                duration_ms=duration_ms,
                metadata=self._metadata(result, work_dir),
            )

        success = status in _SUCCESS_STATUSES or bool(output.strip())
        return ExecutorResult(
            success=success,
            output=output,
            error="" if success else f"Cursor agent status: {status or 'unknown'}",
            duration_ms=float(getattr(result, "duration_ms", 0) or duration_ms),
            num_turns=1,
            session_id=getattr(result, "agent_id", "") or "",
            metadata=self._metadata(result, work_dir),
        )

    def _metadata(self, result: object, work_dir: str) -> dict:
        model = getattr(result, "model", None)
        model_id = getattr(model, "id", None) if model else self._model
        return {
            "mode": "cursor-sdk",
            "provider": "cursor",
            "model": model_id or self._model,
            "cwd": work_dir,
            "run_id": getattr(result, "id", ""),
        }
