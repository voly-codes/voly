"""Repository intelligence pipeline stage."""

from __future__ import annotations

import logging
from typing import Any

from voly.pipeline.types import PipelineStage

_log = logging.getLogger("voly.pipeline")


class _IntelligenceStageMixin:
    """Mixin: optional pre-run repository analysis."""

    def _stage_repo_intelligence(self, context: dict[str, Any], repo_url: str = "") -> None:
        """Analyze an external repo when repo_url is set. Never blocks the pipeline."""
        url = (repo_url or context.get("repo_url") or "").strip()
        if not url:
            return

        from voly.intelligence import AnalyzeConfig, analyze

        try:
            intel = analyze(url, AnalyzeConfig(refresh=False))
            context["repo_intelligence"] = intel
            context["task_features"] = intel.stack.languages + intel.stack.frameworks
            self._fire(PipelineStage.REPO_INTELLIGENCE, repo_intelligence=intel)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 — non-blocking stage
            _log.warning("repo intelligence failed: %s", exc)
            context["repo_intelligence"] = None
            context["task_features"] = []
