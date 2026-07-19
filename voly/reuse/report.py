"""ReuseReport dataclass + JSON save/load under .voly/reuse/reports/."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PickedModule:
    path: str
    reason: str = ""
    confidence: float = 0.0
    repo: str = ""  # owner/repo


@dataclass
class CandidatePack:
    full_name: str  # owner/repo
    html_url: str = ""
    clone_url: str = ""
    description: str = ""
    stars: int = 0
    language: str = ""
    license_spdx: str = ""
    license_allowed: bool = False
    default_branch: str = "main"
    sha: str = ""
    cache_path: str = ""
    tree_summary: str = ""
    scanner_summary: str = ""
    relevant_files: list[str] = field(default_factory=list)
    pack_chars: int = 0
    error: str = ""


@dataclass
class ApplyAction:
    src: str
    dest: str
    status: str = "planned"  # planned | copied | skipped | blocked
    detail: str = ""


@dataclass
class ReuseReport:
    report_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task: str = ""
    created_at: float = field(default_factory=time.time)
    query: str = ""
    candidates: list[CandidatePack] = field(default_factory=list)
    picked: list[PickedModule] = field(default_factory=list)
    apply_actions: list[ApplyAction] = field(default_factory=list)
    apply_dest: str = "vendor/reuse"
    dry_run: bool = True
    cwd: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReuseReport:
        candidates = [CandidatePack(**c) for c in data.get("candidates") or []]
        picked = [PickedModule(**p) for p in data.get("picked") or []]
        actions = [ApplyAction(**a) for a in data.get("apply_actions") or []]
        return cls(
            report_id=data.get("report_id") or uuid.uuid4().hex[:12],
            task=data.get("task") or "",
            created_at=float(data.get("created_at") or time.time()),
            query=data.get("query") or "",
            candidates=candidates,
            picked=picked,
            apply_actions=actions,
            apply_dest=data.get("apply_dest") or "vendor/reuse",
            dry_run=bool(data.get("dry_run", True)),
            cwd=data.get("cwd") or "",
            notes=list(data.get("notes") or []),
        )


def save_report(report: ReuseReport, reports_dir: str | Path) -> Path:
    root = Path(reports_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{report.report_id}.json"
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    latest = root / "latest.json"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def load_report(path: str | Path) -> ReuseReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReuseReport.from_dict(data)


def latest_report_path(reports_dir: str | Path) -> Path | None:
    latest = Path(reports_dir) / "latest.json"
    if latest.is_file():
        return latest
    root = Path(reports_dir)
    if not root.is_dir():
        return None
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None
