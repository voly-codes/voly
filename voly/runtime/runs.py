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
    parent_task_id: str = ""
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
    # Bounded workflow visibility. Kept out of the frozen TaskEvent contract.
    workflow: str = ""
    lap: int = 0
    max_laps: int = 0
    active_role: str = ""
    stop_reason: str = ""
    latest_verdict: str = ""
    cancel_requested: bool = False
    timeline: list[dict] = field(default_factory=list)
    workflow_metrics: dict = field(default_factory=dict)
    graph_nodes: list[dict] = field(default_factory=list)
    graph_edges: list[dict] = field(default_factory=list)

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
        parent_task_id: str = "",
        graph_nodes: list[dict] | None = None,
        graph_edges: list[dict] | None = None,
    ) -> RunRecord:
        now = time.time()
        rec = RunRecord(
            task_id=task_id,
            parent_task_id=parent_task_id,
            task=task[:500],
            status=RUNNING,
            started_at=now,
            heartbeat_at=now,
            total_roles=len(roles),
            done_roles=0,
            current_role=roles[0] if roles else "",
            roles=list(roles),
            plan_id=plan_id or "",
            graph_nodes=list(graph_nodes or []),
            graph_edges=list(graph_edges or []),
        )
        self._write(rec)
        return rec

    def graph_update(
        self,
        task_id: str,
        *,
        node: dict | None = None,
        edges: list[dict] | None = None,
    ) -> None:
        """Upsert one node on the parent run's shared live graph."""
        rec = self.load(task_id)
        if rec is None:
            return
        rec.heartbeat_at = time.time()
        if node is not None:
            item = dict(node)
            node_id = str(item.get("id") or "")
            if node_id:
                by_id = {str(existing.get("id") or ""): existing for existing in rec.graph_nodes}
                by_id[node_id] = {**by_id.get(node_id, {}), **item}
                order = [str(existing.get("id") or "") for existing in rec.graph_nodes]
                if node_id not in order:
                    order.append(node_id)
                rec.graph_nodes = [by_id[key] for key in order if key in by_id]
        if edges is not None:
            rec.graph_edges = [dict(edge) for edge in edges]
        self._write(rec)

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

    def workflow_update(
        self,
        task_id: str,
        *,
        workflow: str | None = None,
        lap: int | None = None,
        max_laps: int | None = None,
        active_role: str | None = None,
        latest_verdict: str | None = None,
        stop_reason: str | None = None,
        transition: dict | None = None,
        metrics: dict | None = None,
    ) -> None:
        """Persist bounded-workflow progress and an optional causal transition."""
        rec = self.load(task_id)
        if rec is None:
            return
        rec.heartbeat_at = time.time()
        if workflow is not None:
            rec.workflow = workflow
        if lap is not None:
            rec.lap = lap
        if max_laps is not None:
            rec.max_laps = max_laps
        if active_role is not None:
            rec.active_role = active_role
            rec.current_role = active_role
        if latest_verdict is not None:
            rec.latest_verdict = latest_verdict
        if stop_reason is not None:
            rec.stop_reason = stop_reason
        if transition is not None:
            rec.timeline.append(dict(transition))
        if metrics is not None:
            rec.workflow_metrics = dict(metrics)
        self._write(rec)

    def request_cancel(self, task_id: str) -> bool:
        """Request cooperative cancellation between blocking workflow turns."""
        rec = self.load(task_id)
        if rec is None or rec.status != RUNNING or not rec.workflow:
            return False
        rec.cancel_requested = True
        rec.heartbeat_at = time.time()
        self._write(rec)
        return True

    def cancellation_requested(self, task_id: str) -> bool:
        rec = self.load(task_id)
        return bool(rec and rec.cancel_requested)

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
    known = set(RunRecord.__dataclass_fields__)  # tolerate extra/legacy keys
    return RunRecord(**{k: v for k, v in data.items() if k in known})
