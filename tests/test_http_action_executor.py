from __future__ import annotations

import json

from voly.config import VOLYConfig
from voly.executor.http_action import HttpActionExecutor


def _config() -> VOLYConfig:
    config = VOLYConfig()
    config.business_executors.enabled = True
    config.business_executors.allow = ["http_call"]
    config.business_executors.http_allowed_hosts = ["api.example.com"]
    return config


def _resolver(host, port, type):  # type: ignore[no-untyped-def]
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


class _Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, size): return b'{"ok":true}'


class _Opener:
    def __init__(self): self.request = None
    def open(self, request, timeout):  # type: ignore[no-untyped-def]
        self.request = request
        return _Response()


def test_http_action_requires_explicit_enablement() -> None:
    result = HttpActionExecutor(VOLYConfig()).run("{}")
    assert result.success is False
    assert "disabled" in result.error


def test_http_action_blocks_private_resolution() -> None:
    result = HttpActionExecutor(
        _config(), resolver=lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))]
    ).run(json.dumps({"method": "POST", "url": "https://api.example.com/x", "idempotency_key": "k"}))
    assert result.success is False
    assert "non-public" in result.error


def test_http_action_sends_bounded_idempotent_request() -> None:
    opener = _Opener()
    result = HttpActionExecutor(_config(), resolver=_resolver, opener=opener).run(json.dumps({
        "method": "PATCH", "url": "https://api.example.com/v1/deals/123?secret=no-log",
        "idempotency_key": "decision-opt-1", "body": {"status": "won"},
    }))
    assert result.success is True
    assert opener.request.get_header("Idempotency-key") == "decision-opt-1"
    report = result.metadata["action_report"]
    assert report["target"] == "https://api.example.com/v1/deals/123"
    assert "secret" not in report["target"]


def test_http_action_rejects_host_method_and_missing_key() -> None:
    executor = HttpActionExecutor(_config(), resolver=_resolver)
    for action in (
        {"method": "POST", "url": "https://evil.example/x", "idempotency_key": "k"},
        {"method": "GET", "url": "https://api.example.com/x", "idempotency_key": "k"},
        {"method": "POST", "url": "https://api.example.com/x"},
    ):
        assert executor.run(json.dumps(action)).success is False


def test_business_executor_config_is_fail_closed(monkeypatch) -> None:
    from voly.config._parser import _parse_config

    monkeypatch.delenv("VOLY_BUSINESS_EXECUTORS_ENABLED", raising=False)
    assert _parse_config({}).business_executors.enabled is False
    config = _parse_config({"business_executors": {
        "enabled": True, "allow": ["http_call"],
        "http": {"allowed_hosts": ["API.EXAMPLE.COM"], "allowed_methods": ["patch"]},
    }})
    assert config.business_executors.http_allowed_hosts == ["api.example.com"]
    assert config.business_executors.http_allowed_methods == ["PATCH"]
