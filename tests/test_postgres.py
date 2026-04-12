import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from olinkb.storage.postgres import PostgresStorage


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SaveConnection:
    def __init__(self) -> None:
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object):
        self.fetchrow_calls.append((query, args))
        if query.startswith("SELECT id, content, content_hash"):
            return None
        if "INSERT INTO memories" in query:
            return {
                "id": uuid4(),
                "uri": args[0],
                "namespace": args[5],
                "scope": args[4],
            }
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args: object):
        self.execute_calls.append((query, args))

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class SavePool:
    def __init__(self, connection: SaveConnection) -> None:
        self.connection = connection

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)


class QueryPool:
    def __init__(self, *, metadata: object, content: str) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.metadata = metadata
        self.content = content

    def _memory_row(self) -> dict[str, object]:
        return {
            "id": uuid4(),
            "uri": "project://olinkb/decisions/richer-memory-context",
            "title": "Persist richer memory context",
            "content": self.content,
            "memory_type": "decision",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
            "metadata": self.metadata,
        }

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        if "GREATEST(" in query:
            return [{**self._memory_row(), "relevance": 0.91}]
        if "uri LIKE 'system://%'" in query:
            row = self._memory_row()
            row.pop("id")
            return [row]
        if "FROM memories" in query and "ORDER BY updated_at DESC, created_at DESC" in query:
            return [
                {
                    **self._memory_row(),
                    "tags": ["memory"],
                    "vitality_score": 1.0,
                    "retrieval_count": 3,
                    "last_accessed": None,
                    "deleted_at": None,
                    "created_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
                }
            ]
        if "FROM sessions" in query:
            return []
        if "FROM audit_log" in query:
            return []
        if "FROM team_members" in query:
            return []
        raise AssertionError(f"Unexpected fetch query: {query}")


class ViewerQueryPool:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        if "WITH ranked AS" not in query:
            raise AssertionError(f"Unexpected query: {query}")
        return [
            {
                "id": uuid4(),
                "uri": "project://olinkb/decisions/search-1",
                "title": "Search one",
                "content": "Matches the viewer search content",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "metadata": "{}",
                "tags": ["viewer"],
                "vitality_score": 1.0,
                "retrieval_count": 2,
                "last_accessed": None,
                "deleted_at": None,
                "created_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                "relevance": 0.91,
            },
            {
                "id": uuid4(),
                "uri": "project://olinkb/decisions/search-2",
                "title": "Search two",
                "content": "Also matches title and content",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "metadata": "{}",
                "tags": ["viewer"],
                "vitality_score": 1.0,
                "retrieval_count": 1,
                "last_accessed": None,
                "deleted_at": None,
                "created_at": datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 4, 11, 11, 0, tzinfo=timezone.utc),
                "relevance": 0.77,
            },
            {
                "id": uuid4(),
                "uri": "project://olinkb/decisions/search-3",
                "title": "Search three",
                "content": "Third row proves cursor pagination",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "metadata": "{}",
                "tags": ["viewer"],
                "vitality_score": 1.0,
                "retrieval_count": 0,
                "last_accessed": None,
                "deleted_at": None,
                "created_at": datetime(2026, 4, 11, 8, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
                "relevance": 0.61,
            },
        ]


@pytest.mark.asyncio
async def test_save_memory_persists_explicit_metadata() -> None:
    storage = PostgresStorage("postgresql://unused")
    connection = SaveConnection()
    storage._pool = SavePool(connection)

    metadata = {
        "what": "Persist richer memory context",
        "decision": "Store structured metadata alongside content",
        "next_steps": "Enrich retrieval paths",
    }

    await storage.save_memory(
        uri="project://olinkb/decisions/richer-memory-context",
        title="Persist richer memory context",
        content="What: Persist richer memory context",
        memory_type="decision",
        scope="project",
        tags=["memory"],
        metadata=metadata,
        author_id=uuid4(),
        author_username="rzjulio",
    )

    insert_query, insert_args = next(
        (query, args) for query, args in connection.fetchrow_calls if "INSERT INTO memories" in query
    )

    assert "metadata" in insert_query
    assert json.loads(insert_args[10]) == metadata


@pytest.mark.asyncio
async def test_save_memory_extracts_metadata_from_structured_content() -> None:
    storage = PostgresStorage("postgresql://unused")
    connection = SaveConnection()
    storage._pool = SavePool(connection)

    content = """What: Persist richer memory context
Why: Retrieved notes need reusable structure
Where: src/olinkb/storage/postgres.py
Learned: Structured context travels better than terse blobs
Context: Thin retrievals hide the useful detail
Decision: Add JSONB metadata with extraction fallback
Next Steps: Update remember and viewer payloads
"""

    await storage.save_memory(
        uri="project://olinkb/decisions/richer-memory-context",
        title="Persist richer memory context",
        content=content,
        memory_type="decision",
        scope="project",
        tags=["memory"],
        metadata=None,
        author_id=uuid4(),
        author_username="rzjulio",
    )

    _, insert_args = next((query, args) for query, args in connection.fetchrow_calls if "INSERT INTO memories" in query)
    assert json.loads(insert_args[10]) == {
        "what": "Persist richer memory context",
        "why": "Retrieved notes need reusable structure",
        "where": "src/olinkb/storage/postgres.py",
        "learned": "Structured context travels better than terse blobs",
        "context": "Thin retrievals hide the useful detail",
        "decision": "Add JSONB metadata with extraction fallback",
        "next_steps": "Update remember and viewer payloads",
    }


@pytest.mark.asyncio
async def test_search_load_and_export_paths_keep_stored_metadata_authoritative() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(
        metadata='{"what": "Stored metadata wins"}',
        content=(
            "What: Extracted metadata should not replace stored data\n"
            "Decision: Preserve stored metadata when present"
        ),
    )
    storage._pool = pool

    search_results = await storage.search_memories(query="richer memory", scope="project", limit=5)
    boot_results = await storage.load_boot_memories(username="rzjulio", project="olinkb")
    snapshot = await storage.export_viewer_snapshot()

    assert search_results[0]["metadata"] == {"what": "Stored metadata wins"}
    assert boot_results[0]["metadata"] == {"what": "Stored metadata wins"}
    assert snapshot["memories"][0]["metadata"] == {"what": "Stored metadata wins"}
    assert any("metadata" in query for query, _ in pool.fetch_calls)


@pytest.mark.asyncio
async def test_search_load_and_export_paths_extract_legacy_metadata_for_empty_rows() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(
        metadata="{}",
        content=(
            "What: Persist richer memory context\n"
            "Why: Retrieved notes need reusable structure\n"
            "Where: src/olinkb/storage/postgres.py\n"
            "Learned: Structured context travels better than terse blobs\n"
            "Context: Legacy rows still exist without stored metadata\n"
            "Decision: Extract metadata during read serialization\n"
            "Next Steps: Keep stored metadata authoritative"
        ),
    )
    storage._pool = pool

    search_results = await storage.search_memories(query="richer memory", scope="project", limit=5)
    boot_results = await storage.load_boot_memories(username="rzjulio", project="olinkb")
    snapshot = await storage.export_viewer_snapshot()

    expected = {
        "what": "Persist richer memory context",
        "why": "Retrieved notes need reusable structure",
        "where": "src/olinkb/storage/postgres.py",
        "learned": "Structured context travels better than terse blobs",
        "context": "Legacy rows still exist without stored metadata",
        "decision": "Extract metadata during read serialization",
        "next_steps": "Keep stored metadata authoritative",
    }

    assert search_results[0]["metadata"] == expected
    assert boot_results[0]["metadata"] == expected
    assert snapshot["memories"][0]["metadata"] == expected


@pytest.mark.asyncio
async def test_search_path_keeps_empty_metadata_for_unstructured_legacy_content() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(metadata="{}", content="Free form note without structured headings")
    storage._pool = pool

    search_results = await storage.search_memories(query="note", scope="project", limit=5)

    assert search_results[0]["metadata"] == {}


@pytest.mark.asyncio
async def test_search_session_summaries_returns_project_scoped_results() -> None:
    storage = PostgresStorage("postgresql://unused")

    class SessionQueryPool:
        async def fetch(self, query: str, *args: object):
            if "FROM sessions" not in query:
                raise AssertionError(f"Unexpected query: {query}")
            return [
                {
                    "session_id": "session-42",
                    "author_username": "rzjulio",
                    "project": "olinkb",
                    "started_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
                    "ended_at": datetime(2026, 4, 11, 11, 0, tzinfo=timezone.utc),
                    "summary": "Goal: Improve memory capture\nAccomplished: Added richer templates",
                    "relevance": 0.93,
                }
            ]

    storage._pool = SessionQueryPool()

    results = await storage.search_session_summaries(query="memory capture", limit=5, project="olinkb")

    assert results[0]["result_type"] == "session_summary"
    assert results[0]["uri"] == "project://olinkb/sessions/session-42"
    assert results[0]["metadata"]["goal"] == "Improve memory capture"
    assert results[0]["scope"] == "project"


@pytest.mark.asyncio
async def test_search_viewer_memories_uses_title_content_query_and_cursor_pagination() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = ViewerQueryPool()
    storage._pool = pool

    results = await storage.search_viewer_memories(query="viewer search", limit=2, cursor=None)

    assert len(results["memories"]) == 2
    assert results["page_info"]["has_next"] is True
    assert results["page_info"]["next_cursor"]["relevance"] == 0.77
    assert results["page_info"]["next_cursor"]["updated_at"] == "2026-04-11T11:00:00+00:00"

    query, args = pool.fetch_calls[0]
    assert "title % $1" in query
    assert "content % $1" in query
    assert "title ILIKE '%' || $1 || '%'" in query
    assert "content ILIKE '%' || $1 || '%'" in query
    assert "uri % $1" not in query
    assert args[0] == "viewer search"
    assert args[4] == 3