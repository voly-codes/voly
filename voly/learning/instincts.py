"""Atomic instincts with manual approval and evidence-gated confidence."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_PROTECTED_PATTERNS = (
    "ignore policy",
    "override policy",
    "bypass security",
    "disable security",
    "ignore system",
    "reveal secret",
)
_POSITIVE_EVIDENCE = {"test_passed", "review_accepted", "user_accepted", "verified_outcome"}
_NEGATIVE_EVIDENCE = {"rollback", "contradiction", "user_correction", "test_failed", "retry"}


class InstinctScope(str, Enum):
    PROJECT = "project"
    ORGANIZATION = "organization"
    GLOBAL = "global"


class InstinctLifecycle(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    RETIRED = "retired"


@dataclass(frozen=True)
class InstinctEvidence:
    kind: str
    source_id: str
    project_id: str
    outcome: str = ""
    created_at: float = field(default_factory=time.time)

    @property
    def is_positive(self) -> bool:
        return self.kind in _POSITIVE_EVIDENCE

    @property
    def is_negative(self) -> bool:
        return self.kind in _NEGATIVE_EVIDENCE


@dataclass
class Instinct:
    id: str
    trigger: str
    action: str
    scope: InstinctScope
    scope_id: str
    confidence: float = 0.25
    evidence: list[InstinctEvidence] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    lifecycle: InstinctLifecycle = InstinctLifecycle.CANDIDATE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.value
        data["lifecycle"] = self.lifecycle.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instinct:
        return cls(
            id=data["id"],
            trigger=data["trigger"],
            action=data["action"],
            scope=InstinctScope(data["scope"]),
            scope_id=data["scope_id"],
            confidence=float(data.get("confidence", 0.25)),
            evidence=[InstinctEvidence(**row) for row in data.get("evidence") or []],
            contradictions=list(data.get("contradictions") or []),
            lifecycle=InstinctLifecycle(data.get("lifecycle", "candidate")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


def _validate_content(trigger: str, action: str) -> None:
    if not trigger.strip() or not action.strip():
        raise ValueError("trigger and action are required")
    lowered = action.lower()
    if any(pattern in lowered for pattern in _PROTECTED_PATTERNS):
        raise ValueError("learned content cannot override policy or security rules")


class InstinctStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[Instinct]:
        if not self.path.is_file():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Instinct.from_dict(row) for row in data if isinstance(row, dict)]

    def _save(self, instincts: list[Instinct]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [instinct.to_dict() for instinct in instincts],
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> list[Instinct]:
        return self._load()

    def propose(
        self,
        trigger: str,
        action: str,
        *,
        project_id: str,
        evidence: InstinctEvidence,
    ) -> Instinct:
        _validate_content(trigger, action)
        instincts = self._load()
        key = hashlib.sha256(
            f"{project_id}|{trigger.strip().lower()}|{action.strip().lower()}".encode()
        ).hexdigest()
        existing = next((item for item in instincts if item.id == key), None)
        if existing is None:
            existing = Instinct(
                id=key,
                trigger=trigger.strip(),
                action=action.strip(),
                scope=InstinctScope.PROJECT,
                scope_id=project_id,
            )
            instincts.append(existing)
        if not any(
            row.kind == evidence.kind and row.source_id == evidence.source_id
            for row in existing.evidence
        ):
            existing.evidence.append(evidence)
            if evidence.is_positive:
                existing.confidence = min(1.0, existing.confidence + 0.15)
            elif evidence.is_negative:
                existing.confidence = max(0.0, existing.confidence - 0.20)
                if evidence.kind in {"rollback", "contradiction", "user_correction"}:
                    existing.contradictions.append(evidence.source_id)
                    if existing.lifecycle is InstinctLifecycle.APPROVED:
                        existing.lifecycle = InstinctLifecycle.SUSPENDED
            existing.updated_at = time.time()
        self._save(instincts)
        return existing

    def approve(self, instinct_id: str) -> Instinct:
        instincts = self._load()
        instinct = next((item for item in instincts if item.id == instinct_id), None)
        if instinct is None:
            raise KeyError(instinct_id)
        if not any(item.is_positive for item in instinct.evidence):
            raise ValueError("approval requires positive evidence")
        instinct.lifecycle = InstinctLifecycle.APPROVED
        instinct.updated_at = time.time()
        self._save(instincts)
        return instinct

    def add_evidence(self, instinct_id: str, evidence: InstinctEvidence) -> Instinct:
        instincts = self._load()
        instinct = next((item for item in instincts if item.id == instinct_id), None)
        if instinct is None:
            raise KeyError(instinct_id)
        if any(
            row.kind == evidence.kind and row.source_id == evidence.source_id
            for row in instinct.evidence
        ):
            return instinct
        instinct.evidence.append(evidence)
        if evidence.is_positive:
            instinct.confidence = min(1.0, instinct.confidence + 0.15)
        elif evidence.is_negative:
            instinct.confidence = max(0.0, instinct.confidence - 0.20)
            if evidence.kind in {"rollback", "contradiction", "user_correction"}:
                instinct.contradictions.append(evidence.source_id)
                if instinct.lifecycle is InstinctLifecycle.APPROVED:
                    instinct.lifecycle = InstinctLifecycle.SUSPENDED
        instinct.updated_at = time.time()
        self._save(instincts)
        return instinct

    def remove(self, instinct_id: str) -> bool:
        instincts = self._load()
        remaining = [item for item in instincts if item.id != instinct_id]
        if len(remaining) == len(instincts):
            return False
        self._save(remaining)
        return True

    def shadow_select(self, task: str, *, project_id: str, limit: int = 5) -> list[Instinct]:
        terms = set(re.findall(r"[\w-]{4,}", task.lower()))
        eligible = [
            item for item in self._load()
            if item.lifecycle is InstinctLifecycle.APPROVED
            and (
                item.scope is InstinctScope.GLOBAL
                or (
                    item.scope is InstinctScope.PROJECT
                    and item.scope_id == project_id
                )
            )
        ]
        scored = [
            (
                sum(term in instinct.trigger.lower() for term in terms),
                instinct.confidence,
                instinct,
            )
            for instinct in eligible
        ]
        scored.sort(key=lambda row: (-row[0], -row[1], row[2].id))
        return [row[2] for row in scored if row[0] > 0][:limit]

    def promote_global(self, instinct_id: str) -> Instinct:
        instincts = self._load()
        instinct = next((item for item in instincts if item.id == instinct_id), None)
        if instinct is None:
            raise KeyError(instinct_id)
        projects = {item.project_id for item in instinct.evidence if item.is_positive}
        if len(projects) < 2:
            raise ValueError("global promotion requires positive evidence from two projects")
        if instinct.lifecycle is not InstinctLifecycle.APPROVED:
            raise ValueError("global promotion requires manual approval")
        instinct.scope = InstinctScope.GLOBAL
        instinct.scope_id = "global"
        instinct.updated_at = time.time()
        self._save(instincts)
        return instinct

    def skill_candidates(self, *, min_confidence: float = 0.7) -> list[dict[str, Any]]:
        groups: dict[str, list[Instinct]] = {}
        for instinct in self._load():
            if (
                instinct.lifecycle is InstinctLifecycle.APPROVED
                and instinct.confidence >= min_confidence
                and not instinct.contradictions
            ):
                topic = next(iter(re.findall(r"[\w-]{4,}", instinct.trigger.lower())), "general")
                groups.setdefault(topic, []).append(instinct)
        return [
            {
                "schema_version": 1,
                "skill_id": f"learned-{topic}-v1",
                "version": 1,
                "instinct_ids": [item.id for item in items],
                "status": "candidate",
            }
            for topic, items in sorted(groups.items())
        ]

    def ingest_task_event(
        self, event: Any, *, trigger: str, action: str, project_id: str
    ) -> Instinct:
        if event.status == "completed":
            kind = "verified_outcome" if getattr(event, "memory_hits", 0) else "observation"
        else:
            kind = "retry" if getattr(event, "retry_count", 0) else "test_failed"
        evidence = InstinctEvidence(kind, event.task_id, project_id, event.status)
        return self.propose(trigger, action, project_id=project_id, evidence=evidence)

    def ingest_evidence_record(
        self, record: Any, *, trigger: str, action: str, project_id: str
    ) -> Instinct:
        feedback = [item.kind for item in record.human_feedback]
        if any(kind in {"reverted", "major_rewrite", "manual_fix", "pr_rejected"} for kind in feedback):
            kind = "user_correction"
        elif "accepted" in feedback:
            kind = "user_accepted"
        elif record.evaluation is not None and record.evaluation.state == "passed":
            kind = "test_passed"
        elif record.outcome.retries:
            kind = "retry"
        else:
            kind = "observation"
        evidence = InstinctEvidence(kind, record.task_id, project_id, record.outcome.state)
        return self.propose(trigger, action, project_id=project_id, evidence=evidence)

    def ingest_business_decision(self, plan: Any, *, project_id: str = "business") -> Instinct:
        """Ingest explicit Decision/outcome evidence without auto-approving it."""
        meta = getattr(plan, "metadata", {}) or {}
        decision = str(meta.get("decision") or "pending")
        execution = str(meta.get("execution") or "pending")
        if decision == "rejected":
            kind, outcome = "user_correction", "rejected"
        elif execution == "completed":
            kind, outcome = "verified_outcome", "completed"
        elif decision == "approved":
            kind, outcome = "user_accepted", "approved"
        else:
            kind, outcome = "observation", "pending"
        evidence = InstinctEvidence(kind, f"{plan.plan_id}:{outcome}", project_id, outcome)
        trigger = f"business signal {meta.get('signal_id') or 'unknown'}"
        action = str(getattr(plan, "task", "") or meta.get("action_kind") or "review business option")
        return self.propose(trigger, action, project_id=project_id, evidence=evidence)
