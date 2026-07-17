"""
MemoryStore — локальное хранилище долгосрочной памяти агента.

Основано на SQLite + FTS5 для полнотекстового поиска.
Не требует внешних зависимостей для базового использования.

Формат хранения:
    - decisions: принятые решения с контекстом
    - conventions: кодовые соглашения и паттерны
    - context: контекст проекта (архитектура, структура)
    - history: история сессий и задач
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger("voly.memory.store")


@dataclass
class MemoryEntry:
    id: str
    category: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class MemoryStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        timestamp REAL NOT NULL,
        importance REAL DEFAULT 0.5,
        tags TEXT DEFAULT '[]'
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        title, content, category, tags,
        content='memories',
        content_rowid='rowid'
    );

    CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, title, content, category, tags)
        VALUES (new.rowid, new.title, new.content, new.category, new.tags);
    END;

    CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, title, content, category, tags)
        VALUES ('delete', old.rowid, old.title, old.content, old.category, old.tags);
    END;

    CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, title, content, category, tags)
        VALUES ('delete', old.rowid, old.title, old.content, old.category, old.tags);
        INSERT INTO memories_fts(rowid, title, content, category, tags)
        VALUES (new.rowid, new.title, new.content, new.category, new.tags);
    END;
    """

    VALID_CATEGORIES = {"decision", "convention", "context", "history", "architect"}

    def __init__(
        self,
        db_path: str | Path = ".voly/memory.db",
        embedding_model: str = "all-MiniLM-L6-v2",
        remote_url: str = "",
        *,
        backend: str = "hybrid",
        agent_memory_account_id: str = "",
        agent_memory_namespace: str = "",
        agent_memory_profile: str = "",
    ):
        self.db_path = Path(db_path)
        self.embedding_model = embedding_model
        self._remote_url = remote_url
        self._backend = (backend or "hybrid").strip().lower()
        self._agent_memory_account_id = agent_memory_account_id
        self._agent_memory_namespace = agent_memory_namespace
        self._agent_memory_profile = agent_memory_profile
        self._remote_client: Any = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_remote_client(self) -> Any:
        if self._remote_client is None and self._backend != "local":
            from voly.memory.client import create_remote_memory_client

            self._remote_client = create_remote_memory_client(
                backend=self._backend,
                remote_url=self._remote_url,
                agent_memory_account_id=self._agent_memory_account_id,
                agent_memory_namespace=self._agent_memory_namespace,
                agent_memory_profile=self._agent_memory_profile,
            )
        return self._remote_client

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()
        return self._conn

    def add(
        self,
        title: str,
        content: str,
        category: str = "context",
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> str:
        import uuid

        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"Invalid category {category!r}. Must be one of: {self.VALID_CATEGORIES}")

        entry_id = uuid.uuid4().hex
        self.conn.execute(
            """INSERT INTO memories (id, category, title, content, metadata, timestamp, importance, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                category,
                title,
                content,
                json.dumps(metadata or {}),
                time.time(),
                importance,
                json.dumps(tags or []),
            ),
        )
        self.conn.commit()

        client = self._get_remote_client()
        if client:
            try:
                client.add(
                    title,
                    content,
                    category=category,
                    tags=tags,
                    metadata=metadata,
                    importance=importance,
                    entry_id=entry_id,
                )
            except Exception as exc:
                _log.warning("remote memory add failed (%s): %s", self._backend, exc)

        return entry_id

    def get(self, entry_id: str) -> MemoryEntry | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        # Wrap in double quotes to treat the whole query as a phrase search,
        # escaping any embedded quotes. This prevents FTS5 syntax errors when
        # the query contains operators like AND, OR, NOT, NEAR, or bare quotes.
        escaped = query.replace('"', '""')
        return f'"{escaped}"'

    def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        client = self._get_remote_client()
        if client:
            try:
                remote = client.search(query, limit=limit)
                if remote:
                    return [self._remote_to_entry(row) for row in remote]
            except Exception as exc:
                _log.warning("remote memory search failed (%s): %s", self._backend, exc)

        try:
            rows = self.conn.execute(
                """SELECT m.* FROM memories m
                   INNER JOIN memories_fts fts ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (self._sanitize_fts_query(query), limit),
            ).fetchall()
        except Exception:
            rows = []
        return [self._row_to_entry(r) for r in rows]

    def list_by_category(self, category: str, limit: int = 50) -> list[MemoryEntry]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def list_by_tags(self, tags: list[str], limit: int = 50) -> list[MemoryEntry]:
        placeholders = ",".join(["?"] * len(tags))
        rows = self.conn.execute(
            f"""SELECT * FROM memories WHERE
                EXISTS (SELECT 1 FROM json_each(tags) WHERE value IN ({placeholders}))
                ORDER BY timestamp DESC LIMIT ?""",
            (*tags, limit),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update(self, entry_id: str, **kwargs: Any) -> bool:
        allowed = {"title", "content", "category", "metadata", "importance", "tags"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        if "metadata" in updates:
            updates["metadata"] = json.dumps(updates["metadata"])
        if "tags" in updates:
            updates["tags"] = json.dumps(updates["tags"])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entry_id]
        self.conn.execute(f"UPDATE memories SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        return self.conn.total_changes > 0

    def delete(self, entry_id: str) -> bool:
        self.conn.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    def count(self, category: str | None = None) -> int:
        if category:
            row = self.conn.execute("SELECT COUNT(*) FROM memories WHERE category = ?", (category,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0] if row else 0

    def clear(self) -> None:
        self.conn.execute("DELETE FROM memories")
        self.conn.execute("DELETE FROM memories_fts")
        self.conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def search_semantic(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Semantic search — CF Vectorize when remote_url set, else sentence-transformers."""
        client = self._get_remote_client()
        if client:
            try:
                remote = client.search(query, limit=limit)
                if remote:
                    return [self._remote_to_entry(row) for row in remote]
            except Exception as exc:
                _log.warning("remote semantic search failed (%s): %s", self._backend, exc)

        try:
            from sentence_transformers import SentenceTransformer, util as st_util
        except ImportError:
            return self.search(query, limit)

        total = self.count()
        if total == 0:
            return []

        # For large stores pre-filter with FTS5 to limit candidates
        if total > 1000:
            candidates = self.search(query, limit=min(total, 200))
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories ORDER BY importance DESC, timestamp DESC LIMIT 1000"
            ).fetchall()
            candidates = [self._row_to_entry(r) for r in rows]

        if not candidates:
            return []

        model = SentenceTransformer(self.embedding_model)
        texts = [f"{e.title} {e.content}" for e in candidates]
        query_emb = model.encode(query, convert_to_tensor=True)
        corpus_emb = model.encode(texts, convert_to_tensor=True)
        scores = st_util.cos_sim(query_emb, corpus_emb)[0].tolist()

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        return [entry for _, entry in ranked[:limit]]

    def _remote_to_entry(self, row: dict[str, Any]) -> MemoryEntry:
        return MemoryEntry(
            id=str(row.get("id", "")),
            category=str(row.get("category", "context")),
            title=str(row.get("title", "")),
            content=str(row.get("content", "")),
            metadata={},
            timestamp=time.time(),
            importance=0.5,
            tags=list(row.get("tags") or []),
        )

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            category=row["category"],
            title=row["title"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            timestamp=row["timestamp"],
            importance=row["importance"],
            tags=json.loads(row["tags"]),
        )
