from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class A2AReport:
    task_id: str
    task: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z"
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
