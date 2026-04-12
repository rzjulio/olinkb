from dataclasses import replace

import pytest

from olinkb.app import OlinKBApp
from olinkb.config import Settings


class FakeStorage:
    def __init__(self) -> None:
        self.ensure_member_calls: list[tuple[str, str]] = []
        self.save_memory_calls: list[dict[str, object]] = []
        self.session_rows: dict[str, dict[str, object]] = {}
        self.end_session_calls: list[dict[str, object]] = []
        self.search_memory_results: list[dict[str, object]] = []
        self.search_session_results: list[dict[str, object]] = []
        self.touched_memory_ids: list[str] = []

    async def ensure_member(self, username: str, team: str) -> dict:
        self.ensure_member_calls.append((username, team))
        return {"id": "member-1", "team": team}

    async def start_session(self, author_id: str, author_username: str, project: str | None) -> str:
        return "session-1"

    async def load_boot_memories(self, username: str, project: str | None) -> list[dict]:
        return []

    async def save_memory(self, **kwargs):
        self.save_memory_calls.append(kwargs)
        return {"status": kwargs.get("status", "created"), "uri": kwargs["uri"]}

    async def search_memories(self, **kwargs):
        return self.search_memory_results

    async def search_session_summaries(self, **kwargs):
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
            "content": "Goal: improve memory capture\nAccomplished: strengthened instructions",
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
    app.sessions.start(session_id="session-1", author="rzjulio", project="olinkb")

    results = await app.remember(query="memory capture", scope="project", limit=5, session_id="session-1")

    assert results[0]["result_type"] == "session_summary"
    assert results[1]["id"] == "memory-1"
    assert storage.touched_memory_ids == ["memory-1"]


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