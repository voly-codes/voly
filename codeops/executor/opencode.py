"""
OpenCodeExecutor — agentic code executor via OpenCode Go.

OpenCode Go is an agentic coding assistant with tool access (like Claude Code CLI).
It can read/write files, run bash commands, and produce real changes.

Endpoint: OPENCODE_BASE_URL=https://opencode.ai/zen/go (OpenAI-compatible with tool use)

Falls back to text-only mode if tool use is not supported by the endpoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from codeops.executor.base import Executor, ExecutorResult, _extract_cli_error
from codeops.telemetry import _estimate_cost


class OpenCodeExecutor(Executor):
    """Agentic code executor via OpenCode Go CLI or API."""

    DEFAULT_MODEL = "deepseek-v4-flash"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        use_cli: bool | None = None,
    ):
        self._base_url = base_url or os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go")
        self._api_key = api_key or os.getenv("OPENCODE_API_KEY", "")
        self._model = model
        # Auto-detect CLI vs API mode
        self._use_cli = use_cli if use_cli is not None else bool(shutil.which("opencode"))

    @property
    def name(self) -> str:
        return "opencode"

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
        """Run via opencode CLI: `opencode run --format json -m provider/model <message>`."""
        model_id = self._model
        if model_id and "/" not in model_id:
            model_id = f"opencode-go/{model_id}"
        cmd = ["opencode", "run", "--format", "json"]
        if model_id:
            cmd += ["-m", model_id]
        cmd.append(task)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env={**os.environ},
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = (time.monotonic() - started) * 1000

            if proc.returncode != 0:
                error = _extract_cli_error(proc.stdout, proc.stderr, proc.returncode)
                return ExecutorResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                    metadata={"mode": "cli", "model": self._model, "provider": "opencode-go"},
                )

            return self._parse_json_events(proc.stdout, proc.stderr, duration_ms)

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(
                success=False,
                error=f"opencode CLI timed out after {timeout}s",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            self._use_cli = False
            return self._run_api(task, timeout=timeout)

    def _run_api(
        self,
        task: str,
        system: str | None = None,
        timeout: int = 120,
    ) -> ExecutorResult:
        """Run via OpenAI-compatible API (text generation only)."""
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
                metadata={"mode": "api", "model": self._model, "provider": "opencode-go"},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)

    def _parse_json_events(self, stdout: str, stderr: str, duration_ms: float) -> ExecutorResult:
        """Parse NDJSON event stream from `opencode run --format json`."""
        import json
        import re
        from codeops.executor.base import _oc_event_error

        text_parts: list[str] = []
        error_parts: list[str] = []
        input_tokens = output_tokens = cost = num_turns = 0
        session_id = ""

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            err = _oc_event_error(ev)
            if err:
                error_parts.append(err)
                continue

            t = ev.get("type", "")
            part = ev.get("part") or {}
            session_id = session_id or ev.get("sessionID") or ev.get("session_id") or ""

            if t == "text":
                text = (
                    part.get("text") or part.get("content") or part.get("value")
                    or ev.get("text") or ""
                )
                if text:
                    text_parts.append(text)
            elif t == "assistant" and isinstance(ev.get("content"), list):
                for block in ev["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            elif t == "message" and "text" in ev:
                text_parts.append(ev["text"])
            elif t == "step_finish":
                num_turns += 1
                tokens = part.get("tokens") or {}
                if isinstance(tokens, dict):
                    input_tokens += tokens.get("input") or 0
                    output_tokens += tokens.get("output") or 0
                cost += part.get("cost") or part.get("costUsd") or 0
            elif t in ("cost", "usage", "summary"):
                input_tokens += ev.get("inputTokens") or ev.get("input_tokens") or 0
                output_tokens += ev.get("outputTokens") or ev.get("output_tokens") or 0
                cost += ev.get("cost") or ev.get("costUsd") or 0
            elif t == "session":
                session_id = session_id or ev.get("id", "")

        if error_parts and not text_parts:
            return ExecutorResult(
                success=False,
                error="\n".join(error_parts),
                duration_ms=duration_ms,
                metadata={"mode": "cli", "model": self._model, "provider": "opencode-go"},
            )

        if not text_parts:
            text_parts = [re.sub(r'\x1b\[[0-9;]*m', '', stdout).strip()]

        if not cost and (input_tokens or output_tokens):
            cost = _estimate_cost(self._model, input_tokens, output_tokens)

        return ExecutorResult(
            success=True,
            output="\n\n".join(p for p in text_parts if p).strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            num_turns=num_turns or 1,
            session_id=session_id,
            metadata={"mode": "cli", "model": self._model, "provider": "opencode-go"},
        )
