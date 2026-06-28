"""Менеджер версий DSPy программ и тегов развёртывания."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProgramVersionRecord:
    version: int
    score: float | None = None
    optimizer: str | None = None
    dataset: str | None = None
    compile_id: str | None = None
    shadow_score_delta: float | None = None
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "score": self.score,
            "optimizer": self.optimizer,
            "dataset": self.dataset,
            "compile_id": self.compile_id,
            "shadow_score_delta": self.shadow_score_delta,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramVersionRecord":
        return cls(
            version=int(data.get("version", 0)),
            score=data.get("score"),
            optimizer=data.get("optimizer"),
            dataset=data.get("dataset"),
            compile_id=data.get("compile_id"),
            shadow_score_delta=data.get("shadow_score_delta"),
            created_at=float(data.get("created_at", time.time())),
        )


class ProgramVersionManager:
    """Отвечает за индексацию версий программ и назначение тегов (production, candidate...)."""

    def __init__(self, programs_dir: str) -> None:
        self._index_path = Path(programs_dir) / "_index.json"
        self._data = self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_version(
        self,
        program_id: str,
        record: ProgramVersionRecord,
        *,
        tags: list[str] | None = None,
    ) -> None:
        entry = self._data.setdefault(program_id, {"versions": {}, "tags": {}})
        entry["versions"][str(record.version)] = record.to_dict()
        for tag in tags or []:
            entry["tags"][tag] = record.version
        self._save()

    def assign_tag(self, program_id: str, tag: str, version: int) -> None:
        entry = self._data.setdefault(program_id, {"versions": {}, "tags": {}})
        entry["tags"][tag] = int(version)
        self._save()

    def resolve_tag(self, program_id: str, tag: str) -> int | None:
        entry = self._data.get(program_id)
        if not entry:
            return None
        tags = entry.get("tags", {})
        version = tags.get(tag)
        return int(version) if version else None

    def latest(self, program_id: str) -> int | None:
        entry = self._data.get(program_id)
        if not entry:
            return None
        versions = [int(v) for v in entry.get("versions", {}).keys()]
        return max(versions) if versions else None

    def metadata(self, program_id: str, version: int) -> ProgramVersionRecord | None:
        entry = self._data.get(program_id)
        if not entry:
            return None
        data = entry.get("versions", {}).get(str(version))
        if not data:
            return None
        return ProgramVersionRecord.from_dict(data)

    def list_programs(self) -> dict[str, dict[str, Any]]:
        """Возвращает словарь программ с версиями и тегами."""
        return self._data
