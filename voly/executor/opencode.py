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

import logging

from voly.executor.base import (
    Executor,
    ExecutorResult,
    _MIN_ATTEMPT_SECONDS,
    _build_opencode_run_cmd,
    _extract_cli_error,
    _fold_retry_costs,
    _is_billing_error,
    _oc_event_error,
)
from voly.telemetry import _estimate_cost

_log = logging.getLogger(__name__)

# Models tried via opencode-go when a billing error is detected.
# 1. OpenCode free tier, 2. User's own provider keys (OPENAI/DEEPSEEK).
_GO_FREE_MODEL_SEQUENCE: tuple[str, ...] = (
    "mimo-v2.5-free",
    "qwen3.6-plus-free",
    "nemotron-3-ultra-free",
    "big-pickle",
    "north-mini-code-free",
    "deepseek-v4-flash-free",
    # Uses OPENAI_API_KEY / DEEPSEEK_API_KEY from environment
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
)


class OpenCodeExecutor(Executor):
    """Agentic code executor via OpenCode Go CLI or API.

    On billing error, automatically retries with free models from _GO_FREE_MODEL_SEQUENCE.
    """

    DEFAULT_MODEL = "mimo-v2.5-free"

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

    def _models_to_try(self) -> list[str]:
        """Return ordered model list: configured model first, then free fallbacks."""
        seen: set[str] = set()
        result: list[str] = []
        for m in (self._model, *_GO_FREE_MODEL_SEQUENCE):
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

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
        """Run via opencode CLI with free model fallback on billing error.

        ``timeout`` is a TOTAL deadline shared across the model loop — each
        attempt gets the remaining time (see ZenExecutor._run_cli for rationale).
        """
        deadline = time.monotonic() + timeout
        # Failed billing attempts we moved past; spend folded into the returned
        # result (see _fold_retry_costs) so retries don't vanish from telemetry.
        abandoned: list[ExecutorResult] = []

        for model in self._models_to_try():
            remaining = int(deadline - time.monotonic())
            if remaining < _MIN_ATTEMPT_SECONDS:
                if not abandoned:
                    return ExecutorResult(
                        success=False,
                        error=f"opencode: {timeout}s deadline too short for any model attempt",
                        metadata={"mode": "cli", "provider": "opencode-go", "timeout": True},
                    )
                _log.warning("opencode._run_cli: %ds deadline exhausted, stopping model iteration", timeout)
                last = abandoned.pop()
                last.metadata["deadline_exhausted"] = True
                return _fold_retry_costs(last, abandoned)

            model_id = model if "/" in model else f"opencode-go/{model}"
            result = self._run_cli_one(task, model_id=model_id, cwd=cwd, timeout=remaining)

            if result.success:
                return _fold_retry_costs(result, abandoned)
            if not result.billing_error:
                return _fold_retry_costs(result, abandoned)
            abandoned.append(result)
            _log.warning("opencode._run_cli: billing error with model=%s, trying next", model)

        assert abandoned
        last = abandoned.pop()
        return _fold_retry_costs(last, abandoned)

    def _run_cli_one(
        self,
        task: str,
        model_id: str,
        cwd: str | None = None,
        timeout: int = 600,
    ) -> ExecutorResult:
        work_dir = os.path.abspath(os.path.expanduser(cwd)) if cwd else None
        cmd = _build_opencode_run_cmd(task, model_id=model_id, cwd=work_dir)

        _log.info("opencode._run_cli_one model=%s cwd=%s cmd=%s", model_id, work_dir, cmd[:8])
        started = time.monotonic()
        try:
            # UTF-8 explicit: CLI output is UTF-8 regardless of OS locale (see
            # claude_code.py for the corruption/UnicodeDecodeError this avoids).
            proc = subprocess.run(
                cmd,
                cwd=work_dir,
                env={**os.environ},
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            duration_ms = (time.monotonic() - started) * 1000

            if proc.returncode != 0:
                error = _extract_cli_error(proc.stdout, proc.stderr, proc.returncode)
                _log.warning("opencode._run_cli_one failed model=%s: %s", model_id, error)
                return ExecutorResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                    billing_error=_is_billing_error(error),
                    metadata={"mode": "cli", "model": model_id, "provider": "opencode-go"},
                )

            return self._parse_json_events(proc.stdout, proc.stderr, duration_ms, model_id=model_id)

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(
                success=False,
                error=f"opencode CLI timed out after {timeout}s",
                duration_ms=duration_ms,
                metadata={"mode": "cli", "model": model_id, "provider": "opencode-go", "timeout": True},
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

    def _parse_json_events(self, stdout: str, stderr: str, duration_ms: float, *, model_id: str = "") -> ExecutorResult:
        """Parse NDJSON event stream from `opencode run --format json`."""
        import json
        import re

        text_parts: list[str] = []
        error_parts: list[str] = []
        input_tokens = output_tokens = cost = num_turns = 0
        session_id = ""
        used_model = model_id or self._model

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
            joined_error = "\n".join(error_parts)
            return ExecutorResult(
                success=False,
                error=joined_error,
                duration_ms=duration_ms,
                billing_error=_is_billing_error(joined_error),
                metadata={"mode": "cli", "model": used_model, "provider": "opencode-go"},
            )

        if not text_parts:
            text_parts = [re.sub(r'\x1b\[[0-9;]*m', '', stdout).strip()]

        if not cost and (input_tokens or output_tokens):
            cost = _estimate_cost(used_model, input_tokens, output_tokens)

        return ExecutorResult(
            success=True,
            output="\n\n".join(p for p in text_parts if p).strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            num_turns=num_turns or 1,
            session_id=session_id,
            metadata={"mode": "cli", "model": used_model, "provider": "opencode-go"},
        )
