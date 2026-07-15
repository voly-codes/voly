"""Request/run correlation ID for logs, API, and Cloudflare Worker calls.

Aligned with Cloudflare Workers Logs practice: emit a stable id on every hop so
Workers custom logs and VOLY TaskEvents can be filtered together
(see cloudflare-docs Workers observability / custom logs).

Headers accepted (first wins):
  X-Correlation-ID, X-Request-ID, cf-ray (read-only fallback is not used as our id)
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-ID"
_ALT_HEADERS = ("X-Request-ID", "x-correlation-id", "x-request-id")

_correlation_id: ContextVar[str | None] = ContextVar("voly_correlation_id", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set((value or "").strip() or None)


def ensure_correlation_id(explicit: str | None = None) -> str:
    """Return explicit or current id, generating one if missing."""
    cid = (explicit or "").strip() or get_correlation_id()
    if not cid:
        cid = new_correlation_id()
    set_correlation_id(cid)
    return cid


def correlation_id_from_headers(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    # Case-insensitive lookup
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    for key in ("x-correlation-id", "x-request-id"):
        val = (lower.get(key) or "").strip()
        if val:
            return val
    return None


def correlation_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers to forward to CF Workers / remote services."""
    out = dict(extra or {})
    cid = get_correlation_id()
    if cid:
        out[CORRELATION_HEADER] = cid
    return out


class CorrelationFilter(logging.Filter):
    """Inject correlation_id into LogRecord for formatters."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"  # type: ignore[attr-defined]
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line — easy to ship alongside Workers Logs."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None) or get_correlation_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
