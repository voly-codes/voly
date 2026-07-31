"""Typed, scoped strategic memory and compact session handoffs."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryClass(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"


class MemoryScope(str, Enum):
    PROJECT = "project"
    ORGANIZATION = "organization"
    GLOBAL = "global"


class MemoryKind(str, Enum):
    DECISION = "decision"
    VERIFIED_FACT = "verified_fact"
    FAILED_ATTEMPT = "failed_attempt"
    OPEN_QUESTION = "open_question"
    NEXT_ACTION = "next_action"


@dataclass(frozen=True)
class HandoffItem:
    kind: MemoryKind
    memory_class: MemoryClass
    title: str
    content: str
    scope: MemoryScope = MemoryScope.PROJECT
    scope_id: str = ""
    provenance: list[str] = field(default_factory=list)
    private: bool = False
    expires_at: float | None = None


@dataclass(frozen=True)
class SessionHandoff:
    session_id: str
    project_id: str
    organization_id: str = ""
    items: list[HandoffItem] = field(default_factory=list)
    schema_version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionHandoff:
        items = [
            HandoffItem(
                kind=MemoryKind(item["kind"]),
                memory_class=MemoryClass(item["memory_class"]),
                title=str(item["title"]),
                content=str(item["content"]),
                scope=MemoryScope(item.get("scope", "project")),
                scope_id=str(item.get("scope_id", "")),
                provenance=list(item.get("provenance") or []),
                private=bool(item.get("private", False)),
                expires_at=item.get("expires_at"),
            )
            for item in data.get("items") or []
        ]
        return cls(
            session_id=str(data["session_id"]),
            project_id=str(data["project_id"]),
            organization_id=str(data.get("organization_id", "")),
            items=items,
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class StrategicMemory:
    id: str
    fingerprint: str
    kind: MemoryKind
    memory_class: MemoryClass
    title: str
    content: str
    scope: MemoryScope
    scope_id: str
    provenance: list[str]
    private: bool
    created_at: float
    expires_at: float | None = None
    contradicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["memory_class"] = self.memory_class.value
        data["scope"] = self.scope.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategicMemory:
        return cls(
            id=data["id"],
            fingerprint=data["fingerprint"],
            kind=MemoryKind(data["kind"]),
            memory_class=MemoryClass(data["memory_class"]),
            title=data["title"],
            content=data["content"],
            scope=MemoryScope(data["scope"]),
            scope_id=data["scope_id"],
            provenance=list(data.get("provenance") or []),
            private=bool(data.get("private", False)),
            created_at=float(data["created_at"]),
            expires_at=data.get("expires_at"),
            contradicts=list(data.get("contradicts") or []),
        )


def project_scope_id(cwd: str | Path) -> str:
    return hashlib.sha256(str(Path(cwd).resolve()).lower().encode()).hexdigest()[:16]


class StrategicMemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[StrategicMemory]:
        if not self.path.is_file():
            return []
        result = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result.append(StrategicMemory.from_dict(json.loads(line)))
        return result

    def _save(self, memories: list[StrategicMemory]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(m.to_dict(), ensure_ascii=False) + "\n" for m in memories)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _fingerprint(item: HandoffItem, scope_id: str) -> str:
        normalized = "|".join((
            item.kind.value,
            item.memory_class.value,
            item.scope.value,
            scope_id,
            item.title.strip().lower(),
            item.content.strip().lower(),
        ))
        return hashlib.sha256(normalized.encode()).hexdigest()

    def compact(self, handoff: SessionHandoff) -> list[StrategicMemory]:
        memories = self._load()
        fingerprints = {memory.fingerprint for memory in memories}
        added = []
        for item in handoff.items:
            scope_id = item.scope_id
            if not scope_id:
                scope_id = {
                    MemoryScope.PROJECT: handoff.project_id,
                    MemoryScope.ORGANIZATION: handoff.organization_id,
                    MemoryScope.GLOBAL: "global",
                }[item.scope]
            if not scope_id:
                raise ValueError(f"scope_id required for {item.scope.value} memory")
            fingerprint = self._fingerprint(item, scope_id)
            if fingerprint in fingerprints:
                continue
            contradictions = [
                memory.id for memory in memories
                if memory.kind == item.kind
                and memory.scope == item.scope
                and memory.scope_id == scope_id
                and memory.title.strip().lower() == item.title.strip().lower()
                and memory.content.strip().lower() != item.content.strip().lower()
            ]
            memory = StrategicMemory(
                id=uuid.uuid4().hex,
                fingerprint=fingerprint,
                kind=item.kind,
                memory_class=item.memory_class,
                title=item.title.strip(),
                content=item.content.strip(),
                scope=item.scope,
                scope_id=scope_id,
                provenance=item.provenance or [f"session:{handoff.session_id}"],
                private=item.private,
                created_at=time.time(),
                expires_at=item.expires_at,
                contradicts=contradictions,
            )
            for existing in memories:
                if existing.id in contradictions and memory.id not in existing.contradicts:
                    existing.contradicts.append(memory.id)
            memories.append(memory)
            fingerprints.add(fingerprint)
            added.append(memory)
        self._save(memories)
        return added

    def retrieve(
        self,
        query: str,
        *,
        project_id: str,
        organization_id: str = "",
        token_budget: int = 600,
        per_class_limit: int = 3,
    ) -> list[StrategicMemory]:
        now = time.time()
        terms = {word.lower() for word in query.split() if len(word) >= 4}
        visible = [
            memory for memory in self._load()
            if (memory.expires_at is None or memory.expires_at > now)
            and (
                (memory.scope is MemoryScope.PROJECT and memory.scope_id == project_id)
                or (
                    memory.scope is MemoryScope.ORGANIZATION
                    and organization_id
                    and memory.scope_id == organization_id
                )
                or memory.scope is MemoryScope.GLOBAL
            )
        ]
        visible.sort(
            key=lambda memory: (
                -sum(term in f"{memory.title} {memory.content}".lower() for term in terms),
                -memory.created_at,
            )
        )
        selected: list[StrategicMemory] = []
        class_counts: dict[MemoryClass, int] = {}
        used = 0
        for memory in visible:
            if class_counts.get(memory.memory_class, 0) >= per_class_limit:
                continue
            cost = max(1, (len(memory.title) + len(memory.content)) // 4)
            if used + cost > token_budget:
                continue
            selected.append(memory)
            used += cost
            class_counts[memory.memory_class] = class_counts.get(memory.memory_class, 0) + 1
        return selected

    def export(self, *, project_id: str = "") -> list[dict[str, Any]]:
        now = time.time()
        return [
            memory.to_dict() for memory in self._load()
            if not memory.private
            and (memory.expires_at is None or memory.expires_at > now)
            and (not project_id or memory.scope is not MemoryScope.PROJECT or memory.scope_id == project_id)
        ]
