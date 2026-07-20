"""Tests for VOLY Memory Store."""

import tempfile
from pathlib import Path

import pytest

from voly.memory.store import MemoryStore


@pytest.fixture(autouse=True)
def _memory_tests_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from hybrid/remote memory env left by other tests or .env."""
    for key in (
        "CF_WORKER_MEMORY_URL",
        "MEMORY_URL",
        "VOLY_MEMORY_URL",
        "VOLY_MEMORY_BACKEND",
    ):
        monkeypatch.delenv(key, raising=False)


def _store(tmp: str) -> MemoryStore:
    return MemoryStore(Path(tmp) / "test.db", backend="local")


def test_add_and_get() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        entry_id = store.add(
            title="Test memory",
            content="This is a test memory entry",
            category="decision",
            importance=0.8,
            tags=["test", "important"],
        )
        assert entry_id

        entry = store.get(entry_id)
        assert entry is not None
        assert entry.title == "Test memory"
        assert entry.content == "This is a test memory entry"
        assert entry.category == "decision"
        assert entry.importance == 0.8
        assert "test" in entry.tags

        store.close()


def test_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.add(title="Architecture decision", content="Use PostgreSQL for storage", category="decision")
        store.add(title="Code convention", content="Use snake_case for Python", category="convention")
        store.add(title="Bug fix", content="Fixed auth token refresh", category="history")

        results = store.search("PostgreSQL")
        assert len(results) >= 1
        assert any("PostgreSQL" in r.content for r in results)

        results = store.search("snake_case")
        assert len(results) >= 1
        assert any("snake_case" in r.content for r in results)

        store.close()


def test_list_by_category() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.add(title="Decision 1", content="Content", category="decision")
        store.add(title="Decision 2", content="Content", category="decision")
        store.add(title="Convention 1", content="Content", category="convention")

        decisions = store.list_by_category("decision")
        assert len(decisions) == 2

        conventions = store.list_by_category("convention")
        assert len(conventions) == 1

        store.close()


def test_update_and_delete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        entry_id = store.add(title="Original", content="Original content", category="context")

        updated = store.update(entry_id, title="Updated", importance=0.9)
        assert updated is True

        entry = store.get(entry_id)
        assert entry is not None
        assert entry.title == "Updated"
        assert entry.importance == 0.9

        deleted = store.delete(entry_id)
        assert deleted is True
        assert store.get(entry_id) is None

        store.close()


def test_search_semantic_fallback() -> None:
    """search_semantic falls back to FTS5 when sentence-transformers is not installed."""
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.add(title="PostgreSQL indexing", content="Use BRIN indexes for time-series", category="decision")
        store.add(title="Docker compose", content="Multi-container setup for local dev", category="context")

        results = store.search_semantic("database indexing strategies")
        assert isinstance(results, list)
        # FTS5 fallback may return 0 results for semantic queries — that's OK
        # The important contract: no exception raised

        store.close()


def test_search_semantic_custom_model() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(
            Path(tmp) / "test.db",
            embedding_model="paraphrase-MiniLM-L3-v2",
            backend="local",
        )
        assert store.embedding_model == "paraphrase-MiniLM-L3-v2"
        store.close()


def test_count_and_clear() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        assert store.count() == 0

        store.add(title="A", content="a", category="context")
        store.add(title="B", content="b", category="context")
        assert store.count() == 2
        assert store.count("context") == 2

        store.clear()
        assert store.count() == 0

        store.close()
