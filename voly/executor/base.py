from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WorkReport:
    """Структурированный мини-отчёт о выполненной задаче."""
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "files_changed": self.files_changed,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "actions": self.actions,
        }


@dataclass
class ExecutorResult:
    success: bool
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0
    num_turns: int = 0
    session_id: str = ""
    metadata: dict = field(default_factory=dict)
    report: WorkReport | None = None
    billing_error: bool = False
    # Set True when executor service is unreachable (e.g. wrangler dev not running).
    # AgentRunner treats this like billing_error: skip to next in BILLING_FALLBACK_CHAIN.
    not_available: bool = False


_BILLING_PATTERNS = (
    # Anthropic
    "credit balance is too low", "credit_balance_too_low", "insufficient credits",
    # DeepSeek
    "insufficient balance",
    # OpenAI
    "exceeded your current quota", "insufficient_quota",
    # Generic HTTP
    "402", "payment required", "billing",
)


def _is_billing_error(error: str) -> bool:
    low = error.lower()
    return any(p in low for p in _BILLING_PATTERNS)


def _oc_event_error(ev: dict) -> str | None:
    """Extract error string from an opencode JSON event, or None if not an error event.

    Handles opencode formats:
      {"type":"error", "error":{"name":"...", "data":{"message":"...", "ref":"..."}}}
      {"type":"error", "message":"..."}
      {"name":"SomeError", "data":{"message":"...", "ref":"..."}}
    """
    def _extract(obj: object) -> tuple[str, str]:
        """Returns (message, ref) from any error-shaped object."""
        if isinstance(obj, str):
            return obj, ""
        if not isinstance(obj, dict):
            return str(obj), ""
        # opencode nested: {"name":..., "data":{"message":..., "ref":...}}
        data = obj.get("data")
        if isinstance(data, dict):
            msg = data.get("message") or data.get("text") or obj.get("name", "error")
            ref = data.get("ref", "")
            return str(msg), str(ref)
        # flat: {"message":..., "ref":...}
        msg = obj.get("message") or obj.get("text") or obj.get("name") or json.dumps(obj, ensure_ascii=False)
        ref = obj.get("ref", "")
        return str(msg), str(ref)

    t = ev.get("type", "")
    name = ev.get("name", "")

    if t == "error":
        inner = ev.get("error") or ev.get("message") or ev
        msg, ref = _extract(inner)
        return f"{msg} ({ref})" if ref else msg

    if name and ("error" in name.lower() or "Error" in name):
        msg, ref = _extract(ev)
        return f"{msg} ({ref})" if ref else msg

    return None


def _extract_cli_error(stdout: str, stderr: str, returncode: int) -> str:
    """Extract a meaningful error from opencode CLI output (JSON or plain text)."""
    messages: list[str] = []

    for source in (stdout, stderr):
        for line in source.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                err = _oc_event_error(ev)
                if err:
                    messages.append(err)
            except json.JSONDecodeError:
                clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line)
                if clean:
                    messages.append(clean)
        if messages:
            break

    if messages:
        return "\n".join(messages)
    return f"opencode exited with code {returncode}"


class Executor(ABC):
    @abstractmethod
    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
        timeout: int = 300,
    ) -> ExecutorResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
