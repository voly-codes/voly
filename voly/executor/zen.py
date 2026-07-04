"""
ZenExecutor — file-capable agent via OpenCode Zen + CLI.

OpenCode Zen provides curated models through opencode.ai/zen/v1.
When the `opencode` CLI is available, Zen runs in agentic mode
with full Read/Write/Edit/Bash access. Falls back to API-only
(read-only) when CLI is not installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

from voly.executor.base import (
    Executor,
    ExecutorResult,
    _MIN_ATTEMPT_SECONDS,
    _extract_cli_error,
    _is_billing_error,
    _oc_event_error,
)
from voly.telemetry import _estimate_cost

logger = logging.getLogger(__name__)

# Models tried in order when a billing error is detected.
# Priority order:
#   1. OpenCode Zen free tier (opencode.ai pays, no user billing)
#   2. OpenCode Zen paid cheap models (opencode subscription)
#   3. User's own provider API keys (separate billing from Anthropic)
_FREE_MODEL_SEQUENCE: tuple[str, ...] = (
    # OpenCode free tier — zero cost
    "deepseek-v4-flash-free",
    "qwen3.6-plus-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
    "big-pickle",
    "north-mini-code-free",
    # Other provider APIs — uses user's own keys (OPENAI_API_KEY, DEEPSEEK_API_KEY)
    # opencode CLI routes these to the respective APIs, separate from Anthropic billing.
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
)


class ZenExecutor(Executor):
    """File-capable coding agent via OpenCode Zen CLI + API.

    When the configured model fails with a billing error (e.g. Anthropic credits
    exhausted), automatically retries with the next model in _FREE_MODEL_SEQUENCE
    until one succeeds or all are exhausted.
    """

    # Start with a free model — claude-sonnet-4-6 routes through Anthropic billing.
    DEFAULT_MODEL = "deepseek-v4-flash-free"

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

    def _models_to_try(self) -> list[str]:
        """Return ordered list of models to attempt: configured model first, then free fallbacks."""
        seen: set[str] = set()
        result: list[str] = []
        for m in (self._model, *_FREE_MODEL_SEQUENCE):
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

    def _run_cli(
        self,
        task: str,
        cwd: str | None = None,
        max_turns: int = 20,
        timeout: int = 600,
    ) -> ExecutorResult:
        """Agentic execution via `opencode run` with file access.

        Tries each model in sequence. On billing error, moves to the next free model.

        ``timeout`` is a TOTAL deadline for this call, shared across the model
        loop — each attempt gets the remaining time. Otherwise N billing-failed
        models × a full per-attempt timeout silently multiplies the caller's
        budget (8 models × 300s ≈ 40 min for a "300s" call).
        """
        deadline = time.monotonic() + timeout
        last_result: ExecutorResult | None = None

        for model in self._models_to_try():
            remaining = int(deadline - time.monotonic())
            if remaining < _MIN_ATTEMPT_SECONDS:
                if last_result is None:
                    return ExecutorResult(
                        success=False,
                        error=f"zen: {timeout}s deadline too short for any model attempt",
                        metadata={"mode": "cli", "provider": "opencode-zen", "timeout": True},
                    )
                logger.warning("zen._run_cli: %ds deadline exhausted, stopping model iteration", timeout)
                last_result.metadata["deadline_exhausted"] = True
                return last_result

            model_id = model if "/" in model else f"opencode/{model}"
            result = self._run_cli_one(task, model_id=model_id, cwd=cwd, max_turns=max_turns, timeout=remaining)
            last_result = result

            if result.success:
                return result
            if not result.billing_error:
                # Non-billing failure (timeout, parse error, etc.) — don't iterate models
                return result
            logger.warning(
                "zen._run_cli: billing error with model=%s, trying next free model", model
            )

        # All models exhausted — return last result (billing_error=True so chain can continue)
        assert last_result is not None
        return last_result

    def _run_cli_one(
        self,
        task: str,
        model_id: str,
        cwd: str | None = None,
        max_turns: int = 20,
        timeout: int = 600,
    ) -> ExecutorResult:
        """Single attempt with one model. Returns ExecutorResult with billing_error set."""
        cmd = ["opencode", "run", "--format", "json", "-m", model_id, task]

        logger.info("zen._run_cli_one model=%s cwd=%s", model_id, cwd)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, env={**os.environ},  # noqa: S603
                capture_output=True, text=True, timeout=timeout,
            )
            duration_ms = (time.monotonic() - started) * 1000

            logger.info(
                "zen._run_cli_one returncode=%d model=%s stdout=%r stderr=%r",
                proc.returncode, model_id,
                proc.stdout[:1000] if proc.stdout else "",
                proc.stderr[:500] if proc.stderr else "",
            )

            if proc.returncode != 0:
                error = _extract_cli_error(proc.stdout, proc.stderr, proc.returncode)
                logger.warning("zen._run_cli_one failed model=%s: %s", model_id, error)
                return ExecutorResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                    billing_error=_is_billing_error(error),
                    metadata={"mode": "cli", "model": model_id, "provider": "opencode-zen"},
                )

            return self._parse_json_events(proc.stdout, proc.stderr, duration_ms, model_id=model_id)
        except subprocess.TimeoutExpired:
            return ExecutorResult(
                success=False,
                error=f"opencode CLI timed out after {timeout}s",
                duration_ms=(time.monotonic() - started) * 1000,
                metadata={"mode": "cli", "model": model_id, "provider": "opencode-zen", "timeout": True},
            )

    def _parse_json_events(self, stdout: str, stderr: str, duration_ms: float, *, model_id: str = "") -> ExecutorResult:
        """Parse NDJSON event stream from `opencode run --format json`."""
        import json
        import re

        text_parts: list[str] = []
        error_parts: list[str] = []
        in_tok = out_tok = cost = num_turns = 0
        session_id = ""

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("zen: non-JSON stdout line: %r", line[:200])
                continue

            t_dbg = ev.get("type")
            logger.debug("zen: event type=%r name=%r keys=%s", t_dbg, ev.get("name"), list(ev.keys()))
            if t_dbg in ("step_finish", "cost", "usage", "summary"):
                logger.debug("zen: %s part=%r", t_dbg, ev.get("part"))

            err = _oc_event_error(ev)
            if err:
                logger.warning("zen: error event detected: %s", err)
                error_parts.append(err)
                continue

            t = ev.get("type", "")
            part = ev.get("part") or {}
            session_id = session_id or ev.get("sessionID") or ev.get("session_id") or ""

            if t == "text":
                # opencode v2: text lives inside part
                text = (
                    part.get("text") or part.get("content") or part.get("value")
                    or ev.get("text") or ""
                )
                if text:
                    text_parts.append(text)
            elif t == "assistant" and isinstance(ev.get("content"), list):
                # opencode v1 format
                for block in ev["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            elif t == "message" and "text" in ev:
                text_parts.append(ev["text"])
            elif t == "step_finish":
                num_turns += 1
                tokens = part.get("tokens") or {}
                if isinstance(tokens, dict):
                    in_tok += tokens.get("input") or 0
                    out_tok += tokens.get("output") or 0
                cost += part.get("cost") or part.get("costUsd") or 0
                logger.debug("zen: step_finish tokens in=%d out=%d cost=%s", in_tok, out_tok, cost)
            elif t in ("cost", "usage", "summary"):
                in_tok += ev.get("inputTokens") or ev.get("input_tokens") or 0
                out_tok += ev.get("outputTokens") or ev.get("output_tokens") or 0
                cost += ev.get("cost") or ev.get("costUsd") or 0
            elif t == "session":
                session_id = session_id or ev.get("id", "")

        used_model = model_id or self._model
        logger.info(
            "zen._parse_json_events: text_parts=%d error_parts=%d in_tok=%d out_tok=%d model=%s",
            len(text_parts), len(error_parts), in_tok, out_tok, used_model,
        )

        if error_parts and not text_parts:
            joined_error = "\n".join(error_parts)
            return ExecutorResult(
                success=False,
                error=joined_error,
                duration_ms=duration_ms,
                billing_error=_is_billing_error(joined_error),
                metadata={"mode": "cli", "model": used_model, "provider": "opencode-zen"},
            )

        if not text_parts:
            fallback = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', stdout).strip()
            logger.warning("zen: no text_parts, using raw fallback: %r", fallback[:300])
            text_parts = [fallback]

        if not cost and (in_tok or out_tok):
            cost = _estimate_cost(used_model, in_tok, out_tok)

        return ExecutorResult(
            success=True,
            output="\n\n".join(p for p in text_parts if p).strip(),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            duration_ms=duration_ms,
            num_turns=num_turns or 1,
            session_id=session_id,
            metadata={"mode": "cli", "model": used_model, "provider": "opencode-zen"},
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
                metadata={"mode": "api", "model": self._model, "provider": "opencode-zen"},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - started) * 1000
            return ExecutorResult(success=False, error=str(e), duration_ms=duration_ms)
