"""Repository intelligence pipeline stage."""

from __future__ import annotations

import logging
import re
from typing import Any

from voly.pipeline.types import PipelineStage

_log = logging.getLogger("voly.pipeline")

_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/[\w.-]+/[\w.-]+(?:\.git)?",
    re.IGNORECASE,
)


def extract_github_url(text: str) -> str:
    """Return the first github.com repo URL in ``text``, or empty string."""
    if not text:
        return ""
    m = _GITHUB_URL_RE.search(text)
    if not m:
        return ""
    return m.group(0).rstrip("/").removesuffix(".git")


def _local_cwd_features(cwd: str) -> list[str]:
    """Best-effort stack features from a local project scan (no network)."""
    if not cwd:
        return []
    try:
        from voly.scanner import ProjectScanner

        profile = ProjectScanner(cwd).scan()
    except Exception:  # noqa: BLE001
        return []
    names: list[str] = []
    for lang in profile.languages or []:
        n = getattr(lang, "name", None) or str(lang)
        if n:
            names.append(str(n))
    for fw in profile.frameworks or []:
        n = getattr(fw, "name", None) or str(fw)
        if n:
            names.append(str(n))
    for tf in profile.test_frameworks or []:
        if tf:
            names.append(str(tf))
    return names


class _IntelligenceStageMixin:
    """Mixin: optional pre-run repository analysis."""

    def _stage_repo_intelligence(self, context: dict[str, Any], repo_url: str = "") -> None:
        """Analyze an external repo when repo_url is set. Never blocks the pipeline.

        Also fills ``task_features`` from a local cwd scan when no remote URL is
        available, so capability stack-match still gets signal.
        """
        url = (repo_url or context.get("repo_url") or "").strip()
        if not url:
            task = str(context.get("task") or "")
            intel_cfg = getattr(self.config, "intelligence", None)  # type: ignore[attr-defined]
            if intel_cfg is not None and bool(getattr(intel_cfg, "auto", False)):
                url = extract_github_url(task)
                if url:
                    context["repo_url"] = url
                    _log.info("[PIPELINE:REPO_INTELLIGENCE] auto-detected %s", url)

        if url:
            from voly.intelligence import AnalyzeConfig, analyze

            try:
                intel = analyze(url, AnalyzeConfig(refresh=False))
                context["repo_intelligence"] = intel
                context["task_features"] = list(
                    (intel.stack.languages or []) + (intel.stack.frameworks or [])
                )
                self._fire(PipelineStage.REPO_INTELLIGENCE, repo_intelligence=intel)  # type: ignore[attr-defined]
                return
            except Exception as exc:  # noqa: BLE001 — non-blocking stage
                _log.warning("repo intelligence failed: %s", exc)
                context["repo_intelligence"] = None

        cwd = str(context.get("cwd") or context.get("project_cwd") or "").strip()
        features = _local_cwd_features(cwd)
        context.setdefault("repo_intelligence", None)
        context["task_features"] = features
        if features:
            _log.info(
                "[PIPELINE:REPO_INTELLIGENCE] local features=%s cwd=%s",
                features[:8],
                cwd or "(none)",
            )
