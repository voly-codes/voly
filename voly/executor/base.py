from __future__ import annotations

import json
import os
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


# Minimum remaining seconds worth starting another CLI attempt with. Model-
# fallback loops (zen/opencode) treat the caller's `timeout` as a TOTAL deadline
# shared across attempts; below this floor the loop stops instead of launching
# a subprocess that would be killed almost immediately.
_MIN_ATTEMPT_SECONDS = 10


def _build_opencode_run_cmd(
    task: str,
    *,
    model_id: str,
    cwd: str | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build ``opencode run`` argv with project directory bound via ``--dir``.

    Subprocess ``cwd`` alone is not enough: OpenCode resolves the project root
    (git root / session dir) independently and may write outside the sandbox.
    ``--dir`` pins the workspace explicitly (see ``opencode run --help``).
    """
    cmd = ["opencode", "run", "--format", "json", "-m", model_id]
    if extra_args:
        cmd.extend(extra_args)
    if cwd:
        cmd.extend(["--dir", os.path.abspath(os.path.expanduser(cwd))])
    cmd.append(task)
    return cmd


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


def _fold_retry_costs(final: ExecutorResult, abandoned: list[ExecutorResult]) -> ExecutorResult:
    """Fold spend of abandoned model attempts into the returned result.

    Model-fallback loops (zen/opencode) discard failed attempts' results, but
    the tokens/cost those attempts burned are real spend — without folding, the
    task's FinOps numbers silently under-report on retries. ``retry_count`` /
    ``retry_cost_usd`` in metadata isolate the retry share so dashboards can
    show waste without double counting (``cost_usd`` is already the total).
    """
    if not abandoned:
        return final
    retry_cost = sum(r.cost_usd for r in abandoned)
    final.cost_usd = round(final.cost_usd + retry_cost, 6)
    final.input_tokens += sum(r.input_tokens for r in abandoned)
    final.output_tokens += sum(r.output_tokens for r in abandoned)
    final.metadata["retry_count"] = len(abandoned)
    final.metadata["retry_cost_usd"] = round(retry_cost, 6)
    return final


def _is_billing_error(error: str) -> bool:
    """True when the error means the provider is out of budget/quota.

    Delegates to the semantic classifier (voly.ai_gateway.error_classifier),
    which fires only for terminal quota/account states — a transient HTTP 429
    rate-limit is deliberately NOT treated as a billing error, so the runner
    won't skip to the next executor for a simple per-minute throttle.
    """
    from voly.ai_gateway.error_classifier import is_terminal_billing_error

    return is_terminal_billing_error(error)


def classify_failure(result: "ExecutorResult") -> str | None:
    """Classify a failed ExecutorResult into an error class, or None on success.

    Feeds the unrecognized-error metric (risk R4): executor billing detection is
    signal-table-based, so a reworded CLI error silently stops triggering the
    billing fallback chain. Failures that carry no recognized marker are tagged
    ``"unrecognized"`` in telemetry — a growing share of those means the CLI
    output format drifted and the signal tables need updating.

    Explicit markers set by the executor win over re-classification of the text:
    ``billing`` / ``not_available`` / ``timeout`` (metadata), then the semantic
    classifier's ErrorType, else ``"unrecognized"``.
    """
    if result.success:
        return None
    if result.billing_error:
        return "billing"
    if result.not_available:
        return "not_available"
    if result.metadata.get("timeout") or result.metadata.get("deadline_exhausted"):
        return "timeout"
    from voly.ai_gateway.error_classifier import classify_provider_error

    return classify_provider_error(None, result.error or "") or "unrecognized"


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
