"""Optional reuse report snippet for local context (pipeline / executor)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

# Reports older than this are ignored for auto-inject.
_MAX_AGE_SECONDS = 7 * 24 * 3600


def format_reuse_context(
    cwd: str | Path,
    *,
    config: Any = None,
    max_chars: int = 1500,
    max_age_seconds: float = _MAX_AGE_SECONDS,
) -> str:
    """Return a short markdown block from the latest reuse report under cwd, or ''."""
    reuse_cfg = getattr(config, "reuse", None) if config is not None else None
    if reuse_cfg is not None and not getattr(reuse_cfg, "enabled", True):
        return ""

    reports_rel = getattr(reuse_cfg, "reports_dir", None) or ".voly/reuse/reports"
    root = Path(cwd).expanduser()
    reports_dir = Path(reports_rel)
    if not reports_dir.is_absolute():
        reports_dir = root / reports_dir

    try:
        from voly.reuse.report import latest_report_path, load_report
    except Exception:
        return ""

    path = latest_report_path(reports_dir)
    if path is None:
        return ""

    try:
        age = time.time() - path.stat().st_mtime
        if age > max_age_seconds:
            return ""
        report = load_report(path)
    except Exception:
        return ""

    lines = [
        "## Code reuse report (voly reuse)\n",
        f"report_id: {report.report_id}\n",
        f"task: {report.task[:200]}\n",
    ]
    if report.query:
        lines.append(f"query: {report.query[:160]}\n")
    usable = [c for c in report.candidates if c.license_allowed and not c.error]
    if report.candidates:
        lines.append("candidates:\n")
        for c in report.candidates[:5]:
            flag = "ok" if c.license_allowed else "deny"
            lines.append(
                f"- {c.full_name} ★{c.stars} license={c.license_spdx or '?'}[{flag}]\n"
            )
    else:
        lines.append(
            "candidates: none — GitHub search returned no repos "
            "(try `voly reuse search` with --lang and a shorter English query).\n"
        )
    if report.picked:
        lines.append("picked modules:\n")
        for p in report.picked[:8]:
            lines.append(f"- {p.repo}:{p.path} ({p.confidence:.2f})\n")
    elif report.candidates and not usable:
        lines.append(
            "picked: none — all candidates blocked by license policy; "
            "do not copy GPL/unknown without review.\n"
        )
    if report.apply_actions:
        planned = [a for a in report.apply_actions if a.status in ("planned", "copied")]
        if planned:
            lines.append("apply:\n")
            for a in planned[:8]:
                lines.append(f"- [{a.status}] {a.src} → {a.dest}\n")
    if usable or report.picked:
        lines.append(
            "Prefer adapting these modules over rewriting from scratch. "
            "Run `voly reuse apply <report> --cwd . --write` only after review.\n"
        )
    else:
        lines.append(
            "No reusable MIT/Apache/BSD modules found automatically; "
            "implement normally or refine the search query.\n"
        )
    text = "".join(lines)
    return text[:max_chars]
