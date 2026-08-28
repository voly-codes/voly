"""Versioned, domain-neutral artifacts for business-signal orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


SIGNAL_SCHEMA_VERSION = 1
OPTION_SCHEMA_VERSION = 1
ACTION_REPORT_SCHEMA_VERSION = 1


class SensingValidationError(ValueError):
    """Raised when a sensing artifact is unsafe or structurally invalid."""


@dataclass(frozen=True)
class Signal:
    """One immutable external observation captured by a sensing connector."""

    signal_id: str
    source: str
    source_ref: str
    captured_at: str
    dedup_key: str
    payload: dict[str, Any]
    confidence: float
    schema_version: int = SIGNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.signal_id or any(mark in self.signal_id for mark in ("/", "\\")):
            raise SensingValidationError(f"invalid signal_id: {self.signal_id!r}")
        if not self.source:
            raise SensingValidationError("signal source is required")
        if not self.dedup_key:
            raise SensingValidationError("signal dedup_key is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise SensingValidationError("signal confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        return cls(
            signal_id=str(data["signal_id"]),
            source=str(data["source"]),
            source_ref=str(data.get("source_ref") or ""),
            captured_at=str(data["captured_at"]),
            dedup_key=str(data["dedup_key"]),
            payload=dict(data.get("payload") or {}),
            confidence=float(data.get("confidence", 0.0)),
            schema_version=int(data.get("schema_version") or SIGNAL_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class Option:
    """One candidate response produced while interpreting a Signal."""

    VALID_URGENCIES: ClassVar[frozenset[str]] = frozenset({"low", "medium", "high"})
    VALID_ACTION_KINDS: ClassVar[frozenset[str]] = frozenset({"business", "code", "ignore"})

    option_id: str
    signal_id: str
    title: str
    rationale: str
    urgency: str
    estimated_impact: str
    action_kind: str
    action_spec: dict[str, Any] = field(default_factory=dict)
    schema_version: int = OPTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.urgency not in self.VALID_URGENCIES:
            raise ValueError(f"invalid option urgency: {self.urgency!r}")
        if self.action_kind not in self.VALID_ACTION_KINDS:
            raise ValueError(f"invalid option action_kind: {self.action_kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Option:
        return cls(
            option_id=str(data["option_id"]),
            signal_id=str(data["signal_id"]),
            title=str(data["title"]),
            rationale=str(data.get("rationale") or ""),
            urgency=str(data["urgency"]),
            estimated_impact=str(data.get("estimated_impact") or ""),
            action_kind=str(data["action_kind"]),
            action_spec=dict(data.get("action_spec") or {}),
            schema_version=int(data.get("schema_version") or OPTION_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class ActionReport:
    """Redactable summary of a completed or attempted business action."""

    action_kind: str
    target: str
    request_summary: str
    result: str
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = ACTION_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionReport:
        return cls(
            action_kind=str(data["action_kind"]),
            target=str(data.get("target") or ""),
            request_summary=str(data.get("request_summary") or ""),
            result=str(data.get("result") or ""),
            metadata=dict(data.get("metadata") or {}),
            schema_version=int(data.get("schema_version") or ACTION_REPORT_SCHEMA_VERSION),
        )
