from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from voly.a2a.assignment import Assignment


@dataclass
class A2AReport:
    task_id: str
    task: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    merged_result: str = ""
    total_duration_ms: float = 0.0
    total_cost_usd: float = 0.0
    agents_used: list[str] = field(default_factory=list)

    def save(self, reports_dir: Path) -> Path:
        path = reports_dir / "a2a" / f"{self.task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2))
        return path

    @classmethod
    def from_a2a_tasks(
        cls,
        task_id: str,
        task: str,
        a2a_tasks: list,
        merged_result: str,
        duration_ms: float,
    ) -> A2AReport:
        subtasks: list[dict[str, Any]] = []
        agents_used: list[str] = []

        for t in a2a_tasks:
            agent = t.metadata.get("agent", "unknown")
            agents_used.append(agent)
            content = getattr(t, "result", "") or ""
            subtasks.append(
                {
                    "agent": agent,
                    "status": t.state.value,
                    "content": content[:2000],
                    "error": t.metadata.get("error"),
                }
            )

        return cls(
            task_id=task_id,
            task=task[:500],
            subtasks=subtasks,
            merged_result=merged_result[:8000],
            total_duration_ms=duration_ms,
            agents_used=agents_used,
        )


def merge_report(task: str, assignments: list[Assignment]) -> str:
    """Human-readable merged report: what each agent (model/tier) produced."""
    per_role_max = 3500
    total_max = 40000
    lines = [f"# Multi-agent result: {task[:120]}", ""]
    for a in assignments:
        status = "✓" if a.ok else "✗"
        skills = ", ".join(a.skills) if a.skills else "—"
        lines.append(
            f"## [{a.role}] {status}  ·  {a.provider}/{a.model} (tier={a.tier})  ·  skills: {skills}"
        )
        if a.error and not a.ok:
            lines.append(f"**Error:** {a.error.strip()}")
        if a.files_touched:
            shown = ", ".join(a.files_touched[:12])
            suffix = (
                f" (+{len(a.files_touched) - 12} more)"
                if len(a.files_touched) > 12
                else ""
            )
            lines.append(f"**Files:** {shown}{suffix}")
        lines.append("")
        body = (a.content or "").strip() or "(no output)"
        cap = per_role_max if a.ok else per_role_max + 1500
        if len(body) > cap:
            body = body[:cap] + "\n...(truncated)"
        lines.append(body)
        lines.append("\n---\n")
    report = "\n".join(lines).strip()
    if len(report) > total_max:
        report = report[:total_max] + "\n...(report truncated)"
    return report
