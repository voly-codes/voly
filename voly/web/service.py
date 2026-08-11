"""Transport-neutral service layer over the VOLY run and task stores.

The HTTP routes (`voly/web/routes/`) and the MCP facade (`voly/mcp/`) are two
transports over the same data, so everything they share lives here. Nothing at
module level imports FastAPI or the MCP SDK, and the events directory is passed
in explicitly rather than read from app state — the MCP server has no request
object to carry it.

Adding a transport should mean writing tool/route signatures, never a second
copy of the logic.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict
from typing import Any

from voly.evidence.store import validate_task_id

_JSON_GLOB = "*.json"

# Bounds on what a caller may pull in one request. The MCP facade hands these
# results to a model whose context they have to fit in, so the cap is lower than
# what a paging UI would want.
_MAX_TASKS = 500
_MAX_RUNS = 200


def resolve_events_dir() -> pathlib.Path:
    """First existing `.voly/events` (cwd, then home), else the cwd candidate."""
    candidates = [
        pathlib.Path.cwd() / ".voly" / "events",
        pathlib.Path.home() / ".voly" / "events",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def runs_dir(ev_dir: pathlib.Path) -> str:
    """`.voly/runs` — sibling of the events dir, where RunTracker heartbeats live."""
    return str(ev_dir.parent / "runs")


def safe_task_id(task_id: str) -> str | None:
    """Validated id, or None when the caller passed something path-like.

    Returning None rather than raising keeps the callers' error shapes their own
    (HTTP 400 for a route, a typed error payload for an MCP tool).
    """
    try:
        return validate_task_id(task_id)
    except ValueError:
        return None


# ── Finished tasks (TaskEvent files) ─────────────────────────────────────────

def load_events(ev_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Every TaskEvent in the events dir, newest first. Unreadable files are skipped."""
    if not ev_dir.exists():
        return []
    out = []
    for f in ev_dir.glob(_JSON_GLOB):
        try:
            d = json.loads(f.read_text())
            d["_mtime"] = f.stat().st_mtime
            out.append(d)
        except Exception:  # noqa: BLE001 — a half-written event must not break the list
            pass
    return sorted(out, key=lambda x: x.get("_mtime", 0), reverse=True)


def list_tasks(
    ev_dir: pathlib.Path,
    limit: int = 100,
    agent: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    tasks = load_events(ev_dir)
    if agent:
        tasks = [t for t in tasks if t.get("agent") == agent]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return tasks[: max(1, min(limit, _MAX_TASKS))]


def get_task(ev_dir: pathlib.Path, task_id: str) -> dict[str, Any] | None:
    """One finished task's TaskEvent, or None when the id is unknown or unsafe."""
    safe = safe_task_id(task_id)
    if safe is None:
        return None
    path = ev_dir / f"{safe}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def task_stats(ev_dir: pathlib.Path) -> dict[str, Any]:
    """Roll-up over every finished task: cost, tokens, duration, and breakdowns."""
    tasks = load_events(ev_dir)
    if not tasks:
        return {
            "total_tasks": 0, "total_cost_usd": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_saved_tokens": 0, "avg_duration_ms": 0,
            "by_agent": {}, "by_status": {}, "by_model": {},
        }

    total_cost = 0.0
    total_in = total_out = total_saved = 0
    durations: list[float] = []
    by_agent: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_model: dict[str, int] = {}

    for t in tasks:
        total_cost += t.get("cost_usd") or 0
        tok = t.get("tokens") or {}
        total_in += tok.get("input") or 0
        total_out += tok.get("output") or 0
        total_saved += (tok.get("saved_rtk") or 0) + (tok.get("saved_headroom") or 0)
        if d := t.get("duration_ms"):
            durations.append(d)
        key_agent = t.get("agent") or "unknown"
        key_status = t.get("status") or "unknown"
        key_model = t.get("model") or "unknown"
        by_agent[key_agent] = by_agent.get(key_agent, 0) + 1
        by_status[key_status] = by_status.get(key_status, 0) + 1
        by_model[key_model] = by_model.get(key_model, 0) + 1

    return {
        "total_tasks": len(tasks),
        "total_cost_usd": round(total_cost, 6),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_saved_tokens": total_saved,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "by_agent": by_agent,
        "by_status": by_status,
        "by_model": by_model,
    }


# ── In-flight runs (RunRecord heartbeats) ────────────────────────────────────

def run_to_dict(rec: Any) -> dict[str, Any]:
    d = asdict(rec)
    d["age_seconds"] = round(rec.age_seconds, 1)
    d["elapsed_seconds"] = round(rec.elapsed_seconds, 1)
    return d


def list_runs(
    ev_dir: pathlib.Path,
    active: bool = False,
    include_children: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Runs known to the RunTracker. `active` keeps only ones still heartbeating."""
    from voly.runtime.runs import RUNNING, RunTracker

    records = RunTracker(runs_dir(ev_dir)).list()
    if not include_children:
        records = [r for r in records if not r.parent_task_id]
    if active:
        records = [r for r in records if r.status == RUNNING]
    return {
        "runs": [run_to_dict(r) for r in records[: max(1, min(limit, _MAX_RUNS))]],
        "active": sum(1 for r in records if r.status == RUNNING),
    }


def get_run(ev_dir: pathlib.Path, task_id: str) -> dict[str, Any] | None:
    from voly.runtime.runs import RunTracker

    safe = safe_task_id(task_id)
    if safe is None:
        return None
    rec = RunTracker(runs_dir(ev_dir)).load(safe)
    return None if rec is None else run_to_dict(rec)


def cancel_run(ev_dir: pathlib.Path, task_id: str) -> bool:
    """Ask for a cooperative stop. False when the run is missing or already done."""
    from voly.runtime.runs import RunTracker

    safe = safe_task_id(task_id)
    if safe is None:
        return False
    return RunTracker(runs_dir(ev_dir)).request_cancel(safe)


# ── Starting a run without an SSE client ─────────────────────────────────────

async def start_run_background(
    *,
    task: str,
    ev_dir: pathlib.Path,
    config: Any = None,
    executor: str = "pipeline",
    cwd: str = "",
    dry_run: bool = False,
    timeout: int = 300,
    max_turns: int = 30,
    workflow: str = "",
    max_rounds: int = 3,
    deadline_seconds: float = 900.0,
) -> dict[str, Any]:
    """Dispatch a run, return its `task_id` immediately, and finish it in the background.

    `POST /api/run` streams progress over SSE, which no MCP `tools/call` can hold
    open — one call gets one response, and a run outlives it. This is the same
    dispatch and the same RunRecord, minus the stream: callers poll `get_run()`
    for heartbeats and `get_task()` for the result.

    Imports from `voly.web.routes.run` are deferred so this module stays free of
    FastAPI until a run is actually started.
    """
    import asyncio

    from voly.web.routes.run import RunRequest, finish_run, launch_run, prepare_run

    req = RunRequest(
        task=task,
        executor=executor,
        cwd=cwd,
        dry_run=dry_run,
        timeout=timeout,
        max_turns=max_turns,
        workflow=workflow,  # type: ignore[arg-type]  # validated by RunRequest
        max_rounds=max_rounds,
        deadline_seconds=deadline_seconds,
    )
    rd = runs_dir(ev_dir)
    effective_req, start_payload, run_id = await prepare_run(req, config, rd)

    async def _drive() -> None:
        try:
            result = await launch_run(effective_req, config, rd, run_id)
            finish_run(rd, run_id, result)
        except Exception as exc:  # noqa: BLE001 — nothing is awaiting this task
            from voly.runtime.runs import FAILED, RunTracker

            RunTracker(rd).finish(run_id, status=FAILED, error=str(exc))

    # Held on the loop, not awaited: the caller gets task_id now, the run lands
    # in the RunRecord (and then the TaskEvent) whenever it finishes.
    background = asyncio.ensure_future(_drive())
    _BACKGROUND_RUNS.add(background)
    background.add_done_callback(_BACKGROUND_RUNS.discard)

    return {**start_payload, "task_id": run_id, "status": "running"}


# Strong references to in-flight background runs. Without this the event loop
# only holds a weak reference and a run can be garbage-collected mid-flight.
_BACKGROUND_RUNS: set[Any] = set()
