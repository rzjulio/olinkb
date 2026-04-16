from dataclasses import replace
from uuid import UUID, uuid4
from pathlib import Path

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
        session_id = str(uuid4())
        self.session_rows[session_id] = {
            "id": session_id,
            "author_username": author_username,
            "project": project,
            "summary": None,
            "memories_read": 0,
            "memories_written": 0,
            "ended_at": None,
        }
        return session_id

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
        return {
            "status": kwargs.get("status", "created"),
            "uri": kwargs["uri"],
            "approval_status": kwargs.get("approval_status", "approved"),
        }

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

    async def find_open_sessions(self, *, author_username: str, project: str | None, limit: int = 2):
        matches = [
            session
            for session in self.session_rows.values()
            if session.get("author_username") == author_username
            and session.get("project") == project
            and session.get("ended_at") is None
        ]
        matches.sort(key=lambda session: str(session.get("id", "")), reverse=True)
        return matches[:limit]


@pytest.mark.asyncio
async def test_sqlite_storage_roundtrip_save_and_remember(tmp_path) -> None:
    settings = Settings(
        pg_url=None,
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        storage_backend="sqlite",
        sqlite_path=tmp_path / "olinkb.db",
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)

    try:
        boot = await app.boot_session(author="rzjulio", project="olinkb")
        saved = await app.save_memory(
            uri="project://olinkb/decisions/sqlite-backend",
            title="SQLite backend",
            content="What: Allow SQLite as a local backend.\nWhy: Local setup should not require a database server.",
            memory_type="decision",
            scope="project",
        )
        results = await app.remember("sqlite backend", scope="project", include_content=True)
    finally:
        await app.storage.close()

    assert UUID(boot["session_id"])
    assert saved["status"] in {"created", "create"}
    assert any(result["uri"] == "project://olinkb/decisions/sqlite-backend" for result in results)


@pytest.mark.asyncio
async def test_sqlite_full_flow_boot_save_search_end(tmp_path) -> None:
    settings = Settings(
        pg_url=None,
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=0,
        cache_max_entries=0,
        storage_backend="sqlite",
        sqlite_path=tmp_path / "flow.db",
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)

    try:
        # Boot empty DB
        boot = await app.boot_session(author="rzjulio", project="olinkb")
        session_id = boot["session_id"]
        assert UUID(session_id)
        assert boot["loaded_count"] == 0
        assert boot["memories"] == []

        # Save several memory types
        uris = []
        for i in range(5):
            result = await app.save_memory(
                uri=f"project://olinkb/decisions/flow-{i}",
                title=f"Flow decision {i}",
                content=f"What: Decision {i}.\nWhy: Flow testing.\nContext: SQLite integration.",
                memory_type="decision",
                scope="project",
                tags="flow,test",
                metadata={"source": "test", "index": i},
                session_id=session_id,
            )
            assert result["status"] == "create"
            uris.append(result["uri"])

        # Save a personal memory
        personal = await app.save_memory(
            uri="personal://rzjulio/prefs/editor",
            title="Editor preference",
            content="What: Prefer VS Code.\nWhy: Best extensions.",
            memory_type="preference",
            scope="personal",
        )
        assert personal["status"] == "create"

        # Boot again should load all project + personal memories
        boot2 = await app.boot_session(author="rzjulio", project="olinkb")
        assert boot2["loaded_count"] == 6
        for mem in boot2["memories"]:
            assert isinstance(mem.get("tags"), list)
            assert isinstance(mem.get("metadata"), dict)

        # Search project scope
        results = await app.remember("flow decision", scope="project", include_content=True)
        assert len(results) >= 1
        found_uris = {r["uri"] for r in results}
        assert any(u in found_uris for u in uris)
        for r in results:
            assert "content" in r
            assert isinstance(r.get("relevance"), float)
            assert r["relevance"] > 0

        # Search personal scope
        personal_results = await app.remember("editor preference", scope="personal", include_content=True)
        assert any(r["uri"] == "personal://rzjulio/prefs/editor" for r in personal_results)

        # Search all scope
        all_results = await app.remember("decision", scope="all", include_content=False)
        assert len(all_results) >= 1
        for r in all_results:
            assert "content" not in r or r.get("result_type") == "session_summary"

        # End session
        end_result = await app.end_session(
            session_id=session_id,
            summary="Tested full SQLite flow with multiple scopes.",
        )
        assert end_result["session_id"] == session_id
        assert end_result["summary"] == "Tested full SQLite flow with multiple scopes."

        # Verify session was ended in storage
        stored = await app.storage.get_session(session_id)
        assert stored is not None
        assert stored["ended_at"] is not None
    finally:
        await app.storage.close()


@pytest.mark.asyncio
async def test_sqlite_search_with_volume(tmp_path) -> None:
    settings = Settings(
        pg_url=None,
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=0,
        cache_max_entries=0,
        storage_backend="sqlite",
        sqlite_path=tmp_path / "volume.db",
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)

    try:
        boot = await app.boot_session(author="rzjulio", project="olinkb")
        session_id = boot["session_id"]

        # Save 50 memories
        for i in range(50):
            await app.save_memory(
                uri=f"project://olinkb/facts/vol-{i}",
                title=f"Volume fact {i}",
                content=f"What: Fact {i} about performance.\nWhy: Volume test.\nContext: Benchmarking SQLite.",
                memory_type="fact",
                scope="project",
                tags="volume,benchmark",
                metadata={"iteration": i},
                session_id=session_id,
            )

        # Boot should cap at 40
        boot2 = await app.boot_session(author="rzjulio", project="olinkb")
        assert boot2["loaded_count"] <= 40

        # Some should have content stripped (hybrid payload)
        has_content = sum(1 for m in boot2["memories"] if "content" in m)
        no_content = sum(1 for m in boot2["memories"] if "content" not in m)
        assert has_content > 0
        assert no_content > 0

        # Search should find relevant results
        results = await app.remember("performance benchmark", scope="project", limit=10, include_content=True)
        assert len(results) > 0
        assert all(r.get("relevance", 0) > 0 for r in results)
    finally:
        await app.storage.close()
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
async def test_boot_session_returns_uuid_session_id() -> None:
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

    result = await app.boot_session(author="rzjulio", project="olinkb")

    assert UUID(result["session_id"])


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
async def test_save_memory_infers_project_uri_and_scope_when_omitted() -> None:
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
        title="PPCC switch sizing",
        content="What: Reduced the PPCC dx-switch width in the GL code dialog.",
        memory_type="bugfix",
        project="facturacion-electronica",
    )

    assert result["status"] == "created"
    assert app.storage.save_memory_calls[0]["scope"] == "project"
    assert app.storage.save_memory_calls[0]["uri"] == "project://facturacion-electronica/bugfixes/ppcc-switch-sizing"


@pytest.mark.asyncio
async def test_save_memory_treats_file_uri_as_source_reference_and_infers_canonical_uri() -> None:
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

    await app.save_memory(
        uri="file:///c:/Julio%20C.%20Rodriguez/repositorios/facturacion-electronica/Aplicaciones/CFDIWeb/src/app/pages/glcodes/ppcc-glcode-dialog/ppcc-glcode-dialog.component.scss",
        title="PPCC switch sizing",
        content="What: Reduced the PPCC dx-switch width in the GL code dialog.",
        memory_type="bugfix",
        project="facturacion-electronica",
    )

    assert app.storage.save_memory_calls[0]["uri"] == "project://facturacion-electronica/bugfixes/ppcc-switch-sizing"
    assert app.storage.save_memory_calls[0]["metadata"]["source_uri"] == "file:///c:/Julio%20C.%20Rodriguez/repositorios/facturacion-electronica/Aplicaciones/CFDIWeb/src/app/pages/glcodes/ppcc-glcode-dialog/ppcc-glcode-dialog.component.scss"


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
async def test_save_memory_blocks_business_documentation_for_non_admin() -> None:
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
    app.storage = storage

    with pytest.raises(PermissionError, match="Only admins can save business documentation"):
        await app.save_memory(
            uri="org://shared/notes/quarterly-roadmap",
            title="Quarterly roadmap",
            content="# Q2 roadmap",
            memory_type="business_documentation",
            scope="org",
        )


@pytest.mark.asyncio
async def test_save_memory_enriches_technical_documentation_tags() -> None:
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
    app.storage = storage

    await app.save_memory(
        uri="org://shared/notes/platform-handbook",
        title="Platform handbook",
        content="# Platform handbook",
        memory_type="documentation",
        scope="org",
        metadata={"documentation_scope": "global", "applicable_projects": []},
    )

    tags = storage.save_memory_calls[0]["tags"]
    assert "documentation" in tags
    assert "technical-documentation" in tags
    assert "documentacion" in tags
    assert "documentacion-tecnica" in tags
    assert "global" in tags
    assert "documentacion-global" in tags


@pytest.mark.asyncio
async def test_save_memory_enriches_business_documentation_tags() -> None:
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
    storage.member_role = "admin"
    app.storage = storage

    await app.save_memory(
        uri="org://shared/notes/quarterly-roadmap",
        title="Quarterly roadmap",
        content="# Q2 roadmap",
        memory_type="business_documentation",
        scope="org",
        metadata={"documentation_scope": "repo", "applicable_projects": ["olinkb"]},
    )

    tags = storage.save_memory_calls[0]["tags"]
    assert "business-documentation" in tags
    assert "documentacion-negocio" in tags
    assert "repo" in tags
    assert "documentacion-repo" in tags
    assert "olinkb" in tags


@pytest.mark.asyncio
async def test_capture_memory_auto_saves_high_confidence_bugfix() -> None:
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

    result = await app.capture_memory(
        content=(
            "What: Fix invalid JSON handling in the CLI transport\n"
            "Why: Tool input errors were hard to understand\n"
            "Where: src/olinkb/tool_cli.py\n"
            "Evidence: Invalid payloads raised confusing runtime errors\n"
            "Learned: CLI-facing failures need explicit JSON validation"
        ),
        project="olinkb",
        scope_hint="project",
        source_surface="cli",
        files=["src/olinkb/tool_cli.py", "tests/test_tool_cli.py"],
        commands=["pytest -q tests/test_tool_cli.py"],
    )

    assert result["action"] == "save"
    assert result["saved"] is True
    assert result["suggested_memory_type"] == "bugfix"
    assert storage.save_memory_calls[0]["memory_type"] == "bugfix"
    assert storage.save_memory_calls[0]["uri"].startswith("project://olinkb/bugfixes/")


@pytest.mark.asyncio
async def test_capture_memory_suggests_org_documentation_when_permissions_block_save() -> None:
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
    storage.member_role = "developer"
    app.storage = storage

    result = await app.capture_memory(
        content=(
            "# OlinKB Architecture Guide\n\n"
            "This document explains the shared CLI-first memory flow, setup steps, and architecture boundaries.\n\n"
            "Decision: Keep CLI as the primary operator surface while preserving MCP compatibility."
        ),
        title="OlinKB architecture guide",
        scope_hint="org",
        source_surface="cli",
        files=["README.md", "src/olinkb/cli.py"],
        commands=["olinkb tool analyze_memory --json '{\"content\":\"# OlinKB Architecture Guide\"}'"],
    )

    assert result["action"] == "suggest"
    assert result["saved"] is False
    assert result["suggested_memory_type"] == "documentation"
    assert result["documentation_candidate"] is True
    assert storage.save_memory_calls == []


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
    storage = FakeStorage()
    app1 = OlinKBApp(settings=settings)
    app1.storage = storage
    boot = await app1.boot_session(author="rzjulio", project="olinkb")

    app2 = OlinKBApp(settings=settings)
    app2.storage = storage

    result = await app2.end_session(boot["session_id"].upper(), "Recovered end")

    assert result["status"] == "recovered"
    assert result["author"] == "rzjulio"
    assert result["session_id"] == boot["session_id"]
    assert storage.end_session_calls[0]["session_id"] == boot["session_id"]


@pytest.mark.asyncio
async def test_end_session_rejects_invalid_session_id_format() -> None:
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

    with pytest.raises(ValueError, match="Invalid session_id format"):
        await app.end_session("missing-session", "Nope")


@pytest.mark.asyncio
async def test_end_session_resolves_single_persisted_open_session_when_session_id_is_omitted() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="facturacion-electronica",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    storage = FakeStorage()
    app.storage = storage
    session_id = str(uuid4())
    storage.session_rows[session_id] = {
        "id": session_id,
        "author_username": "rzjulio",
        "project": "facturacion-electronica",
        "summary": None,
        "memories_read": 0,
        "memories_written": 0,
        "ended_at": None,
    }

    result = await app.end_session(None, "Closed after styling verification.")

    assert result["session_id"] == session_id
    assert result["status"] == "recovered"
    assert storage.end_session_calls[0]["session_id"] == session_id


@pytest.mark.asyncio
async def test_end_session_marks_unknown_uuid_as_stale_or_missing() -> None:
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

    with pytest.raises(ValueError, match="stale, already cleaned up, or from a different OlinKB environment"):
        await app.end_session(str(uuid4()), "Nope")


@pytest.mark.asyncio
async def test_end_session_reports_when_current_process_tracks_different_active_session() -> None:
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
    boot = await app.boot_session(author="rzjulio", project="olinkb")

    with pytest.raises(ValueError, match="different active session_id is currently open"):
        await app.end_session(str(uuid4()), "Nope")


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
    boot = await app.boot_session(author="rzjulio", project="olinkb")

    summary = (
        "Goal: Improve memory usefulness\n"
        "Discoveries: Session summaries are not queried by remember today\n"
        "Accomplished: Added retrieval over session summaries and promoted valuable closures into memories\n"
        "Next Steps: Surface session summaries more clearly in the viewer"
    )

    result = await app.end_session(boot["session_id"], summary)

    assert result["memories_written"] == 1
    assert storage.save_memory_calls[0]["uri"] == f"project://olinkb/sessions/{boot['session_id']}"
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
    boot = await app.boot_session(author="rzjulio", project="olinkb")

    result = await app.end_session(boot["session_id"], "Closed session after quick check.")

    assert result["memories_written"] == 0
    assert storage.save_memory_calls == []


@pytest.mark.asyncio
async def test_save_documentation_by_developer_gets_pending_status() -> None:
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
    storage.member_role = "developer"
    storage.project_role = "developer"
    app.storage = storage

    result = await app.save_memory(
        uri="project://olinkb/documentation/api-guide",
        title="API Guide",
        content="# API Guide\nHow to use the REST API.",
        memory_type="documentation",
        scope="project",
    )

    assert len(storage.save_memory_calls) == 1
    assert storage.save_memory_calls[0]["approval_status"] == "pending"
    assert "awaiting_approval" not in result


@pytest.mark.asyncio
async def test_save_documentation_by_lead_gets_pending_with_awaiting_approval() -> None:
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
    app.storage = storage

    result = await app.save_memory(
        uri="project://olinkb/documentation/api-guide",
        title="API Guide",
        content="# API Guide\nHow to use the REST API.",
        memory_type="documentation",
        scope="project",
    )

    assert storage.save_memory_calls[0]["approval_status"] == "pending"
    assert result["awaiting_approval"] is True
    assert "approval_hint" in result


@pytest.mark.asyncio
async def test_save_development_standard_by_developer_gets_pending() -> None:
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
    storage.member_role = "developer"
    storage.project_role = "developer"
    app.storage = storage

    await app.save_memory(
        uri="project://olinkb/development-standards/code-style",
        title="Code Style Guide",
        content="# Code Style\nUse Black formatter.",
        memory_type="development_standard",
        scope="project",
    )

    assert storage.save_memory_calls[0]["approval_status"] == "pending"


@pytest.mark.asyncio
async def test_save_non_managed_type_always_approved() -> None:
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
    storage.member_role = "developer"
    storage.project_role = "developer"
    app.storage = storage

    await app.save_memory(
        uri="project://olinkb/bugfixes/login-crash",
        title="Fix login crash",
        content="What: Fixed null pointer in login",
        memory_type="bugfix",
        scope="project",
    )

    assert storage.save_memory_calls[0]["approval_status"] == "approved"


@pytest.mark.asyncio
async def test_save_documentation_by_admin_gets_pending_with_awaiting_approval() -> None:
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
    storage.member_role = "admin"
    storage.project_role = "admin"
    app.storage = storage

    result = await app.save_memory(
        uri="project://olinkb/documentation/api-guide",
        title="API Guide",
        content="# API Guide\nHow to use the REST API.",
        memory_type="documentation",
        scope="project",
    )

    assert storage.save_memory_calls[0]["approval_status"] == "pending"
    assert result["awaiting_approval"] is True
    assert "review_memory_proposal" in result["approval_hint"]


@pytest.mark.asyncio
async def test_save_non_managed_type_by_lead_has_no_awaiting_approval() -> None:
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
    app.storage = storage

    result = await app.save_memory(
        uri="project://olinkb/decisions/use-fts5",
        title="Use FTS5 for search",
        content="What: Use FTS5 for full-text search",
        memory_type="decision",
        scope="project",
    )

    assert storage.save_memory_calls[0]["approval_status"] == "approved"
    assert "awaiting_approval" not in result