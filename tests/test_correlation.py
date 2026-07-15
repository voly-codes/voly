"""Correlation ID helpers and TaskEvent schema v3 field."""

from __future__ import annotations

import json
import logging

from voly.correlation import (
    CORRELATION_HEADER,
    CorrelationFilter,
    JsonLogFormatter,
    correlation_headers,
    ensure_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from voly.telemetry import TASK_EVENT_SCHEMA_VERSION, TaskEvent


def test_ensure_correlation_id_stable() -> None:
    set_correlation_id(None)
    a = ensure_correlation_id()
    b = ensure_correlation_id()
    assert a == b
    assert get_correlation_id() == a


def test_correlation_headers_forward() -> None:
    set_correlation_id("cid-42")
    headers = correlation_headers({"Authorization": "Bearer x"})
    assert headers[CORRELATION_HEADER] == "cid-42"
    assert headers["Authorization"] == "Bearer x"


def test_json_log_formatter_includes_correlation_id() -> None:
    set_correlation_id("cid-log")
    record = logging.LogRecord(
        name="voly.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    CorrelationFilter().filter(record)
    line = JsonLogFormatter().format(record)
    data = json.loads(line)
    assert data["correlation_id"] == "cid-log"
    assert data["msg"] == "hello"


def test_task_event_schema_v3_has_correlation_id() -> None:
    assert TASK_EVENT_SCHEMA_VERSION == 3
    ev = TaskEvent(
        task_id="t1",
        agent="developer",
        status="completed",
        correlation_id="cid-1",
    )
    assert ev.to_dict()["correlation_id"] == "cid-1"
    assert ev.to_dict()["schema_version"] == 3
