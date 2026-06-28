"""
MiMoExecutor — дешёвый текстовый агент через MiMo (OpenAI-совместимый).

Не выполняет код, только генерирует текст. Использовать для:
  - генерации migration scripts
  - анализа diff
  - code review (текстовый)

НЕ использовать для задач требующих Read/Write/Bash.
"""

from __future__ import annotations

import os
import time

from codeops.executor.base import Executor, ExecutorResult


class MiMoExecutor(Executor):
    """Дешёвый OpenAI-совместимый агент через MiMo API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "mimo-v2.5",
    ):
        self._base_url = base_url or os.getenv("MIMO_BASE_URL_OPENAI", "https://token-plan-sgp.xiaomimimo.com/v1")
        self._api_key = api_key or os.getenv("MIMO_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "mimo"

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 1,
        timeout: int = 120,
    ) -> ExecutorResult:
        try:
            from openai import OpenAI
        except ImportError:
            return ExecutorResult(success=False, error="openai package not installed")

        started = time.monotonic()
        try:
            client = OpenAI(api_key=self._api_key or "dummy", base_url=self._base_url)
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": task}],
                timeout=timeout,
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
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)
