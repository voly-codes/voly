from __future__ import annotations

import json

from voly.config import VOLYConfig
from voly.executor.http_action import (
    HttpActionExecutor,
    _PinnedHTTPSConnection,
    _PinnedHTTPSHandler,
)


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


def test_pinned_https_connection_dials_validated_ip_not_hostname() -> None:
    """Regression for DNS-rebinding: the socket must connect to the IP that was
    validated as public, not re-resolve the hostname at connect time (which
    would let a rebinding attacker swap in a private address after the check).
    """

    class _FakeSocket:
        def setsockopt(self, *args): pass

    class _FakeContext:
        def __init__(self): self.wrap_calls = []
        def wrap_socket(self, sock, server_hostname):
            self.wrap_calls.append((sock, server_hostname))
            return sock

    dial_calls = []

    def fake_create_connection(address, timeout, source_address):
        dial_calls.append(address)
        return _FakeSocket()

    conn = _PinnedHTTPSConnection("api.example.com", pinned_ip="93.184.216.34", timeout=5)
    conn._create_connection = fake_create_connection
    conn._context = _FakeContext()
    conn.connect()

    assert dial_calls == [("93.184.216.34", conn.port)]
    assert conn._context.wrap_calls == [(conn.sock, "api.example.com")]


def test_http_action_default_opener_pins_resolved_ip() -> None:
    executor = HttpActionExecutor(_config(), resolver=_resolver)
    opener = executor._build_opener("93.184.216.34")
    handler = next(h for h in opener.handlers if isinstance(h, _PinnedHTTPSHandler))
    assert handler._pinned_ip == "93.184.216.34"


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
