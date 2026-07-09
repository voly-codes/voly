"""Load plan documents from YAML/JSON files or dicts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voly.plan.types import Plan, PlanStep, PlanValidationError


def load_plan_dict(data: dict[str, Any], *, default_cwd: str = "") -> Plan:
    """Build a Plan from a dict (YAML/JSON decoded). Resets runtime step fields."""
    if not isinstance(data, dict):
        raise PlanValidationError("plan document must be a mapping")

    plan = Plan.from_dict(data)
    if default_cwd and not plan.cwd:
        plan.cwd = default_cwd

    # Fresh run from file: force steps back to pending unless keep_status set.
    if not data.get("keep_status"):
        for step in plan.steps:
            step.status = "pending"
            step.error = ""
            step.verify_log = []
            # Keep task/acceptance/depends_on from file.

    return plan


def load_plan_file(path: str | Path, *, default_cwd: str = "") -> Plan:
    """Load a plan from ``.yaml`` / ``.yml`` / ``.json``."""
    p = Path(path)
    if not p.is_file():
        raise PlanValidationError(f"plan file not found: {p}")
    text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise PlanValidationError("PyYAML required to load YAML plans") from exc
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        # Try JSON first, then YAML.
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import yaml

            data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise PlanValidationError(f"plan file root must be a mapping: {p}")

    if not data.get("plan_id"):
        data["plan_id"] = p.stem

    return load_plan_dict(data, default_cwd=default_cwd)


def plan_summary(plan: Plan) -> dict[str, Any]:
    """Compact summary for CLI / telemetry stage_log (no schema bump)."""
    return {
        "plan_id": plan.plan_id,
        "status": plan.status,
        "cwd": plan.cwd,
        "steps": [
            {
                "id": s.id,
                "role": s.role,
                "mode": s.mode,
                "status": s.status,
                "depends_on": list(s.depends_on),
                "error": s.error[:200] if s.error else "",
                "verify_ok": _verify_ok(s),
            }
            for s in plan.steps
        ],
        "verified": sum(1 for s in plan.steps if s.status == "verified"),
        "failed": sum(1 for s in plan.steps if s.status == "failed"),
        "total": len(plan.steps),
    }


def _verify_ok(step: PlanStep) -> bool | None:
    if not step.verify_log:
        return None
    return all(bool(e.get("ok")) for e in step.verify_log)
