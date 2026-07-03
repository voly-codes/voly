"""Tests for pipeline HTTP server."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from codeops.config import VOLYConfig
from codeops.pipeline_server import create_pipeline_handler


def _make_handler(token: str = ""):
    config = VOLYConfig()
    handler_class = create_pipeline_handler(config, token=token)
    handler = handler_class.__new__(handler_class)
    handler.headers = {}
    handler.wfile = MagicMock()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler


def test_pipeline_handler_health() -> None:
    handler = _make_handler()
    handler.path = "/health"
    handler.do_GET()

    written = handler.wfile.write.call_args[0][0]
    data = json.loads(written.decode())
    assert data["status"] == "ok"


def test_pipeline_handler_unauthorized() -> None:
    handler = _make_handler(token="secret")
    handler.path = "/run"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = MagicMock(read=lambda n: b"{}")
    handler.do_POST()

    written = handler.wfile.write.call_args[0][0]
    data = json.loads(written.decode())
    assert data["error"] == "unauthorized"
