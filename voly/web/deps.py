"""Shared app state and dependency helpers for VOLY web routes."""

from __future__ import annotations

import os
import pathlib
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voly.config import VOLYConfig


@dataclass
class AppState:
    ev_dir: pathlib.Path
    config: "VOLYConfig | None" = None
    # Signals the background watchdog-reaper thread (server.py) to stop.
    watchdog_stop: threading.Event = field(default_factory=threading.Event)

    def marketplace_url(self) -> str:
        if self.config:
            url = getattr(getattr(self.config, "registry", None), "marketplace_url", "")
            if url:
                return url
        for key in ("CF_WORKER_MARKETPLACE_URL", "MARKETPLACE_URL"):
            u = os.environ.get(key, "").strip()
            if u:
                return u
        return ""

    def spend_url(self) -> str:
        if self.config:
            raw = getattr(getattr(self.config, "spend", None), "remote_url", "")
            if raw and "${" not in raw:
                return raw
        for key in ("CF_WORKER_SPEND_URL", "SPEND_URL"):
            u = os.environ.get(key, "").strip()
            if u:
                return u
        return ""
