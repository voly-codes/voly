"""Shared app state and dependency helpers for CodeOps web routes."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeops.config import CodeOpsConfig


@dataclass
class AppState:
    ev_dir: pathlib.Path
    config: "CodeOpsConfig | None" = None

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
