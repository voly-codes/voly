"""Atomic JSON persistence for plans under ``.voly/plans/``.

Unlike RunTracker (best-effort telemetry), PlanStore **raises** on I/O errors:
plan state is the source of truth for gates and must not silently disappear.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Iterable

from voly.plan.types import Plan, PlanValidationError


class PlanStore:
    """Load/save Plan documents as ``<plans_dir>/<plan_id>.json``."""

    def __init__(self, plans_dir: str = ".voly/plans") -> None:
        self.plans_dir = plans_dir

    def path(self, plan_id: str) -> str:
        if not plan_id or "/" in plan_id or "\\" in plan_id or plan_id in (".", ".."):
            raise PlanValidationError(f"invalid plan_id for path: {plan_id!r}")
        return os.path.join(self.plans_dir, f"{plan_id}.json")

    def save(self, plan: Plan) -> None:
        """Atomically write plan JSON (tempfile + os.replace)."""
        plan.updated_at = time.time()
        if plan.created_at <= 0:
            plan.created_at = plan.updated_at
        os.makedirs(self.plans_dir, exist_ok=True)
        target = self.path(plan.plan_id)
        fd, tmp = tempfile.mkstemp(dir=self.plans_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(plan.to_dict(), fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, target)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            raise

    def load(self, plan_id: str) -> Plan | None:
        path = self.path(plan_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise PlanValidationError(f"plan file is not an object: {path}")
        return Plan.from_dict(data)

    def exists(self, plan_id: str) -> bool:
        return os.path.isfile(self.path(plan_id))

    def delete(self, plan_id: str) -> bool:
        path = self.path(plan_id)
        if not os.path.isfile(path):
            return False
        os.unlink(path)
        return True

    def list_ids(self) -> list[str]:
        try:
            names = os.listdir(self.plans_dir)
        except OSError:
            return []
        ids = [n[:-5] for n in names if n.endswith(".json")]
        return sorted(ids)

    def list(self) -> list[Plan]:
        out: list[Plan] = []
        for plan_id in self.list_ids():
            try:
                plan = self.load(plan_id)
            except (OSError, ValueError, PlanValidationError):
                continue
            if plan is not None:
                out.append(plan)
        out.sort(key=lambda p: p.updated_at or p.created_at, reverse=True)
        return out

    def save_many(self, plans: Iterable[Plan]) -> None:
        for plan in plans:
            self.save(plan)
