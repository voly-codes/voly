"""Bounded RSS/Atom polling connector using only the Python standard library."""

from __future__ import annotations

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from voly.sensing.connectors.base import SensingConnector
from voly.sensing.schema import Signal

MAX_FEED_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0


def _text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
    return ""


class RSSConnector(SensingConnector):
    name = "rss"

    def __init__(
        self,
        feeds: list[str],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        fetch: Callable[[str, float], bytes] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.feeds = list(feeds)
        self.timeout_seconds = timeout_seconds
        self._fetch = fetch or self._fetch_url
        self._now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _fetch_url(url: str, timeout: float) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"RSS feed URL must use http(s): {url!r}")
        request = urllib.request.Request(url, headers={"User-Agent": "VOLY/0.1 RSS"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_FEED_BYTES:
                raise ValueError(f"RSS feed exceeds {MAX_FEED_BYTES} bytes")
            body = response.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            raise ValueError(f"RSS feed exceeds {MAX_FEED_BYTES} bytes")
        return body

    def poll(self) -> list[Signal]:
        captured_at = self._now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        signals: list[Signal] = []
        for feed_url in self.feeds:
            root = ET.fromstring(self._fetch(feed_url, self.timeout_seconds))
            entries = [
                node for node in root.iter()
                if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
            ]
            for entry in entries:
                title = _text(entry, ("title",))
                body = _text(entry, ("description", "summary", "content"))
                entry_id = _text(entry, ("guid", "id", "link")) or title
                published = _text(entry, ("pubdate", "published", "updated"))
                identity = f"{feed_url}\n{entry_id}\n{published}"
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                signals.append(Signal(
                    signal_id=f"rss-{digest[:16]}",
                    source=self.name,
                    source_ref=f"{feed_url}#{entry_id}" if entry_id else feed_url,
                    captured_at=captured_at,
                    dedup_key=f"sha256:{digest}",
                    payload={
                        "title": title,
                        "body": body,
                        "raw": {"entry_id": entry_id, "published": published},
                    },
                    confidence=0.8 if entry_id else 0.5,
                ))
        return signals
