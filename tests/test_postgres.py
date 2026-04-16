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
                "approval_status": args[11] if len(args) > 11 else "approved",
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


class ProjectMemberPool:
    def __init__(self) -> None:
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object):
        self.fetchrow_calls.append((query, args))
        if "SELECT id, project, member_id, username, team, role, is_active\n            FROM project_members" in query:
            return None
        if "INSERT INTO project_members" in query:
            return {
                "id": uuid4(),
                "project": args[0],
                "member_id": args[1],
                "username": args[2],
                "team": args[3],
                "role": args[4],
                "is_active": True,
            }
        raise AssertionError(f"Unexpected fetchrow query: {query}")


class ProposalConnection:
    def __init__(self) -> None:
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object):
        self.fetchrow_calls.append((query, args))
        if "SELECT id, uri, scope, namespace, memory_type, proposed_memory_type, approval_status" in query:
            return {
                "id": uuid4(),
                "uri": args[0],
                "scope": "project",
                "namespace": "project://olinkb",
                "memory_type": "decision",
                "proposed_memory_type": "convention",
                "approval_status": "pending",
            }
        if "SET proposed_memory_type = $2" in query:
            return {
                "id": uuid4(),
                "uri": args[0],
                "namespace": "project://olinkb",
                "scope": "project",
                "memory_type": "decision",
                "proposed_memory_type": args[1],
                "approval_status": "pending",
            }
        if "SET memory_type = proposed_memory_type" in query:
            return {
                "id": uuid4(),
                "uri": args[0],
                "namespace": "project://olinkb",
                "scope": "project",
                "memory_type": "convention",
                "proposed_memory_type": "convention",
                "approval_status": "approved",
            }
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args: object):
        self.execute_calls.append((query, args))


class ProposalPool:
    def __init__(self, connection: ProposalConnection) -> None:
        self.connection = connection

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)


class PendingProposalPool:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object):
        self.fetchval_calls.append((query, args))
        return 2

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        return [
            {
                "id": uuid4(),
                "uri": "project://olinkb/decisions/richer-memory-context",
                "title": "Persist richer memory context",
                "content": "What: Persist richer memory context",
                "memory_type": "decision",
                "proposed_memory_type": "convention",
                "approval_status": "pending",
                "author_username": "rzjulio",
                "proposed_by_username": "rzjulio",
                "proposed_at": datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
                "proposal_note": "Should become the standard",
                "scope": "project",
                "namespace": "project://olinkb",
                "metadata": "{}",
                "updated_at": datetime(2026, 4, 12, 12, 5, tzinfo=timezone.utc),
            }
        ]


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


class TenantQueryPool:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        if "FROM memories AS m" not in query:
            raise AssertionError(f"Unexpected fetch query: {query}")
        return [
            {
                "id": uuid4(),
                "uri": "project://olinkb/decisions/richer-memory-context",
                "title": "Persist richer memory context",
                "content": "What: Persist richer memory context",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                "metadata": "{}",
                "relevance": 0.91,
            }
        ]


class BootQueryPool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        if "uri LIKE 'system://%'" not in query:
            raise AssertionError(f"Unexpected query: {query}")
        return self.rows


class BenchmarkQueryPool:
    def __init__(self, boot_rows: list[dict[str, object]], sample_rows: list[dict[str, object]]) -> None:
        self.boot_rows = boot_rows
        self.sample_rows = sample_rows
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        if "uri LIKE 'system://%'" in query:
            return self.boot_rows
        if "FROM memories" in query and "LIMIT $1" in query:
            return self.sample_rows[: int(args[0])]
        raise AssertionError(f"Unexpected query: {query}")


class ViewerQueryPool:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []

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

    async def fetchval(self, query: str, *args: object):
        self.fetchval_calls.append((query, args))
        if "SELECT COUNT(*)" not in query:
            raise AssertionError(f"Unexpected fetchval query: {query}")
        return 7


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
Evidence: query payloads were too thin in practice
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
        "evidence": "query payloads were too thin in practice",
        "next_steps": "Update remember and viewer payloads",
    }


@pytest.mark.asyncio
async def test_ensure_project_member_creates_default_project_membership() -> None:
    storage = PostgresStorage("postgresql://unused")
    storage._pool = ProjectMemberPool()

    result = await storage.ensure_project_member(
        member_id=uuid4(),
        username="rzjulio",
        project="olinkb",
        team="rz-develop",
        default_role="developer",
    )

    assert result["project"] == "olinkb"
    assert result["role"] == "developer"


@pytest.mark.asyncio
async def test_propose_memory_promotion_marks_memory_pending() -> None:
    storage = PostgresStorage("postgresql://unused")
    connection = ProposalConnection()
    storage._pool = ProposalPool(connection)

    result = await storage.propose_memory_promotion(
        uri="project://olinkb/decisions/richer-memory-context",
        proposed_memory_type="convention",
        rationale="This should become the project standard",
        actor_id=uuid4(),
        actor_username="rzjulio",
    )

    assert result["approval_status"] == "pending"
    assert result["proposed_memory_type"] == "convention"
    assert any("propose_promotion" in query for query, _ in connection.execute_calls)


@pytest.mark.asyncio
async def test_review_memory_proposal_approves_pending_convention() -> None:
    storage = PostgresStorage("postgresql://unused")
    connection = ProposalConnection()
    storage._pool = ProposalPool(connection)

    result = await storage.review_memory_proposal(
        uri="project://olinkb/decisions/richer-memory-context",
        action="approve",
        note="Approved",
        reviewer_id=uuid4(),
        reviewer_username="lead-user",
    )

    assert result["approval_status"] == "approved"
    assert result["memory_type"] == "convention"


@pytest.mark.asyncio
async def test_load_pending_proposals_returns_count_and_lean_payloads() -> None:
    storage = PostgresStorage("postgresql://unused")
    storage._pool = PendingProposalPool()

    result = await storage.load_pending_proposals(project="olinkb", limit=5)

    assert result["total_count"] == 2
    assert result["proposals"][0]["approval_status"] == "pending"
    assert result["proposals"][0]["proposed_memory_type"] == "convention"
    assert "content" not in result["proposals"][0]


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
async def test_search_memories_omits_content_by_default_for_lean_payloads() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(
        metadata='{"what": "Stored metadata wins"}',
        content="What: Persist richer memory context",
    )
    storage._pool = pool

    search_results = await storage.search_memories(query="richer memory", scope="project", limit=5)

    assert "content" not in search_results[0]


@pytest.mark.asyncio
async def test_search_memories_can_include_content_when_requested() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(
        metadata='{"what": "Stored metadata wins"}',
        content="What: Persist richer memory context",
    )
    storage._pool = pool

    search_results = await storage.search_memories(
        query="richer memory",
        scope="project",
        limit=5,
        include_content=True,
    )

    assert search_results[0]["content"] == "What: Persist richer memory context"


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
            "Evidence: Existing rows predate the metadata column\n"
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
        "evidence": "Existing rows predate the metadata column",
        "next_steps": "Keep stored metadata authoritative",
    }

    assert search_results[0]["metadata"] == expected
    assert boot_results[0]["metadata"] == expected
    assert snapshot["memories"][0]["metadata"] == expected


@pytest.mark.asyncio
async def test_load_boot_memories_keeps_full_content_only_for_prioritized_prefix() -> None:
    storage = PostgresStorage("postgresql://unused")
    rows = [
        {
            "uri": f"system://config-{index}",
            "title": f"Config {index}",
            "content": f"What: Full content {index}",
            "memory_type": "decision",
            "scope": "system",
            "namespace": "system://config",
            "author_username": "rzjulio",
            "metadata": "{}",
            "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        }
        for index in range(7)
    ]
    storage._pool = BootQueryPool(rows)

    boot_results = await storage.load_boot_memories(
        username="rzjulio",
        project="olinkb",
        full_content_limit=3,
    )

    assert boot_results[0]["content"] == "What: Full content 0"
    assert boot_results[1]["content"] == "What: Full content 1"
    assert boot_results[2]["content"] == "What: Full content 2"
    assert "content" not in boot_results[3]
    assert "content" not in boot_results[6]


@pytest.mark.asyncio
async def test_load_boot_memories_reranks_full_content_toward_higher_value_memory_types() -> None:
    storage = PostgresStorage("postgresql://unused")
    rows = [
        {
            "uri": "project://olinkb/preferences/p1",
            "title": "Preference one",
            "content": "Preference body",
            "memory_type": "preference",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "metadata": "{}",
            "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        },
        {
            "uri": "project://olinkb/events/e1",
            "title": "Event one",
            "content": "Event body",
            "memory_type": "event",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "metadata": "{}",
            "updated_at": datetime(2026, 4, 11, 11, 0, tzinfo=timezone.utc),
        },
        {
            "uri": "project://olinkb/decisions/d1",
            "title": "Decision one",
            "content": "Decision body",
            "memory_type": "decision",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "metadata": '{"what": "Important decision"}',
            "updated_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
        },
        {
            "uri": "project://olinkb/conventions/c1",
            "title": "Convention one",
            "content": "Convention body",
            "memory_type": "convention",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "metadata": '{"what": "Critical convention"}',
            "updated_at": datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
        },
    ]
    storage._pool = BootQueryPool(rows)

    boot_results = await storage.load_boot_memories(
        username="rzjulio",
        project="olinkb",
        full_content_limit=2,
    )

    assert "content" not in boot_results[0]
    assert "content" not in boot_results[1]
    assert boot_results[2]["content"] == "Decision body"
    assert boot_results[3]["content"] == "Convention body"


@pytest.mark.asyncio
async def test_search_memories_lean_payload_adds_preview() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = QueryPool(
        metadata='{"what": "Stored metadata wins"}',
        content="What: Persist richer memory context",
    )
    storage._pool = pool

    search_results = await storage.search_memories(query="richer memory", scope="project", limit=5)

    assert search_results[0]["preview"] == "What: Stored metadata wins"


@pytest.mark.asyncio
async def test_search_memories_applies_project_team_and_personal_scoping() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = TenantQueryPool()
    storage._pool = pool

    await storage.search_memories(
        query="richer memory",
        scope="all",
        limit=5,
        username="rzjulio",
        team="rz-develop",
        project="olinkb",
    )

    query, args = pool.fetch_calls[0]
    assert "m.author_username = $4" in query
    assert "m.namespace = $5" in query
    assert "tm.team = $6" in query
    assert args[3] == "rzjulio"
    assert args[4] == "project://olinkb"
    assert args[5] == "rz-develop"


@pytest.mark.asyncio
async def test_search_memories_matches_documentation_queries_against_tags_and_type_terms() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = TenantQueryPool()
    storage._pool = pool

    await storage.search_memories(
        query="hay documentacion tecnica global",
        scope="all",
        limit=5,
        username="rzjulio",
        team="rz-develop",
        project="olinkb",
    )

    query, args = pool.fetch_calls[0]
    assert "m.memory_type ILIKE '%' || term || '%'" in query
    assert "unnest(COALESCE(m.tags, ARRAY[]::text[]))" in query
    assert "COALESCE(m.metadata::text, '') ILIKE '%' || term || '%'" in query
    assert "documentacion" in args[6]
    assert "documentation" in args[6]
    assert "tecnica" in args[6]
    assert "technical-documentation" in args[6]
    assert "global" in args[6]


@pytest.mark.asyncio
async def test_benchmark_payloads_reports_boot_and_sample_savings() -> None:
    storage = PostgresStorage("postgresql://unused")
    boot_rows = [
        {
            "uri": f"system://boot-{index}",
            "title": f"Boot {index}",
            "content": f"What: Boot content {index} " + ("x" * 120),
            "memory_type": "decision" if index >= 2 else "preference",
            "scope": "system",
            "namespace": "system://boot",
            "author_username": "rzjulio",
            "metadata": '{}' if index < 2 else '{"what": "Boot value"}',
            "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        }
        for index in range(4)
    ]
    sample_rows = [
        {
            "id": uuid4(),
            "uri": f"project://olinkb/decisions/{index}",
            "title": f"Decision {index}",
            "content": "What: Sample content " + ("y" * 160),
            "memory_type": "decision",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "tags": ["sample"],
            "metadata": '{"what": "Sample value"}',
            "vitality_score": 1.0,
            "retrieval_count": 0,
            "last_accessed": None,
            "deleted_at": None,
            "created_at": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
        }
        for index in range(3)
    ]
    storage._pool = BenchmarkQueryPool(boot_rows=boot_rows, sample_rows=sample_rows)

    benchmark = await storage.benchmark_payloads(
        username="rzjulio",
        project="olinkb",
        sample_size=3,
        boot_limit=4,
        boot_full_content_limit=2,
    )

    assert benchmark["boot"]["savings"]["approx_tokens"] > 0
    assert benchmark["sample"]["savings"]["approx_tokens"] > 0
    assert benchmark["sample"]["lean"]["bytes"] < benchmark["sample"]["full"]["bytes"]


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
    assert "content" not in results[0]
    assert results[0]["metadata"]["goal"] == "Improve memory capture"
    assert results[0]["scope"] == "project"


@pytest.mark.asyncio
async def test_search_viewer_memories_uses_title_content_query_and_cursor_pagination() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = ViewerQueryPool()
    storage._pool = pool

    results = await storage.search_viewer_memories(
        query="viewer search",
        limit=2,
        cursor=None,
        team="rz-develop",
        project="olinkb",
    )

    assert len(results["memories"]) == 2
    assert results["page_info"]["has_next"] is True
    assert results["page_info"]["next_cursor"]["relevance"] == 0.77
    assert results["page_info"]["next_cursor"]["updated_at"] == "2026-04-11T11:00:00+00:00"

    query, args = pool.fetch_calls[0]
    assert "title % $1" in query
    assert "content % $1" in query
    assert "title ILIKE '%' || $1 || '%'" in query
    assert "content ILIKE '%' || $1 || '%'" in query
    assert "m.memory_type ILIKE '%' || term || '%'" in query
    assert "unnest(COALESCE(m.tags, ARRAY[]::text[]))" in query
    assert "uri % $1" not in query
    assert "($2::text IS NULL OR m.namespace = $2)" in query
    assert "($3::text IS NULL OR tm.team = $3)" in query
    assert args[0] == "viewer search"
    assert args[1] == "project://olinkb"
    assert args[2] == "rz-develop"
    assert args[6] == 3
    assert args[7] == ["viewer", "search"]


@pytest.mark.asyncio
async def test_search_viewer_memories_without_filters_includes_all_non_personal_scopes() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = ViewerQueryPool()
    storage._pool = pool

    await storage.search_viewer_memories(
        query="",
        limit=2,
        cursor=None,
        team=None,
        project=None,
    )

    query, args = pool.fetch_calls[0]
    assert "($2::text IS NULL OR m.namespace = $2)" in query
    assert "($3::text IS NULL OR tm.team = $3)" in query
    assert args[0] == ""
    assert args[1] is None
    assert args[2] is None
    assert args[6] == 3


@pytest.mark.asyncio
async def test_count_viewer_memories_without_filters_uses_global_non_personal_scope() -> None:
    storage = PostgresStorage("postgresql://unused")
    pool = ViewerQueryPool()
    storage._pool = pool

    result = await storage.count_viewer_memories(query="", team=None, project=None)

    query, args = pool.fetchval_calls[0]
    assert result == 7
    assert "($2::text IS NULL OR m.namespace = $2)" in query
    assert "($3::text IS NULL OR tm.team = $3)" in query
    assert args[0] == ""
    assert args[1] is None
    assert args[2] is None