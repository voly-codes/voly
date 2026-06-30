"""
ZenExecutor — file-capable agent via OpenCode Zen + CLI.

OpenCode Zen provides curated models through opencode.ai/zen/v1.
When the `opencode` CLI is available, Zen runs in agentic mode
with full Read/Write/Edit/Bash access. Falls back to API-only
(read-only) when CLI is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from codeops.executor.base import Executor, ExecutorResult


class ZenExecutor(Executor):
    """File-capable coding agent via OpenCode Zen CLI + API."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self._base_url = base_url or os.getenv("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen")
        self._api_key = api_key or os.getenv("OPENCODE_API_KEY", "")
        self._model = model
        self._use_cli = shutil.which("opencode") is not None

    @property
    def name(self) -> str:
        return "zen"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 20,
        timeout: int = 600,
        system: str | None = None,
    ) -> ExecutorResult:
        if self._use_cli:
            return self._run_cli(task, cwd=cwd, max_turns=max_turns, timeout=timeout)
        return self._run_api(task, system=system, timeout=timeout)

    def _run_cli(
        self,
        task: str,
        cwd: str | None = None,
        max_turns: int = 20,
        timeout: int = 600,
    ) -> ExecutorResult:
        """Agentic execution via `opencode run` with file access."""
        cmd = ["opencode", "run", task]
        env = {**os.environ}
        if self._model:
            env["OPENCODE_MODEL"] = self._model
        env["OPENCODE_PROVIDER"] = "opencode-zen"
        env["OPENCODE_BASE_URL"] = self._base_url

        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, env=env,
                capture_output=True, text=True, timeout=timeout,
            )
            duration_ms = (time.monotonic() - started) * 1000

            if proc.returncode != 0:
                return ExecutorResult(
                    success=False,
                    error=proc.stderr or f"opencode exited with code {proc.returncode}",
                    duration_ms=duration_ms,
                )

            output = proc.stdout or ""
            return ExecutorResult(
                success=True,
                output=output,
                duration_ms=duration_ms,
                num_turns=max_turns,
                metadata={"mode": "cli", "model": self._model, "provider": "opencode-zen"},
            )
        except subprocess.TimeoutExpired:
            return ExecutorResult(
                success=False,
                error=f"opencode CLI timed out after {timeout}s",
                duration_ms=(time.monotonic() - started) * 1000,
            )

    def _run_api(
        self,
        task: str,
        system: str | None = None,
        timeout: int = 180,
    ) -> ExecutorResult:
        """Fallback: text-only API call (read-only, no file access)."""
        try:
            from openai import OpenAI
        except ImportError:
            return ExecutorResult(success=False, error="openai package not installed")

        started = time.monotonic()
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": task})

        try:
            client = OpenAI(api_key=self._api_key or "dummy", base_url=self._base_url)
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                timeout=timeout,
                temperature=0.0,
            )
            duration_ms = (time.monotonic() - started) * 1000
            content = response.choices[0].message.content or ""
            usage = response.usage

            return ExecutorResult(
                success=True,
                output=content,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                duration_ms=duration_ms,
                num_turns=1,
                metadata={"mode": "api", "model": self._model, "provider": "opencode-zen"},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)
