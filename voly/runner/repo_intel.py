"""Optional repository intelligence before executor runs."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("voly.chain")


def analyze_repo_for_run(repo_url: str) -> dict[str, Any]:
    """Analyze repo_url; return context dict. Never raises."""
    url = (repo_url or "").strip()
    if not url:
        return {}
    try:
        from voly.intelligence import AnalyzeConfig, analyze

        intel = analyze(url, AnalyzeConfig(refresh=False))
        ctx = {
            "repo_intelligence": intel,
            "task_features": intel.stack.languages + intel.stack.frameworks,
        }
        _log.debug(
            "repo intelligence: repo=%s features=%s",
            url,
            ctx["task_features"],
        )
        return ctx
    except Exception as exc:  # noqa: BLE001
        _log.warning("repo intelligence failed: %s", exc)
        return {"repo_intelligence": None, "task_features": []}
