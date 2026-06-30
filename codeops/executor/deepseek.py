"""
DeepSeekExecutor — code generation via DeepSeek API (OpenAI-compatible).

Best for:
  - TypeScript / React component generation
  - Code refactoring and transformation
  - SQL / Python scripts
  - Fast, cheap code-heavy tasks

Models:
  deepseek-chat          — general, fast ($0.27/$1.10 per 1M)
  deepseek-coder         — code-optimized
  deepseek-reasoner      — complex reasoning (R1)
"""

from __future__ import annotations

import os
import time

from codeops.executor.base import Executor, ExecutorResult
from codeops.telemetry import _estimate_cost


class DeepSeekExecutor(Executor):
    """Code generation via DeepSeek API (OpenAI-compatible)."""

    DEFAULT_MODEL = "deepseek-chat"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self._base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "deepseek"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 1,
        timeout: int = 120,
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
            in_tok = usage.prompt_tokens if usage else 0
            out_tok = usage.completion_tokens if usage else 0

            return ExecutorResult(
                success=True,
                output=content,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=_estimate_cost(self._model, in_tok, out_tok),
                duration_ms=duration_ms,
                num_turns=1,
                metadata={"model": self._model, "provider": "deepseek"},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)
