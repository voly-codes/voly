"""Console encoding helpers for cross-platform CLI output."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_utf8_stdio(
    *,
    platform: str | None = None,
    streams: tuple[TextIO, ...] | None = None,
) -> None:
    """Use UTF-8 for CLI output on Windows without assuming stream type.

    ``TextIOWrapper.reconfigure`` is unavailable for some redirected or test
    streams, so those streams are intentionally left unchanged.
    """
    if (platform or sys.platform) != "win32":
        return
    targets = streams if streams is not None else (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            continue
