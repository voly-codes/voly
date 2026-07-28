"""Atomic local JSON storage for evidence records and human feedback."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from voly.evidence.schema import EvidenceRecord, HumanFeedback

VALID_HUMAN_FEEDBACK = frozenset(
    {"accepted", "edited", "major_rewrite", "reverted", "pr_rejected", "manual_fix"}
)
MAX_FEEDBACK_COMMENT_CHARS = 2000
MAX_FEEDBACK_SOURCE_CHARS = 64
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_FEEDBACK_LOCK = threading.Lock()


def validate_task_id(task_id: str) -> str:
    """Return a safe evidence id or reject path-like and malformed values."""
    normalized = (task_id or "").strip()
    if not _TASK_ID_RE.fullmatch(normalized):
        raise ValueError(
            "invalid task_id; expected 1-128 ASCII letters, digits, '_' or '-', "
            "starting with a letter or digit"
        )
    return normalized


class EvidenceStore:
    def __init__(self, store_dir: str | Path = ".voly/evidence") -> None:
        self.store_dir = Path(store_dir)

    def path(self, task_id: str) -> Path:
        return self.store_dir / f"{validate_task_id(task_id)}.json"

    def save(self, record: EvidenceRecord) -> Path:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(
            dir=str(self.store_dir),
            prefix=f".{record.task_id}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path(record.task_id))
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return self.path(record.task_id)

    def load(self, task_id: str) -> EvidenceRecord | None:
        try:
            data = json.loads(self.path(task_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return EvidenceRecord.from_dict(data) if isinstance(data, dict) else None

    def add_human_feedback(
        self,
        task_id: str,
        kind: str,
        *,
        source: str = "explicit",
        comment: str = "",
    ) -> EvidenceRecord:
        normalized = (kind or "").strip().lower()
        if normalized not in VALID_HUMAN_FEEDBACK:
            raise ValueError(
                f"invalid human feedback {kind!r}; expected one of "
                f"{sorted(VALID_HUMAN_FEEDBACK)}"
            )
        normalized_source = (source or "").strip()
        if not normalized_source or len(normalized_source) > MAX_FEEDBACK_SOURCE_CHARS:
            raise ValueError(
                f"feedback source must contain 1-{MAX_FEEDBACK_SOURCE_CHARS} characters"
            )
        if len(comment) > MAX_FEEDBACK_COMMENT_CHARS:
            raise ValueError(
                f"feedback comment exceeds {MAX_FEEDBACK_COMMENT_CHARS} characters"
            )

        safe_task_id = validate_task_id(task_id)
        # FastAPI may serve sync handlers concurrently. Keep the local
        # read-modify-replace sequence lossless within one VOLY process.
        with _FEEDBACK_LOCK:
            record = self.load(safe_task_id)
            if record is None:
                raise FileNotFoundError(
                    f"evidence record not found: {safe_task_id}"
                )
            record.human_feedback.append(
                HumanFeedback(
                    kind=normalized,
                    source=normalized_source,
                    comment=comment,
                    recorded_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            if record.evaluation is not None:
                from voly.evaluation import apply_human_feedback

                if apply_human_feedback(record.evaluation, normalized):
                    record.outcome.state = record.evaluation.state
            self.save(record)
            return record
