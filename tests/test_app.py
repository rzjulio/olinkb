from dataclasses import replace

import pytest

from olinkb.app import OlinKBApp
from olinkb.config import Settings


class FakeStorage:
    def __init__(self) -> None:
        self.ensure_member_calls: list[tuple[str, str]] = []
        self.ensure_project_member_calls: list[dict[str, object]] = []
        self.boot_memory_calls: list[dict[str, object]] = []
        self.save_memory_calls: list[dict[str, object]] = []
        self.propose_calls: list[dict[str, object]] = []
        self.review_calls: list[dict[str, object]] = []
        self.pending_proposal_calls: list[dict[str, object]] = []
        self.session_rows: dict[str, dict[str, object]] = {}
        self.end_session_calls: list[dict[str, object]] = []
        self.search_memory_results: list[dict[str, object]] = []
        self.search_session_results: list[dict[str, object]] = []
        self.search_memory_calls: list[dict[str, object]] = []
        self.search_session_calls: list[dict[str, object]] = []
        self.touched_memory_ids: list[str] = []
        self.member_role = "developer"
        self.project_role = "developer"
        self.pending_proposals_result: dict[str, object] = {"total_count": 0, "proposals": []}

    async def ensure_member(self, username: str, team: str) -> dict:
        self.ensure_member_calls.append((username, team))
        return {"id": "member-1", "team": team, "role": self.member_role}

    async def ensure_project_member(self, **kwargs):
        self.ensure_project_member_calls.append(kwargs)
        return {
            "id": "project-member-1",
            "project": kwargs["project"],
            "member_id": kwargs["member_id"],
            "username": kwargs["username"],
            "team": kwargs["team"],
            "role": self.project_role,
            "is_active": True,
        }

    async def start_session(self, author_id: str, author_username: str, project: str | None) -> str:
        return "session-1"

    async def load_boot_memories(
        self,
        username: str,
        project: str | None,
        full_content_limit: int = 5,
    ) -> list[dict]:
        self.boot_memory_calls.append(
            {
                "username": username,
                "project": project,
                "full_content_limit": full_content_limit,
            }
        )
        return []

    async def save_memory(self, **kwargs):
        self.save_memory_calls.append(kwargs)
        return {"status": kwargs.get("status", "created"), "uri": kwargs["uri"]}

    async def propose_memory_promotion(self, **kwargs):
        self.propose_calls.append(kwargs)
        return {
            "status": "pending",
            "uri": kwargs["uri"],
            "proposed_memory_type": kwargs["proposed_memory_type"],
            "approval_status": "pending",
        }

    async def load_pending_proposals(self, **kwargs):
        self.pending_proposal_calls.append(kwargs)
        return self.pending_proposals_result

    async def review_memory_proposal(self, **kwargs):
        self.review_calls.append(kwargs)
        return {
            "status": "approved" if kwargs["action"] == "approve" else "rejected",
            "uri": kwargs["uri"],
            "approval_status": "approved" if kwargs["action"] == "approve" else "rejected",
        }

    async def search_memories(self, **kwargs):
        self.search_memory_calls.append(kwargs)
        return self.search_memory_results

    async def search_session_summaries(self, **kwargs):
        self.search_session_calls.append(kwargs)
        return self.search_session_results

    async def touch_memories(self, memory_ids: list[str]):
        self.touched_memory_ids.extend(memory_ids)

    async def end_session(self, **kwargs):
        self.end_session_calls.append(kwargs)
        session = self.session_rows.setdefault(
            kwargs["session_id"],
            {
                "id": kwargs["session_id"],
                "author_username": "rzjulio",
                "project": "olinkb",
                "summary": None,
                "memories_read": kwargs["memories_read"],
                "memories_written": kwargs["memories_written"],
                "ended_at": None,
            },
        )
        session["summary"] = kwargs["summary"]
        session["memories_read"] = kwargs["memories_read"]
        session["memories_written"] = kwargs["memories_written"]
        session["ended_at"] = "ended"

    async def get_session(self, session_id: str):
        return self.session_rows.get(session_id)


@pytest.mark.asyncio
async def test_boot_session_accepts_explicit_team_override() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    app.storage = FakeStorage()

    result = await app.boot_session(author="rzjulio", team="override-team", project="olinkb")

    assert app.storage.ensure_member_calls == [("rzjulio", "override-team")]
    assert result["team"] == "override-team"


@pytest.mark.asyncio
async def test_boot_session_includes_review_queue_for_project_approvers() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.member_role = "lead"
    storage.project_role = "lead"
    storage.pending_proposals_result = {"total_count": 1, "proposals": [{"uri": "project://olinkb/decisions/d1"}]}
    app.storage = storage

    result = await app.boot_session(author="rzjulio", project="olinkb")

    assert result["review_queue"]["total_count"] == 1
    assert storage.pending_proposal_calls[0]["project"] == "olinkb"


@pytest.mark.asyncio
async def test_boot_session_uses_hybrid_boot_payload_limit() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    app.storage = storage

    await app.boot_session(author="rzjulio", project="olinkb")

    assert storage.boot_memory_calls[0]["full_content_limit"] == 5


@pytest.mark.asyncio
async def test_save_memory_accepts_bugfix_memory_type() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    app.storage = FakeStorage()

    result = await app.save_memory(
        uri="project://olinkb/bugfixes/save-memory-memory-type",
        title="Accept bugfix memory type",
        content="What: save_memory now accepts bugfix as a valid memory_type.",
        memory_type="bugfix",
        scope="project",
    )

    assert result["status"] == "created"
    assert app.storage.save_memory_calls[0]["memory_type"] == "bugfix"


@pytest.mark.asyncio
async def test_save_memory_blocks_direct_project_convention_for_non_approver() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.project_role = "developer"
    app.storage = storage

    with pytest.raises(PermissionError, match="explicitly call propose_memory_promotion"):
        await app.save_memory(
            uri="project://olinkb/conventions/new-standard",
            title="New standard",
            content="What: Important pattern",
            memory_type="convention",
            scope="project",
        )


@pytest.mark.asyncio
async def test_save_memory_does_not_queue_convention_review_without_explicit_proposal() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.project_role = "developer"
    app.storage = storage

    result = await app.save_memory(
        uri="project://olinkb/decisions/richer-memory-context",
        title="Persist richer memory context",
        content="What: Save the concrete pattern first.",
        memory_type="decision",
        scope="project",
    )

    assert result["status"] == "created"
    assert storage.propose_calls == []


@pytest.mark.asyncio
async def test_save_memory_passes_explicit_metadata_to_storage() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    app.storage = FakeStorage()

    metadata = {
        "what": "Persist richer memory context",
        "decision": "Store structured metadata alongside content",
        "next_steps": "Add retrieval enrichment",
    }

    await app.save_memory(
        uri="project://olinkb/decisions/richer-memory-context",
        title="Persist richer memory context",
        content="What: Persist richer memory context\nDecision: Store structured metadata alongside content",
        memory_type="decision",
        scope="project",
        metadata=metadata,
    )

    assert app.storage.save_memory_calls[0]["metadata"] == metadata


@pytest.mark.asyncio
async def test_propose_memory_promotion_uses_project_scope_and_returns_pending() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.project_role = "developer"
    app.storage = storage

    result = await app.propose_memory_promotion(
        uri="project://olinkb/decisions/richer-memory-context",
        rationale="This pattern should become the standard approach.",
        target_memory_type="standard",
    )

    assert result["approval_status"] == "pending"
    assert storage.propose_calls[0]["proposed_memory_type"] == "convention"


@pytest.mark.asyncio
async def test_review_memory_proposal_requires_project_approver() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.project_role = "lead"
    app.storage = storage

    result = await app.review_memory_proposal(
        uri="project://olinkb/decisions/richer-memory-context",
        action="approve",
        note="Approved as the default project convention.",
    )

    assert result["approval_status"] == "approved"
    assert storage.review_calls[0]["action"] == "approve"


@pytest.mark.asyncio
async def test_list_pending_approvals_requires_project_approver() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.project_role = "lead"
    storage.pending_proposals_result = {"total_count": 2, "proposals": [{"uri": "project://olinkb/decisions/d1"}]}
    app.storage = storage

    result = await app.list_pending_approvals()

    assert result["total_count"] == 2
    assert storage.pending_proposal_calls[0]["project"] == "olinkb"


@pytest.mark.asyncio
async def test_end_session_recovers_persisted_session_when_memory_state_is_missing() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.session_rows["session-1"] = {
        "id": "session-1",
        "author_username": "rzjulio",
        "project": "olinkb",
        "summary": None,
        "memories_read": 0,
        "memories_written": 0,
        "ended_at": None,
    }
    app.storage = storage

    result = await app.end_session("session-1", "Recovered end")

    assert result["status"] == "recovered"
    assert result["author"] == "rzjulio"
    assert storage.end_session_calls[0]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_end_session_raises_clear_error_for_unknown_session() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    app.storage = FakeStorage()

    with pytest.raises(ValueError, match="Unknown session_id"):
        await app.end_session("missing-session", "Nope")


@pytest.mark.asyncio
async def test_remember_merges_memory_and_session_summary_results() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.search_memory_results = [
        {
            "id": "memory-1",
            "uri": "project://olinkb/decisions/richer-memory-context",
            "title": "Persist richer memory context",
            "content": "What: Persist richer memory context",
            "memory_type": "decision",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "relevance": 0.81,
            "updated_at": "2026-04-12T00:00:00+00:00",
        }
    ]
    storage.search_session_results = [
        {
            "result_type": "session_summary",
            "session_id": "session-42",
            "uri": "project://olinkb/sessions/session-42",
            "title": "Session summary olinkb session-42",
            "summary": "Goal: improve memory capture\nAccomplished: strengthened instructions",
            "memory_type": "session_summary",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "relevance": 0.92,
            "ended_at": "2026-04-12T01:00:00+00:00",
            "updated_at": "2026-04-12T01:00:00+00:00",
        }
    ]
    app.storage = storage
    app.sessions.start(session_id="session-1", author="rzjulio", team="default-team", project="olinkb")

    results = await app.remember(query="memory capture", scope="project", limit=5, session_id="session-1")

    assert results[0]["result_type"] == "session_summary"
    assert "content" not in results[0]
    assert results[1]["id"] == "memory-1"
    assert storage.touched_memory_ids == ["memory-1"]
    assert storage.search_memory_calls[0]["include_content"] is False
    assert storage.search_memory_calls[0]["username"] == "rzjulio"
    assert storage.search_memory_calls[0]["team"] == "default-team"
    assert storage.search_memory_calls[0]["project"] == "olinkb"


@pytest.mark.asyncio
async def test_remember_can_explicitly_include_full_memory_content() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    storage.search_memory_results = [
        {
            "id": "memory-1",
            "uri": "project://olinkb/decisions/richer-memory-context",
            "title": "Persist richer memory context",
            "content": "What: Persist richer memory context",
            "memory_type": "decision",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "relevance": 0.81,
            "updated_at": "2026-04-12T00:00:00+00:00",
        }
    ]
    app.storage = storage

    results = await app.remember(
        query="memory context",
        scope="project",
        limit=5,
        include_content=True,
    )

    assert results[0]["content"] == "What: Persist richer memory context"
    assert storage.search_memory_calls[0]["include_content"] is True
    assert storage.search_memory_calls[0]["username"] == "rzjulio"
    assert storage.search_memory_calls[0]["team"] == "default-team"
    assert storage.search_memory_calls[0]["project"] == "olinkb"


@pytest.mark.asyncio
async def test_remember_uses_active_session_context_for_scoping() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="default-user",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    app.storage = storage

    boot = await app.boot_session(author="rzjulio", team="override-team", project="other-project")
    await app.remember(query="memory context", scope="all", limit=5, session_id=boot["session_id"])

    assert storage.search_memory_calls[0]["username"] == "rzjulio"
    assert storage.search_memory_calls[0]["team"] == "override-team"
    assert storage.search_memory_calls[0]["project"] == "other-project"


@pytest.mark.asyncio
async def test_end_session_promotes_valuable_summary_to_memory() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    app.storage = storage
    await app.boot_session(author="rzjulio", project="olinkb")

    summary = (
        "Goal: Improve memory usefulness\n"
        "Discoveries: Session summaries are not queried by remember today\n"
        "Accomplished: Added retrieval over session summaries and promoted valuable closures into memories\n"
        "Next Steps: Surface session summaries more clearly in the viewer"
    )

    result = await app.end_session("session-1", summary)

    assert result["memories_written"] == 1
    assert storage.save_memory_calls[0]["uri"] == "project://olinkb/sessions/session-1"
    assert storage.save_memory_calls[0]["memory_type"] == "event"


@pytest.mark.asyncio
async def test_end_session_keeps_brief_summary_as_session_only() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    app.storage = storage
    await app.boot_session(author="rzjulio", project="olinkb")

    result = await app.end_session("session-1", "Closed session after quick check.")

    assert result["memories_written"] == 0
    assert storage.save_memory_calls == []