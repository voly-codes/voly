"""Deterministic local-first research that never changes task routing."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .types import ResearchCandidate, ResearchDecision, ResearchReport

_EXCLUDED = {".git", ".voly", "__pycache__", "node_modules", ".venv", "dist", "build"}
_TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".md", ".toml", ".yaml", ".yml"}
_RISK_WORDS = {
    "architecture", "security", "integration", "migration", "dependency", "pipeline",
    "agent", "research", "design", "protocol", "auth", "database", "api",
    "архитектур", "безопас", "интеграц", "миграц", "зависим", "исслед",
}


def _terms(task: str) -> set[str]:
    return {
        word.lower() for word in re.findall(r"[\w-]{4,}", task, flags=re.UNICODE)
        if word.lower() not in {"with", "from", "that", "this", "для", "нужно", "сделать"}
    }


def _eligibility(task: str) -> tuple[bool, str]:
    lowered = task.lower()
    if len(task.strip()) < 24:
        return False, "task is too small for research overhead"
    matched = sorted(word for word in _RISK_WORDS if word in lowered)
    if matched:
        return True, f"risk/complexity signals: {', '.join(matched[:4])}"
    if len(task.split()) >= 10:
        return True, "multi-part task justifies a local evidence pass"
    return False, "no material size or risk signal"


def _local_candidates(
    root: Path, terms: set[str], limit: int, deadline: float
) -> list[ResearchCandidate]:
    scored: list[tuple[float, Path, str]] = []
    scanned = 0
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in _EXCLUDED)
        for filename in sorted(files):
            if time.monotonic() >= deadline:
                break
            path = Path(directory) / filename
            if path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            scanned += 1
            if scanned > 1500:
                break
            try:
                if path.stat().st_size > 256_000:
                    continue
                sample = path.read_text(encoding="utf-8", errors="ignore")[:24_000].lower()
            except OSError:
                continue
            path_text = path.as_posix().lower()
            name_hits = sum(2 for term in terms if term in path_text)
            content_hits = sum(1 for term in terms if term in sample)
            score = float(name_hits + content_hits)
            if score:
                scored.append(
                    (score, path, f"{name_hits // 2} path and {content_hits} content matches")
                )
        if scanned > 1500 or time.monotonic() >= deadline:
            break
    scored.sort(key=lambda item: (-item[0], item[1].as_posix()))
    result: list[ResearchCandidate] = []
    for index, (score, path, reason) in enumerate(scored[:limit]):
        rel = path.relative_to(root).as_posix()
        result.append(ResearchCandidate(
            candidate_id=f"local-{index + 1}",
            source="project",
            location=rel,
            title=path.name,
            score=score,
            provenance=f"local:{rel}",
            reason=reason,
        ))
    return result


def _reuse_candidates(root: Path, limit: int) -> list[ResearchCandidate]:
    path = root / ".voly" / "reuse" / "reports" / "latest.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    result = []
    for item in (data.get("picked") or [])[:limit]:
        location = f"{item.get('repo', '')}:{item.get('path', '')}".strip(":")
        result.append(ResearchCandidate(
            candidate_id=f"reuse-{len(result) + 1}",
            source="reuse-report",
            location=location,
            title=item.get("path") or item.get("repo") or "reuse candidate",
            score=float(item.get("confidence") or 0) * 10,
            provenance=f"reuse-report:{data.get('report_id', 'unknown')}",
            reason=item.get("reason") or "previously selected by the reuse pipeline",
        ))
    return result


def run_research(
    task: str,
    cwd: str | Path,
    *,
    max_candidates: int = 8,
    max_duration_ms: int = 1000,
) -> ResearchReport:
    """Produce an offline recommendation; never mutate routing or fetch the network."""
    started = time.monotonic()
    root = Path(cwd).expanduser().resolve()
    eligible, reason = _eligibility(task)
    candidates: list[ResearchCandidate] = []
    if eligible and root.is_dir():
        candidates = _reuse_candidates(root, max_candidates)
        remaining = max(0, max_candidates - len(candidates))
        deadline = started + max(1, max_duration_ms) / 1000
        candidates.extend(_local_candidates(root, _terms(task), remaining, deadline))
    candidates.sort(key=lambda item: (-item.score, item.candidate_id))
    selected = candidates[0] if candidates else None
    if selected and selected.source == "reuse-report" and selected.score >= 7:
        decision = ResearchDecision.REUSE
    elif selected and selected.score >= 2:
        decision = ResearchDecision.ADAPT
    else:
        decision = ResearchDecision.BUILD
    return ResearchReport(
        task=task,
        eligible=eligible,
        eligibility_reason=reason,
        decision=decision,
        candidates=candidates,
        selected_candidate_id=selected.candidate_id if selected else "",
        rejected_candidate_ids=[c.candidate_id for c in candidates[1:]],
        provenance=[c.provenance for c in candidates],
        duration_ms=(time.monotonic() - started) * 1000,
    )


def save_report(report: ResearchReport, reports_dir: str | Path) -> Path:
    root = Path(reports_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    path = root / f"{report.report_id}.json"
    temporary = root / f".{report.report_id}.{os.getpid()}.tmp"
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    latest_tmp = root / f".latest.{os.getpid()}.tmp"
    latest_tmp.write_text(payload, encoding="utf-8")
    latest_tmp.replace(root / "latest.json")
    return path
