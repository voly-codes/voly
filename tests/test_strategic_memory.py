from __future__ import annotations

import time

from voly.memory.strategic import (
    HandoffItem,
    MemoryClass,
    MemoryKind,
    MemoryScope,
    SessionHandoff,
    StrategicMemoryStore,
)


def _item(
    title: str,
    content: str,
    *,
    memory_class: MemoryClass = MemoryClass.SEMANTIC,
    scope: MemoryScope = MemoryScope.PROJECT,
    private: bool = False,
    expires_at: float | None = None,
) -> HandoffItem:
    return HandoffItem(
        kind=MemoryKind.VERIFIED_FACT,
        memory_class=memory_class,
        title=title,
        content=content,
        scope=scope,
        private=private,
        expires_at=expires_at,
    )


def test_compaction_deduplicates_and_marks_contradictions(tmp_path):
    store = StrategicMemoryStore(tmp_path / "memory.jsonl")
    first = SessionHandoff("s1", "project-a", items=[_item("Runtime", "Python 3.12")])
    assert len(store.compact(first)) == 1
    assert store.compact(first) == []

    second = SessionHandoff("s2", "project-a", items=[_item("Runtime", "Python 3.13")])
    added = store.compact(second)
    memories = store.retrieve("Runtime", project_id="project-a")

    assert len(added) == 1
    assert added[0].contradicts
    assert all(memory.contradicts for memory in memories)


def test_project_scope_prevents_cross_project_contamination(tmp_path):
    store = StrategicMemoryStore(tmp_path / "memory.jsonl")
    store.compact(SessionHandoff("s1", "project-a", items=[_item("Database", "Postgres")]))
    store.compact(SessionHandoff("s2", "project-b", items=[_item("Database", "SQLite")]))

    project_a = store.retrieve("Database", project_id="project-a")

    assert [memory.content for memory in project_a] == ["Postgres"]


def test_global_and_matching_organization_are_visible(tmp_path):
    store = StrategicMemoryStore(tmp_path / "memory.jsonl")
    store.compact(SessionHandoff(
        "s1",
        "project-a",
        organization_id="org-a",
        items=[
            _item("Global rule", "Use provenance", scope=MemoryScope.GLOBAL),
            _item("Org rule", "Use gateway", scope=MemoryScope.ORGANIZATION),
        ],
    ))

    visible = store.retrieve(
        "rule", project_id="project-b", organization_id="org-a"
    )
    assert {memory.title for memory in visible} == {"Global rule", "Org rule"}


def test_expiry_private_export_and_retrieval_budget(tmp_path):
    store = StrategicMemoryStore(tmp_path / "memory.jsonl")
    store.compact(SessionHandoff(
        "s1",
        "project-a",
        items=[
            _item("Expired", "old", expires_at=time.time() - 1),
            _item("Private", "observation", private=True),
            _item("Long", "x" * 400),
            _item("Short", "usable"),
        ],
    ))

    retrieved = store.retrieve("Short", project_id="project-a", token_budget=20)
    exported = store.export(project_id="project-a")

    assert "Short" in {memory.title for memory in retrieved}
    assert "Expired" not in {memory.title for memory in retrieved}
    assert "Long" not in {memory.title for memory in retrieved}
    assert "Private" not in {item["title"] for item in exported}
    assert "Expired" not in {item["title"] for item in exported}


def test_per_class_limit_and_compact_context_reduce_transcript_size(tmp_path):
    store = StrategicMemoryStore(tmp_path / "memory.jsonl")
    transcript = "discussion " * 1000
    store.compact(SessionHandoff(
        "s1",
        "project-a",
        items=[
            _item("Fact one", "Use SQLite"),
            _item("Fact two", "Use FTS5"),
            _item(
                "Procedure",
                "Run tests before commit",
                memory_class=MemoryClass.PROCEDURAL,
            ),
        ],
    ))

    retrieved = store.retrieve(
        "Use tests", project_id="project-a", per_class_limit=1, token_budget=100
    )
    compact_chars = sum(len(item.title) + len(item.content) for item in retrieved)

    assert len([m for m in retrieved if m.memory_class is MemoryClass.SEMANTIC]) == 1
    assert compact_chars < len(transcript)
