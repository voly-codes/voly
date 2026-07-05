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

import logging

from voly.executor.base import Executor, ExecutorResult, _is_billing_error

_log = logging.getLogger("voly.executor.claude_code")


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
        ]

        # Explicitly grant access to cwd so claude doesn't deny file operations.
        # Without this, claude may ask for permission interactively (no TTY → exit 1).
        # "--" ends option parsing so --add-dir (variadic) doesn't consume the task string.
        if cwd:
            cmd += ["--add-dir", cwd]

        cmd += ["--", task]

        env = {**os.environ}
        started = time.monotonic()

        _log.info(
            "[CLAUDE] cmd=%s cwd=%r max_turns=%d",
            " ".join(cmd[:5]) + " ...",
            cwd,
            max_turns,
        )

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
                # stdout may contain JSON with is_error=true and a real error message —
                # try to parse it first before falling back to generic message.
                if proc.stdout.strip():
                    try:
                        parsed = self._parse_output(proc.stdout, proc.stderr, duration_ms)
                        _log.warning(
                            "[CLAUDE] exit=%d stdout_json=ok is_error=%s error=%r billing=%s",
                            proc.returncode, not parsed.success,
                            (parsed.error or "")[:200], parsed.billing_error,
                        )
                        return parsed
                    except Exception:
                        pass

                err = proc.stderr or proc.stdout or f"claude exited with code {proc.returncode}"
                _log.warning(
                    "[CLAUDE] exit=%d stderr=%r stdout=%r",
                    proc.returncode,
                    (proc.stderr or "")[:400],
                    (proc.stdout or "")[:400],
                )
                return ExecutorResult(
                    success=False,
                    error=err[:2000],
                    duration_ms=duration_ms,
                    billing_error=_is_billing_error(err),
                )

            _log.info("[CLAUDE] exit=0 duration_ms=%.0f stdout_len=%d", duration_ms, len(proc.stdout))
            return self._parse_output(proc.stdout, proc.stderr, duration_ms)

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - started) * 1000
            _log.error("[CLAUDE] timeout after %ds cwd=%r", timeout, cwd)
            return ExecutorResult(
                success=False,
                error=f"Timeout after {timeout}s",
                duration_ms=duration_ms,
                metadata={"timeout": True},
            )
        except FileNotFoundError:
            _log.error("[CLAUDE] binary not found: %s", self._bin)
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

        # modelUsage может быть более детальным. Ключи camelCase — контракт
        # текущего claude CLI (2.1.x: inputTokens/outputTokens); snake_case
        # оставлен для старых версий.
        model_usage = data.get("modelUsage", {})
        if model_usage and not input_tokens:
            for model_data in model_usage.values():
                input_tokens += model_data.get("inputTokens") or model_data.get("input_tokens") or 0
                output_tokens += model_data.get("outputTokens") or model_data.get("output_tokens") or 0

        error_text = data.get("api_error_status", "") if is_error else ""
        # claude CLI may embed billing errors in result text when is_error=True
        billing = is_error and _is_billing_error(error_text or result_text or stderr)

        return ExecutorResult(
            success=not is_error,
            output=result_text,
            error=error_text,
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
            billing_error=billing,
        )
