"""Fail-closed HTTP business action executor."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlparse

from voly.executor.base import Executor, ExecutorResult
from voly.sensing.schema import ActionReport


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that dials a pre-validated IP instead of re-resolving the host.

    Plain HTTPSConnection.connect() calls socket.create_connection((self.host, ...)),
    which re-resolves the hostname at connect time. That reopens a DNS-rebinding gap:
    the address checked as public and the address the socket actually opens to can
    differ if DNS answers change between the check and the connect. Pinning the
    validated IP for the TCP connection while still doing TLS SNI/cert verification
    against the original hostname closes that gap.
    """

    def __init__(self, host, *, pinned_ip: str, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # type: ignore[override]
        self.sock = self._create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if self._tunnel_host:
            self._tunnel()
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str) -> None:
        import ssl

        super().__init__(context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def https_open(self, req):  # type: ignore[no-untyped-def]
        def build(host, **kwargs):  # type: ignore[no-untyped-def]
            return _PinnedHTTPSConnection(host, pinned_ip=self._pinned_ip, **kwargs)

        return self.do_open(build, req, context=self._context)


def _resolve_validated_ip(host: str, resolver: Callable[..., list] = socket.getaddrinfo) -> str:
    try:
        addresses = resolver(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"cannot resolve HTTP action host: {host}") from exc
    if not addresses:
        raise ValueError(f"cannot resolve HTTP action host: {host}")
    pinned_ip: str | None = None
    for item in addresses:
        address = ipaddress.ip_address(item[4][0].split("%", 1)[0])
        if not address.is_global:
            raise ValueError(f"HTTP action host resolves to non-public address: {address}")
        if pinned_ip is None:
            pinned_ip = str(address)
    assert pinned_ip is not None
    return pinned_ip


class HttpActionExecutor(Executor):
    def __init__(self, config, *, resolver=socket.getaddrinfo, opener=None,
                 action_permission: str = "http_call", report_kind: str = "http_call") -> None:  # type: ignore[no-untyped-def]
        self.config = config
        self.resolver = resolver
        self._custom_opener = opener
        self.action_permission = action_permission
        self.report_kind = report_kind

    def _build_opener(self, pinned_ip: str):  # type: ignore[no-untyped-def]
        if self._custom_opener is not None:
            return self._custom_opener
        return urllib.request.build_opener(_NoRedirect(), _PinnedHTTPSHandler(pinned_ip))

    @property
    def name(self) -> str:
        return "http-action"

    def run(self, task: str, cwd: str | None = None, allowed_tools: list[str] | None = None,
            max_turns: int = 30, timeout: int = 300) -> ExecutorResult:
        del cwd, allowed_tools, max_turns
        cfg = self.config.business_executors
        if not cfg.enabled or self.action_permission not in cfg.allow:
            return ExecutorResult(False, error=f"{self.action_permission} business executor is disabled")
        try:
            action = json.loads(task)
            if not isinstance(action, dict):
                raise ValueError("HTTP action must be a JSON object")
            method = str(action.get("method") or "").upper()
            url = str(action.get("url") or "")
            idempotency_key = str(action.get("idempotency_key") or "")
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("HTTP action URL must be credential-free HTTPS")
            host = parsed.hostname.lower()
            if host not in set(cfg.http_allowed_hosts):
                raise ValueError(f"HTTP action host is not allowlisted: {host}")
            if method not in set(cfg.http_allowed_methods):
                raise ValueError(f"HTTP action method is not allowlisted: {method}")
            if not idempotency_key:
                raise ValueError("HTTP action requires idempotency_key")
            pinned_ip = _resolve_validated_ip(host, self.resolver)
            body = json.dumps(action.get("body") or {}).encode("utf-8")
            headers = {"Content-Type": "application/json", "Idempotency-Key": idempotency_key}
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            request_timeout = min(float(timeout), float(cfg.http_timeout_seconds))
            opener = self._build_opener(pinned_ip)
            with opener.open(request, timeout=request_timeout) as response:
                data = response.read(cfg.http_max_response_bytes + 1)
                if len(data) > cfg.http_max_response_bytes:
                    raise ValueError("HTTP action response exceeds configured limit")
                status = int(response.status)
            report = ActionReport(
                action_kind=self.report_kind, target=f"https://{host}{parsed.path}",
                request_summary=f"{method} {parsed.path or '/'}", result=f"HTTP {status}",
                metadata={"idempotency_key": idempotency_key},
            )
            return ExecutorResult(
                success=200 <= status < 300,
                output=report.result,
                error="" if 200 <= status < 300 else report.result,
                metadata={"action_report": report.to_dict()},
            )
        except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
            return ExecutorResult(False, error=str(exc))
