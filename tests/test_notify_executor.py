from __future__ import annotations

import json

from voly.config import VOLYConfig
from voly.executor.notify import NotifyExecutor


def _resolver(*args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


class _Response:
    status = 204
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, size): return b""


class _Opener:
    def __init__(self): self.request = None
    def open(self, request, timeout): self.request = request; return _Response()


def test_notify_webhook_is_allowlisted_and_redacted() -> None:
    config = VOLYConfig()
    config.business_executors.enabled = True
    config.business_executors.allow = ["notify"]
    config.business_executors.http_allowed_hosts = ["hooks.example.com"]
    opener = _Opener()
    result = NotifyExecutor(config, resolver=_resolver, opener=opener).run(json.dumps({
        "url": "https://hooks.example.com/services/team?token=secret",
        "message": "Competitor pricing alert",
        "idempotency_key": "notify-opt-1",
    }))
    assert result.success is True
    assert json.loads(opener.request.data) == {"text": "Competitor pricing alert"}
    assert result.metadata["action_report"]["action_kind"] == "notify"
    assert "token" not in result.metadata["action_report"]["target"]


def test_notify_requires_enablement_message_and_key() -> None:
    assert NotifyExecutor(VOLYConfig()).run("{}").success is False
    config = VOLYConfig()
    config.business_executors.enabled = True
    config.business_executors.allow = ["notify"]
    config.business_executors.http_allowed_hosts = ["hooks.example.com"]
    executor = NotifyExecutor(config, resolver=_resolver)
    assert executor.run(json.dumps({"url": "https://hooks.example.com/x", "message": ""})).success is False
