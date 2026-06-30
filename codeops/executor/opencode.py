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

from codeops.executor.base import Executor, ExecutorResult


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
        """Run via opencode CLI: `opencode run <message>`.

        Message is a positional argument — NOT stdin.
        Output is plain text with ANSI codes stripped.
        """
        cmd = ["opencode", "run", task]

        env = {**os.environ}
        if self._model:
            env["OPENCODE_MODEL"] = self._model
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
                    error=proc.stderr or f"opencode exited with code {proc.returncode}",
                    duration_ms=duration_ms,
                    metadata={"mode": "cli"},
                )

            import re
            # stdout holds the assistant reply; stderr has progress/model info
            output = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', proc.stdout).strip()
            if not output:
                # Some versions write to stderr; strip ANSI and use last non-empty line
                lines = [re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', l).strip()
                         for l in proc.stderr.splitlines() if l.strip()]
                output = lines[-1] if lines else ""

            return ExecutorResult(
                success=True,
                output=output,
                duration_ms=duration_ms,
                metadata={"mode": "cli", "provider": "opencode-go"},
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(
                success=False,
                error=f"opencode CLI timed out after {timeout}s",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            # CLI not found — fall back to API
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

            return ExecutorResult(
                success=True,
                output=content,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
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

        text_parts: list[str] = []
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

            t = ev.get("type", "")
            # Assistant text content
            if t == "assistant" and isinstance(ev.get("content"), list):
                for block in ev["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            # Plain text events (older format)
            elif t in ("text", "message") and "text" in ev:
                text_parts.append(ev["text"])
            # Usage / cost summary
            elif t in ("cost", "usage", "summary"):
                input_tokens += ev.get("input_tokens", 0) or 0
                output_tokens += ev.get("output_tokens", 0) or 0
                cost += ev.get("cost", 0) or 0
                num_turns += ev.get("turns", 0) or 0
                session_id = session_id or ev.get("session_id", "")
            elif t == "session":
                session_id = session_id or ev.get("id", "")

        # Fallback: if no structured text, strip ANSI and use raw stdout
        if not text_parts:
            text_parts = [re.sub(r'\x1b\[[0-9;]*m', '', stdout).strip()]

        return ExecutorResult(
            success=True,
            output="\n\n".join(p for p in text_parts if p).strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            num_turns=num_turns or 1,
            session_id=session_id,
            metadata={"mode": "cli", "provider": "opencode-go"},
        )
