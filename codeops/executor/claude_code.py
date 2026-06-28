"""
ClaudeCodeExecutor — запускает claude -p в подпроцессе.

Это единственный executor который реально ВЫПОЛНЯЕТ код:
  - читает/пишет файлы через инструменты
  - запускает bash команды
  - возвращает cost_usd и токены из --output-format json

Использование:
  executor = ClaudeCodeExecutor()
  result = executor.run("Мигрируй Button компоненты в src/", cwd="/path/to/project")
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from codeops.executor.base import Executor, ExecutorResult


class ClaudeCodeExecutor(Executor):
    """Запускает claude CLI в non-interactive режиме с полным доступом к инструментам."""

    DEFAULT_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    def __init__(self, claude_bin: str | None = None):
        self._bin = claude_bin or shutil.which("claude") or "claude"

    @property
    def name(self) -> str:
        return "claude-code"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
        timeout: int = 600,
    ) -> ExecutorResult:
        tools = allowed_tools or self.DEFAULT_TOOLS
        tools_arg = ",".join(tools)

        cmd = [
            self._bin,
            "--print",
            "--output-format", "json",
            "--allowed-tools", tools_arg,
            "--max-turns", str(max_turns),
            task,
        ]

        env = {**os.environ}
        started = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = (time.monotonic() - started) * 1000

            if proc.returncode != 0:
                return ExecutorResult(
                    success=False,
                    error=proc.stderr or f"claude exited with code {proc.returncode}",
                    duration_ms=duration_ms,
                )

            return self._parse_output(proc.stdout, proc.stderr, duration_ms)

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(
                success=False,
                error=f"Timeout after {timeout}s",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            return ExecutorResult(
                success=False,
                error=f"claude CLI not found at: {self._bin}",
            )

    def _parse_output(self, stdout: str, stderr: str, duration_ms: float) -> ExecutorResult:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # claude может вернуть стриминг или текст без JSON
            return ExecutorResult(
                success=True,
                output=stdout,
                duration_ms=duration_ms,
            )

        is_error = data.get("is_error", False)
        result_text = data.get("result", "")

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # modelUsage может быть более детальным
        model_usage = data.get("modelUsage", {})
        if model_usage and not input_tokens:
            for model_data in model_usage.values():
                input_tokens += model_data.get("input_tokens", 0)
                output_tokens += model_data.get("output_tokens", 0)

        return ExecutorResult(
            success=not is_error,
            output=result_text,
            error=data.get("api_error_status", "") if is_error else "",
            cost_usd=data.get("total_cost_usd", 0.0) or 0.0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=data.get("duration_ms", duration_ms),
            num_turns=data.get("num_turns", 0),
            session_id=data.get("session_id", ""),
            metadata={
                "stop_reason": data.get("stop_reason"),
                "terminal_reason": data.get("terminal_reason"),
                "subtype": data.get("subtype"),
            },
        )
