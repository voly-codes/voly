"""Versioned hook contracts independent of any executor harness."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HookEventType(str, Enum):
    RUN_STARTED = "run_started"
    TASK_OBSERVED = "task_observed"
    FILES_CHANGED = "files_changed"
    BEFORE_VERIFY = "before_verify"
    AFTER_VERIFY = "after_verify"
    BUDGET_THRESHOLD = "budget_threshold"
    RUN_FINISHED = "run_finished"


class FailPolicy(str, Enum):
    OPEN = "fail_open"
    CLOSED = "fail_closed"


@dataclass(frozen=True)
class HookEvent:
    event_type: HookEventType
    run_id: str
    project_id: str
    cwd: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)


@dataclass
class HookManifest:
    hook_id: str
    handler: str
    events: list[HookEventType]
    permissions: list[str]
    timeout_seconds: float
    idempotency: str
    fail_policy: FailPolicy
    enabled: bool = False
    imported: bool = False
    approved_at: float | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["events"] = [item.value for item in self.events]
        data["fail_policy"] = self.fail_policy.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, imported: bool = False) -> HookManifest:
        required = {
            "hook_id", "handler", "events", "permissions",
            "timeout_seconds", "idempotency", "fail_policy",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"hook manifest missing required fields: {missing}")
        timeout = float(data["timeout_seconds"])
        if timeout <= 0 or timeout > 300:
            raise ValueError("hook timeout_seconds must be within (0, 300]")
        idempotency = str(data["idempotency"]).strip()
        if not idempotency:
            raise ValueError("hook idempotency strategy is required")
        return cls(
            hook_id=str(data["hook_id"]),
            handler=str(data["handler"]),
            events=[HookEventType(item) for item in data["events"]],
            permissions=list(data["permissions"]),
            timeout_seconds=timeout,
            idempotency=idempotency,
            fail_policy=FailPolicy(data["fail_policy"]),
            enabled=False if imported else bool(data.get("enabled", False)),
            imported=imported or bool(data.get("imported", False)),
            approved_at=data.get("approved_at"),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass(frozen=True)
class HookResult:
    hook_id: str
    event_id: str
    status: str
    proceed: bool
    duration_ms: float
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    idempotency_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
