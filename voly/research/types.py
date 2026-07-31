"""Typed research-first decision contract."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResearchDecision(str, Enum):
    REUSE = "reuse"
    ADAPT = "adapt"
    BUILD = "build"


@dataclass(frozen=True)
class ResearchCandidate:
    candidate_id: str
    source: str
    location: str
    title: str
    score: float
    provenance: str
    reason: str


@dataclass
class ResearchReport:
    task: str
    eligible: bool
    eligibility_reason: str
    decision: ResearchDecision
    candidates: list[ResearchCandidate] = field(default_factory=list)
    selected_candidate_id: str = ""
    rejected_candidate_ids: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    mode: str = "shadow"
    network_used: bool = False
    report_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data
