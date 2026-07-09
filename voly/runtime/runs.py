"""In-flight run tracking (heartbeat) + watchdog — Этап 2, Rung A.

`TaskEvent` is emitted only at the END of a run, so a hung multi-agent chain
leaves no trace and no watchdog can see it mid-flight. A ``RunRecord`` is a
lightweight JSON file written when a run starts and updated (heartbeat) after
each sub-agent step. A ``Watchdog`` flags records whose heartbeat is older than
``stale_factor × task_timeout`` — those are runs that crashed or hung without
finishing.

The records also answer the open empirical question from roadmap §6 — how long
chains actually run and how often they hang — which decides whether the more
expensive rungs (checkpoint/resume) are worth building.

Design rules:
- Tracking is **best-effort**: any failure here must never break the run
  (mirrors telemetry). All public methods swallow their own errors.
- Writes are **atomic** (temp file + ``os.replace``) so a crash mid-write can't
  corrupt a record a reader is scanning.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
STALE = "stale"


@dataclass
class RunRecord:
    task_id: str
    task: str = ""
    status: str = RUNNING
    started_at: float = 0.0
    heartbeat_at: float = 0.0
    total_roles: int = 0
    done_roles: int = 0
    current_role: str = ""
    roles: list[str] = field(default_factory=list)
    error: str = ""
    # Plan gates (Rung B PR4) — optional mirror of the multi-agent plan.
    plan_id: str = ""
    step_statuses: list[dict] = field(default_factory=list)

    @property
    def age_seconds(self) -> float:
        """Seconds since the last heartbeat (how long silent)."""
        return max(0.0, time.time() - self.heartbeat_at) if self.heartbeat_at else 0.0

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at) if self.started_at else 0.0


class RunTracker:
    """Writes/updates one JSON RunRecord per multi-agent run."""

    def __init__(self, runs_dir: str = ".voly/runs") -> None:
        self.runs_dir = runs_dir

    def path(self, task_id: str) -> str:
        return os.path.join(self.runs_dir, f"{task_id}.json")

    def _write(self, rec: RunRecord) -> None:
        try:
            os.makedirs(self.runs_dir, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.runs_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(asdict(rec), fh, ensure_ascii=False)
                os.replace(tmp, self.path(rec.task_id))
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except OSError:
            pass  # best-effort: never break the run

    def start(
        self,
        task_id: str,
        task: str,
        roles: list[str],
        *,
        plan_id: str = "",
    ) -> RunRecord:
        now = time.time()
        rec = RunRecord(
            task_id=task_id,
            task=task[:500],
            status=RUNNING,
            started_at=now,
            heartbeat_at=now,
            total_roles=len(roles),
            done_roles=0,
            current_role=roles[0] if roles else "",
            roles=list(roles),
            plan_id=plan_id or "",
        )
        self._write(rec)
        return rec

    def heartbeat(
        self,
        task_id: str,
        current_role: str,
        done_roles: int,
        *,
        step_statuses: list[dict] | None = None,
    ) -> None:
        rec = self.load(task_id)
        if rec is None:
            return
        rec.heartbeat_at = time.time()
        rec.current_role = current_role
        rec.done_roles = done_roles
        if step_statuses is not None:
            rec.step_statuses = list(step_statuses)
        self._write(rec)

    def finish(
        self,
        task_id: str,
        status: str = COMPLETED,
        error: str = "",
        *,
        step_statuses: list[dict] | None = None,
    ) -> None:
        rec = self.load(task_id)
        if rec is None:
            return
        rec.status = status
        rec.heartbeat_at = time.time()
        rec.done_roles = rec.total_roles if status == COMPLETED else rec.done_roles
        rec.current_role = ""
        rec.error = error[:500]
        if step_statuses is not None:
            rec.step_statuses = list(step_statuses)
        self._write(rec)

    def load(self, task_id: str) -> RunRecord | None:
        return _load_path(self.path(task_id))

    def list(self) -> list[RunRecord]:
        out: list[RunRecord] = []
        try:
            names = sorted(os.listdir(self.runs_dir))
        except OSError:
            return out
        for name in names:
            if not name.endswith(".json"):
                continue
            rec = _load_path(os.path.join(self.runs_dir, name))
            if rec is not None:
                out.append(rec)
        out.sort(key=lambda r: r.started_at, reverse=True)
        return out


class Watchdog:
    """Detects runs that stopped sending heartbeats without finishing."""

    def __init__(
        self,
        runs_dir: str = ".voly/runs",
        task_timeout: float = 120.0,
        stale_factor: float = 2.0,
    ) -> None:
        self.tracker = RunTracker(runs_dir)
        self.task_timeout = task_timeout
        self.stale_factor = stale_factor

    @property
    def stale_after(self) -> float:
        return self.task_timeout * self.stale_factor

    def is_stale(self, rec: RunRecord) -> bool:
        return rec.status == RUNNING and rec.age_seconds > self.stale_after

    def scan(self) -> list[RunRecord]:
        """Return running records whose heartbeat is older than the threshold."""
        return [r for r in self.tracker.list() if self.is_stale(r)]

    def reap(self) -> list[RunRecord]:
        """Mark stale running records as ``stale`` and return them."""
        reaped = self.scan()
        for rec in reaped:
            self.tracker.finish(rec.task_id, status=STALE, error="watchdog: no heartbeat")
        return reaped


def _load_path(path: str) -> RunRecord | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    known = {f for f in RunRecord.__dataclass_fields__}  # tolerate extra/legacy keys
    return RunRecord(**{k: v for k, v in data.items() if k in known})
