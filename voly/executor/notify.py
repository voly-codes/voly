"""Single v1 notification transport: an allowlisted HTTPS webhook."""

from __future__ import annotations

import json
import socket

from voly.executor.base import Executor, ExecutorResult
from voly.executor.http_action import HttpActionExecutor


class NotifyExecutor(Executor):
    def __init__(self, config, *, resolver=socket.getaddrinfo, opener=None) -> None:  # type: ignore[no-untyped-def]
        self.http = HttpActionExecutor(
            config, resolver=resolver, opener=opener,
            action_permission="notify", report_kind="notify",
        )

    @property
    def name(self) -> str:
        return "notify"

    def run(self, task: str, cwd: str | None = None, allowed_tools: list[str] | None = None,
            max_turns: int = 30, timeout: int = 300) -> ExecutorResult:
        try:
            action = json.loads(task)
            if not isinstance(action, dict):
                raise ValueError("notify action must be a JSON object")
            message = str(action.get("message") or "").strip()
            if not message or len(message) > 10_000:
                raise ValueError("notify message must contain 1-10000 characters")
            request = {
                "method": "POST",
                "url": action.get("url"),
                "body": {"text": message},
                "idempotency_key": action.get("idempotency_key"),
            }
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return ExecutorResult(False, error=str(exc))
        return self.http.run(json.dumps(request), timeout=timeout)
