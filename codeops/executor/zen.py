"""
ZenExecutor — analysis, planning, and code review via OpenCode Zen.

OpenCode Zen is a fast reasoning model optimized for:
  - Architecture analysis
  - Code review
  - Planning / task decomposition
  - Technical documentation

Endpoint: OPENCODE_ZEN_BASE_URL (OpenAI-compatible)
"""

from __future__ import annotations

import os
import time

from codeops.executor.base import Executor, ExecutorResult


class ZenExecutor(Executor):
    """Analysis and planning via OpenCode Zen (OpenAI-compatible)."""

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

    @property
    def name(self) -> str:
        return "zen"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 1,
        timeout: int = 180,
        system: str | None = None,
    ) -> ExecutorResult:
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
                metadata={"model": self._model, "provider": "zen"},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)
