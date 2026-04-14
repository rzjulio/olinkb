# Managed Memory Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add viewer-managed Markdown memories with three managed types, multi-project/global applicability, approval traceability, and lean boot-session behavior that only auto-loads applicable `development_standard` memories.

**Architecture:** Reuse `memories` as the canonical content store, add a `managed_memory_targets` table for applicability, normalize approved MCP proposals into `development_standard`, and extend the live viewer plus MCP surface to create, list, update, and archive managed memories. `boot_session` remains lean by filtering to approved `development_standard` rows that apply to the active context.

**Tech Stack:** Python 3.11, asyncpg, MCP Python SDK, ThreadingHTTPServer, PostgreSQL migrations, pytest

---

## File Structure

### Create

- `src/olinkb/storage/migrations/005_add_managed_memory_support.sql` — schema changes for new managed memory types and applicability targets
- `tests/test_viewer_server.py` — endpoint-level tests for managed memory upload/list/update/delete behavior if a dedicated file is preferred over extending an existing viewer server test file

### Modify

- `src/olinkb/domain.py` — extend allowed memory types and add any managed-memory helper validation
- `src/olinkb/storage/postgres.py` — manage target rows, boot-session filtering, search filtering, and proposal approval normalization support
- `src/olinkb/app.py` — enforce role-aware managed-memory creation, listing, update, archive, and proposal normalization
- `src/olinkb/server.py` — expose MCP tools for managed memory creation/listing/archive
- `src/olinkb/viewer_server.py` — add HTTP endpoints for managed memory admin operations
- `src/olinkb/viewer.py` — add payload support and UI rendering for managed memories and their applicability metadata
- `tests/test_app.py` — app-level TDD for permissions, boot loading, search behavior, and proposal normalization
- `tests/test_postgres.py` — storage-level tests for targets, boot applicability, and search filtering
- `tests/test_server.py` — MCP tool wiring tests
- `tests/test_viewer.py` — viewer payload/rendering tests for managed memories
- `README.md` — add user-facing note on managed memories in viewer mode
- `docs/DEVELOPER-GUIDE.md` — document upload/governance behavior and new MCP/viewer surfaces if the implementation adds user-visible commands or flows

---

### Task 1: Add Schema Support For Managed Memories

**Files:**
- Create: `src/olinkb/storage/migrations/005_add_managed_memory_support.sql`
- Modify: `src/olinkb/domain.py`
- Test: `tests/test_postgres.py`

- [ ] **Step 1: Write the failing schema/type tests**

```python
def test_validate_memory_type_accepts_managed_memory_types() -> None:
    from olinkb.domain import validate_memory_type

    assert validate_memory_type("documentation") == "documentation"
    assert validate_memory_type("business_documentation") == "business_documentation"
    assert validate_memory_type("development_standard") == "development_standard"
```

```python
@pytest.mark.asyncio
async def test_managed_memory_targets_table_is_used_for_applicability() -> None:
    storage = PostgresStorage("postgresql://unused")
    # This test will start as a red test by asserting on a method that does not exist yet.
    assert hasattr(storage, "replace_managed_memory_targets")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_postgres.py -k "managed_memory_targets_table_is_used_for_applicability or validate_memory_type_accepts_managed_memory_types" -v`

Expected: FAIL with missing managed memory types and missing storage method.

- [ ] **Step 3: Add the migration and domain constants**

```sql
ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_memory_type_check;

ALTER TABLE memories
ADD CONSTRAINT memories_memory_type_check CHECK (
    memory_type IN (
        'fact', 'preference', 'event', 'constraint', 'procedure',
        'failure_pattern', 'tool_affordance', 'convention', 'decision',
        'discovery', 'bugfix',
        'documentation', 'business_documentation', 'development_standard'
    )
);

CREATE TABLE IF NOT EXISTS managed_memory_targets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('global', 'project')),
    target_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (memory_id, target_type, target_value)
);

CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_memory_id ON managed_memory_targets(memory_id);
CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_target ON managed_memory_targets(target_type, target_value);
```

```python
ALLOWED_MEMORY_TYPES = {
    "fact",
    "preference",
    "event",
    "constraint",
    "procedure",
    "failure_pattern",
    "tool_affordance",
    "convention",
    "decision",
    "discovery",
    "bugfix",
    "documentation",
    "business_documentation",
    "development_standard",
}
```

- [ ] **Step 4: Add a small helper for managed-memory type checks**

```python
MANAGED_MEMORY_TYPES = {
    "documentation",
    "business_documentation",
    "development_standard",
}


def is_managed_memory_type(memory_type: str) -> bool:
    return memory_type in MANAGED_MEMORY_TYPES
```

- [ ] **Step 5: Run the focused tests again**

Run: `pytest tests/test_postgres.py -k "managed_memory_targets_table_is_used_for_applicability or validate_memory_type_accepts_managed_memory_types" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/olinkb/storage/migrations/005_add_managed_memory_support.sql src/olinkb/domain.py tests/test_postgres.py
git commit -m "feat: add managed memory schema support"
```

### Task 2: Implement Storage Support For Targets, Search, And Boot Filtering

**Files:**
- Modify: `src/olinkb/storage/postgres.py`
- Test: `tests/test_postgres.py`

- [ ] **Step 1: Write the failing storage tests**

```python
@pytest.mark.asyncio
async def test_replace_managed_memory_targets_rewrites_global_and_project_targets() -> None:
    storage = PostgresStorage("postgresql://unused")
    connection = SaveConnection()
    storage._pool = SavePool(connection)

    await storage.replace_managed_memory_targets(
        memory_id=uuid4(),
        targets=[
            {"target_type": "global", "target_value": "*"},
            {"target_type": "project", "target_value": "olinkb"},
        ],
    )

    assert any("DELETE FROM managed_memory_targets" in query for query, _ in connection.execute_calls)
    assert any("INSERT INTO managed_memory_targets" in query for query, _ in connection.execute_calls)
```

```python
@pytest.mark.asyncio
async def test_load_boot_memories_only_keeps_applicable_development_standards() -> None:
    rows = [
        {
            "uri": "project://olinkb/standards/review-flow",
            "title": "Review flow",
            "content": "# Review flow",
            "memory_type": "development_standard",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "ana",
            "metadata": {"managed": True},
            "updated_at": datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        },
        {
            "uri": "project://olinkb/docs/api-guidelines",
            "title": "API Guidelines",
            "content": "# API Guidelines",
            "memory_type": "documentation",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "ana",
            "metadata": {"managed": True},
            "updated_at": datetime(2026, 4, 12, 11, 0, tzinfo=timezone.utc),
        },
    ]
    storage = PostgresStorage("postgresql://unused")
    storage._pool = BootQueryPool(rows)

    result = await storage.load_boot_memories(username="rzjulio", project="olinkb")

    assert [item["memory_type"] for item in result] == ["development_standard"]
```

```python
@pytest.mark.asyncio
async def test_search_memories_can_filter_by_managed_type() -> None:
    storage = PostgresStorage("postgresql://unused")
    storage._pool = TenantQueryPool()

    await storage.search_memories(
        query="review flow",
        scope="project",
        limit=5,
        username="rzjulio",
        team="mi-equipo",
        project="olinkb",
        memory_types=["development_standard"],
    )

    query, args = storage._pool.fetch_calls[0]
    assert "m.memory_type = ANY" in query
    assert args[-1] == ["development_standard"]
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `pytest tests/test_postgres.py -k "replace_managed_memory_targets or load_boot_memories_only_keeps_applicable_development_standards or search_memories_can_filter_by_managed_type" -v`

Expected: FAIL with missing methods or unsupported search signature.

- [ ] **Step 3: Add target helper methods and boot/search support**

```python
BOOT_MEMORY_TYPE_SCORE = {
    "development_standard": 18,
    "convention": 18,
    "procedure": 16,
    "decision": 14,
    "constraint": 12,
    "bugfix": 11,
    "failure_pattern": 10,
    "tool_affordance": 9,
    "discovery": 7,
    "fact": 5,
    "event": 3,
    "preference": 1,
}


async def replace_managed_memory_targets(self, *, memory_id: UUID, targets: list[dict[str, str]]) -> None:
    await self.connect()
    assert self._pool is not None
    async with self._pool.acquire() as conn:
        await conn.execute("DELETE FROM managed_memory_targets WHERE memory_id = $1", memory_id)
        for target in targets:
            await conn.execute(
                """
                INSERT INTO managed_memory_targets (memory_id, target_type, target_value)
                VALUES ($1, $2, $3)
                """,
                memory_id,
                target["target_type"],
                target["target_value"],
            )
```

```python
async def fetch_managed_memory_targets(self, memory_ids: list[UUID]) -> dict[str, list[dict[str, str]]]:
    await self.connect()
    assert self._pool is not None
    if not memory_ids:
        return {}
    rows = await self._pool.fetch(
        """
        SELECT memory_id::text AS memory_id, target_type, target_value
        FROM managed_memory_targets
        WHERE memory_id = ANY($1::uuid[])
        ORDER BY target_type ASC, target_value ASC
        """,
        memory_ids,
    )
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["memory_id"], []).append(
            {"target_type": row["target_type"], "target_value": row["target_value"]}
        )
    return grouped
```

```python
async def search_memories(
    self,
    query: str,
    scope: str,
    limit: int,
    include_content: bool = False,
    username: str | None = None,
    team: str | None = None,
    project: str | None = None,
    memory_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows = await self._pool.fetch(
        """
        SELECT m.id, m.uri, m.title, m.content, m.memory_type, m.scope, m.namespace,
               m.author_username, m.metadata, m.updated_at,
               GREATEST(similarity(m.title, $1), similarity(m.content, $1), similarity(m.uri, $1)) AS relevance
        FROM memories AS m
        LEFT JOIN team_members AS tm ON tm.id = m.author_id
        WHERE m.deleted_at IS NULL
          AND m.scope = ANY($2::text[])
          AND ($7::text[] IS NULL OR m.memory_type = ANY($7::text[]))
          AND (
                m.scope = 'system'
             OR m.scope = 'org'
             OR (m.scope = 'personal' AND m.author_username = $4)
             OR (m.scope = 'project' AND $5::text IS NOT NULL AND m.namespace = $5)
             OR (m.scope = 'team' AND $6::text IS NOT NULL AND tm.team = $6)
          )
        ORDER BY relevance DESC, m.retrieval_count DESC, m.updated_at DESC
        LIMIT $3
        """,
        query,
        scope_filters,
        limit,
        username,
        project_namespace,
        team,
        memory_types,
    )
    return [self._serialize_memory(row, include_content=include_content) for row in rows]
```

```python
async def load_boot_memories(
    self,
    username: str,
    project: str | None,
    limit: int = 40,
    full_content_limit: int = 5,
) -> list[dict[str, Any]]:
    project_prefix = f"project://{project}/%" if project else "__no_project_match__"
    personal_prefix = f"personal://{username}/%"
    rows = await self._pool.fetch(
        """
        SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
               metadata, approval_status, updated_at
        FROM memories
        WHERE deleted_at IS NULL
          AND approval_status = 'approved'
          AND memory_type = 'development_standard'
          AND (
                uri LIKE 'system://%'
             OR uri LIKE $1
             OR uri LIKE $2
          )
        ORDER BY updated_at DESC
        LIMIT $3
        """,
        project_prefix,
        personal_prefix,
        limit,
    )
    targets_by_memory_id = await self.fetch_managed_memory_targets([row["id"] for row in rows])
    applicable_rows = [
        row for row in rows
        if self._managed_memory_applies_to_project(targets_by_memory_id.get(str(row["id"]), []), project)
    ]
    serialized_rows = [self._serialize_memory({**dict(row), "targets": targets_by_memory_id.get(str(row["id"]), [])}, include_content=True) for row in applicable_rows]
    full_content_indexes = self._select_boot_full_content_indexes(serialized_rows, full_content_limit)
    return [
        self._finalize_memory_payload(memory.copy(), include_content=index in full_content_indexes)
        for index, memory in enumerate(serialized_rows)
    ]
```

- [ ] **Step 4: Normalize payloads with target metadata for downstream layers**

```python
def _serialize_memory(self, row: asyncpg.Record | dict[str, Any], include_content: bool = False) -> dict[str, Any]:
    payload = self._serialize_record(row)
    payload["metadata"] = self._normalize_metadata(payload.get("content"), payload.get("metadata"))
    payload["tags"] = parse_tags(payload.get("tags") or [])
    payload["managed"] = bool(payload.get("metadata", {}).get("managed"))
    payload["origin_channel"] = payload.get("metadata", {}).get("origin_channel")
    payload["targets"] = payload.get("targets", [])
    return payload
```

- [ ] **Step 5: Run the focused storage tests again**

Run: `pytest tests/test_postgres.py -k "replace_managed_memory_targets or load_boot_memories_only_keeps_applicable_development_standards or search_memories_can_filter_by_managed_type" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/olinkb/storage/postgres.py tests/test_postgres.py
git commit -m "feat: add managed memory storage behavior"
```

### Task 3: Add App-Level Managed Memory Workflows And Proposal Normalization

**Files:**
- Modify: `src/olinkb/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing app tests**

```python
@pytest.mark.asyncio
async def test_create_managed_memory_requires_admin_or_lead_for_documentation() -> None:
    app = OlinKBApp(settings=Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
    ))
    storage = FakeStorage()
    storage.member_role = "developer"
    storage.project_role = "developer"
    app.storage = storage

    with pytest.raises(PermissionError, match="Only admins or leads can create managed memories"):
        await app.create_managed_memory(
            title="API Guide",
            content="# API Guide",
            memory_type="documentation",
            targets=[{"target_type": "project", "target_value": "olinkb"}],
            author="rzjulio",
        )
```

```python
@pytest.mark.asyncio
async def test_create_managed_memory_requires_admin_for_business_documentation() -> None:
    app = OlinKBApp(settings=Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
    ))
    storage = FakeStorage()
    storage.member_role = "lead"
    app.storage = storage

    with pytest.raises(PermissionError, match="Only admins can manage business_documentation"):
        await app.create_managed_memory(
            title="Business Workflow",
            content="# Business Workflow",
            memory_type="business_documentation",
            targets=[{"target_type": "global", "target_value": "*"}],
            author="rzjulio",
        )
```

```python
@pytest.mark.asyncio
async def test_normalize_target_memory_type_accepts_development_standard() -> None:
    assert OlinKBApp._normalize_target_memory_type("development_standard") == "development_standard"
    assert OlinKBApp._normalize_target_memory_type("standard") == "development_standard"
```

```python
@pytest.mark.asyncio
async def test_review_memory_proposal_normalizes_approved_standard_markdown() -> None:
    app = OlinKBApp(settings=Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
    ))
    storage = FakeStorage()
    storage.member_role = "lead"
    storage.project_role = "lead"
    app.storage = storage

    await app.review_memory_proposal(
        uri="project://olinkb/decisions/review-flow",
        action="approve",
        note="Approved as team standard.",
        author="rzjulio",
    )

    assert storage.review_calls[0]["normalize_to_markdown"] is True
```

- [ ] **Step 2: Run the app tests to verify they fail**

Run: `pytest tests/test_app.py -k "create_managed_memory or normalize_target_memory_type_accepts_development_standard or review_memory_proposal_normalizes_approved_standard_markdown" -v`

Expected: FAIL with missing methods, old target-type normalization, or missing normalization signal.

- [ ] **Step 3: Add managed-memory orchestration methods and role checks**

```python
async def create_managed_memory(
    self,
    *,
    title: str,
    content: str,
    memory_type: str,
    targets: list[dict[str, str]],
    summary: str | None = None,
    source_filename: str | None = None,
    session_id: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    validate_memory_type(memory_type)
    username = author or self.settings.user
    member = await self.storage.ensure_member(username=username, team=self.settings.team)
    self._authorize_managed_memory_create(memory_type=memory_type, member=member)
    metadata = {
        "managed": True,
        "source_format": "markdown",
        "origin_channel": "viewer_upload",
        "audience": "business" if memory_type == "business_documentation" else "engineering",
        "source_filename": source_filename,
        "summary": summary,
        "final_memory_type": memory_type,
    }
    primary_project = next((target["target_value"] for target in targets if target["target_type"] == "project"), None)
    scope = "system" if any(target["target_type"] == "global" for target in targets) else "project"
    uri = (
        f"system://managed/{memory_type}/{title.lower().replace(' ', '-')}"
        if scope == "system"
        else f"project://{primary_project}/managed/{memory_type}/{title.lower().replace(' ', '-')}"
    )
    result = await self.storage.save_memory(
        uri=uri,
        title=title,
        content=content,
        memory_type=memory_type,
        scope=scope,
        tags=[],
        metadata=metadata,
        author_id=member["id"],
        author_username=username,
    )
    await self.storage.replace_managed_memory_targets(memory_id=result["id"], targets=targets)
    return result
```

```python
@staticmethod
def _authorize_managed_memory_create(*, memory_type: str, member: dict[str, Any]) -> None:
    role = member.get("role", "developer")
    if memory_type == "business_documentation" and role != "admin":
        raise PermissionError("Only admins can manage business_documentation")
    if role not in {"admin", "lead"}:
        raise PermissionError("Only admins or leads can create managed memories")
```

- [ ] **Step 4: Normalize proposal approval to development standards**

```python
@staticmethod
def _normalize_target_memory_type(target_memory_type: str) -> str:
    normalized = target_memory_type.strip().lower()
    if normalized in {"standard", "development_standard"}:
        normalized = "development_standard"
    validate_memory_type(normalized)
    if normalized != "development_standard":
        raise ValueError("Only promotion to development_standard is supported")
    return normalized
```

```python
@staticmethod
def _normalize_development_standard_markdown(title: str, content: str, targets: list[dict[str, str]]) -> str:
    applies_to = ["Global" if target["target_type"] == "global" else target["target_value"] for target in targets]
    return (
        f"# {title}\n\n"
        "## Purpose\n"
        "Standardized guidance approved for recurring project work.\n\n"
        "## Rule\n"
        f"{content.strip()}\n\n"
        "## Applies To\n"
        + "\n".join(f"- {item}" for item in applies_to)
        + "\n"
    )
```

- [ ] **Step 5: Run the focused app tests again**

Run: `pytest tests/test_app.py -k "create_managed_memory or normalize_target_memory_type_accepts_development_standard or review_memory_proposal_normalizes_approved_standard_markdown" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/olinkb/app.py tests/test_app.py
git commit -m "feat: add managed memory app workflows"
```

### Task 4: Expose Managed Memory MCP Tools And Viewer HTTP Endpoints

**Files:**
- Modify: `src/olinkb/server.py`
- Modify: `src/olinkb/viewer_server.py`
- Test: `tests/test_server.py`
- Test: `tests/test_viewer_server.py`

- [ ] **Step 1: Write the failing server tests**

```python
@pytest.mark.asyncio
async def test_server_create_managed_memory_passes_targets(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    await server.create_managed_memory(
        title="API Guide",
        content="# API Guide",
        memory_type="documentation",
        targets=[{"target_type": "project", "target_value": "olinkb"}],
    )

    assert app.calls[0]["targets"] == [{"target_type": "project", "target_value": "olinkb"}]
```

```python
def test_viewer_server_rejects_non_markdown_upload(tmp_path) -> None:
    with pytest.raises(ValueError, match="Only \.md uploads are supported"):
        viewer_server._validate_managed_memory_upload(
            {
                "title": "API Guide",
                "content": "# API Guide",
                "memory_type": "documentation",
                "source_filename": "api-guide.txt",
                "targets": [{"target_type": "project", "target_value": "olinkb"}],
            }
        )
```

- [ ] **Step 2: Run the tool and endpoint tests to verify they fail**

Run: `pytest tests/test_server.py tests/test_viewer_server.py -k "managed_memory or markdown_upload" -v`

Expected: FAIL with missing MCP tools or missing viewer-server endpoints.

- [ ] **Step 3: Add MCP tools for managed memory operations**

```python
@mcp.tool
async def create_managed_memory(
    title: str,
    content: str,
    memory_type: str,
    targets: list[dict],
    summary: str | None = None,
    source_filename: str | None = None,
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    return await get_app().create_managed_memory(
        title=title,
        content=content,
        memory_type=memory_type,
        targets=targets,
        summary=summary,
        source_filename=source_filename,
        session_id=session_id,
        author=author,
    )
```

```python
@mcp.tool
async def list_managed_memories(
    memory_types: list[str] | None = None,
    project: str | None = None,
    include_archived: bool = False,
    author: str | None = None,
) -> dict:
    return await get_app().list_managed_memories(
        memory_types=memory_types,
        project=project,
        include_archived=include_archived,
        author=author,
    )
```

- [ ] **Step 4: Add live viewer endpoints**

```python
def do_POST(self) -> None:  # noqa: N802
    parsed = urlparse(self.path)
    if parsed.path == "/api/managed-memories":
        payload = self._read_json_body()
        result = asyncio.run(
            _create_managed_memory_payload(
                self.server.settings.pg_url,
                payload=payload,
                username=self.server.settings.user,
                team=self.server.settings.team,
                project=self.server.settings.default_project,
                pool_max_size=self.server.settings.pg_pool_max_size,
            )
        )
        self._send_json(result, status=HTTPStatus.CREATED)
        return
    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
```

```python
def do_PUT(self) -> None:  # noqa: N802
    parsed = urlparse(self.path)
    if parsed.path.startswith("/api/managed-memories/"):
        memory_id = parsed.path.rsplit("/", 1)[-1]
        payload = self._read_json_body()
        result = asyncio.run(
            _update_managed_memory_payload(
                self.server.settings.pg_url,
                memory_id=memory_id,
                payload=payload,
                username=self.server.settings.user,
                team=self.server.settings.team,
                project=self.server.settings.default_project,
                pool_max_size=self.server.settings.pg_pool_max_size,
            )
        )
        self._send_json(result)
        return
    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
```

```python
def do_DELETE(self) -> None:  # noqa: N802
    parsed = urlparse(self.path)
    if parsed.path.startswith("/api/managed-memories/"):
        memory_id = parsed.path.rsplit("/", 1)[-1]
        payload = self._read_json_body()
        result = asyncio.run(
            _archive_managed_memory_payload(
                self.server.settings.pg_url,
                memory_id=memory_id,
                reason=payload.get("reason", "Archived from viewer"),
                username=self.server.settings.user,
                team=self.server.settings.team,
                project=self.server.settings.default_project,
                pool_max_size=self.server.settings.pg_pool_max_size,
            )
        )
        self._send_json(result)
        return
    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
```

`GET /api/managed-memories` should list managed rows with filters for `memory_type`, `project`, and `include_archived`.

- [ ] **Step 5: Run the focused server tests again**

Run: `pytest tests/test_server.py tests/test_viewer_server.py -k "managed_memory or markdown_upload" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/olinkb/server.py src/olinkb/viewer_server.py tests/test_server.py tests/test_viewer_server.py
git commit -m "feat: expose managed memory APIs"
```

### Task 5: Add Managed Memory UI To The Live Viewer

**Files:**
- Modify: `src/olinkb/viewer.py`
- Test: `tests/test_viewer.py`

- [ ] **Step 1: Write the failing viewer tests**

```python
def test_build_viewer_payload_includes_managed_memory_applicability() -> None:
    payload = build_viewer_payload(
        memories=[
            {
                "id": "m1",
                "uri": "project://olinkb/standards/review-flow",
                "title": "Review flow",
                "content": "# Review flow",
                "memory_type": "development_standard",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "ana",
                "metadata": {"managed": True, "origin_channel": "viewer_upload"},
                "targets": [{"target_type": "project", "target_value": "olinkb"}],
                "updated_at": "2026-04-12T12:00:00+00:00",
                "deleted_at": None,
            }
        ],
        sessions=[],
        audit_log=[],
        team_members=[],
    )

    assert payload["managedMemories"][0]["appliesTo"] == ["olinkb"]
    assert payload["managedMemories"][0]["approvedBy"] is None
```

```python
def test_render_viewer_html_includes_managed_memory_panel() -> None:
    html = render_viewer_html(build_empty_viewer_payload())
    assert "Managed Memories" in html
    assert "managed-memory-panel" in html
```

- [ ] **Step 2: Run the viewer tests to verify they fail**

Run: `pytest tests/test_viewer.py -k "managed_memory" -v`

Expected: FAIL with missing managed-memory payload or UI panel.

- [ ] **Step 3: Extend the viewer payload**

```python
def build_empty_viewer_payload() -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "memoryCount": 0,
            "activeMemoryCount": 0,
            "deletedMemoryCount": 0,
            "sessionCount": 0,
            "auditCount": 0,
            "authorCount": 0,
            "edgeCount": 0,
        },
        "filters": {
            "scopes": [],
            "authors": [],
            "tags": [],
            "memoryTypes": [],
            "teams": [],
            "projects": [],
            "established": ["active", "deleted"],
        },
        "memories": [],
        "sessions": [],
        "auditLog": [],
        "teamMembers": [],
        "graph": {"nodes": [], "edges": []},
        "highlights": [],
        "pendingApprovals": {"enabled": False, "total_count": 0, "proposals": []},
        "managedMemories": [],
    }
```

```python
def build_viewer_payload(
    *,
    memories: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    audit_log: list[dict[str, Any]],
    team_members: list[dict[str, Any]],
    pending_approvals: dict[str, Any] | None = None,
    generated_at: str | None = None,
):
    managed_memories = [memory for memory in normalized_memories if memory.get("metadata", {}).get("managed")]
    return {
        "generatedAt": generated,
        "stats": stats,
        "filters": filters,
        "memories": normalized_memories,
        "sessions": normalized_sessions,
        "auditLog": normalized_audit_log,
        "teamMembers": normalized_team_members,
        "graph": graph,
        "highlights": highlights,
        "pendingApprovals": normalized_pending_approvals,
        "managedMemories": managed_memories,
    }
```

```python
def _normalize_memory(memory: dict[str, Any], teams_by_username: dict[str, str]) -> dict[str, Any]:
    normalized = {
        "id": str(memory.get("id")),
        "uri": memory.get("uri") or "",
        "title": memory.get("title") or "Untitled",
        "content": memory.get("content") or "",
        "memory_type": memory.get("memory_type") or "event",
        "scope": memory.get("scope") or "project",
        "namespace": memory.get("namespace") or "",
        "author_username": memory.get("author_username") or "",
        "metadata": memory.get("metadata") or {},
        "tags": memory.get("tags") or [],
        "updated_at": memory.get("updated_at"),
        "deleted_at": memory.get("deleted_at"),
    }
    normalized["managed"] = bool(normalized["metadata"].get("managed"))
    normalized["originChannel"] = normalized["metadata"].get("origin_channel")
    normalized["appliesTo"] = [
        target["target_value"] if target["target_type"] == "project" else "Global"
        for target in memory.get("targets", [])
    ]
    normalized["approvedBy"] = memory.get("reviewed_by_username")
    return normalized
```

- [ ] **Step 4: Add the managed-memory admin panel to the HTML renderer**

```html
<section class="panel managed-memory-panel">
  <div class="panel-header">
    <h2>Managed Memories</h2>
    <p>Upload and govern Markdown-backed standards and documentation.</p>
  </div>
  <div id="managed-memory-list"></div>
</section>
```

Include:

- a type filter
- a project filter
- an upload button and form shell
- explicit applicability badges
- created-by and approved-by labels

- [ ] **Step 5: Run the focused viewer tests again**

Run: `pytest tests/test_viewer.py -k "managed_memory" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/olinkb/viewer.py tests/test_viewer.py
git commit -m "feat: add managed memory viewer UI"
```

### Task 6: Finalize Search, Documentation, And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/DEVELOPER-GUIDE.md`
- Modify: `tests/test_app.py`
- Modify: `tests/test_postgres.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_viewer.py`
- Modify: `tests/test_viewer_server.py`

- [ ] **Step 1: Add the final cross-cutting failing tests**

```python
@pytest.mark.asyncio
async def test_remember_merges_documentation_and_development_standard_results() -> None:
    app = OlinKBApp(settings=Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
    ))
    storage = FakeStorage()
    storage.search_memory_results = [
        {
            "id": "m1",
            "uri": "project://olinkb/docs/api-guide",
            "title": "API Guide",
            "memory_type": "documentation",
            "relevance": 0.95,
        },
        {
            "id": "m2",
            "uri": "project://olinkb/standards/review-flow",
            "title": "Review Flow",
            "memory_type": "development_standard",
            "relevance": 0.92,
        },
    ]
    app.storage = storage

    result = await app.remember(query="review api", scope="project")

    assert [item["memory_type"] for item in result] == ["documentation", "development_standard"]
```

```python
def test_readme_mentions_managed_memory_viewer_flow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Managed Memories" in readme
```

- [ ] **Step 2: Run the final red tests**

Run: `pytest tests/test_app.py tests/test_postgres.py tests/test_server.py tests/test_viewer.py tests/test_viewer_server.py -k "managed_memory or development_standard or business_documentation or remember_merges" -v`

Expected: FAIL until the final glue logic and docs are in place.

- [ ] **Step 3: Update docs and fill any missing behavior**

```md
## Managed Memories

The live viewer can now upload Markdown-backed managed memories.

- `Documentation`: searchable engineering documentation
- `Business Documentation`: searchable business documentation, admin-only
- `Development Standard`: searchable and boot-loadable standards
```

Ensure `remember()` documentation reflects optional managed-type filtering and that `boot_session` documentation reflects the new `development_standard` rule.

- [ ] **Step 4: Run the focused managed-memory verification set**

Run: `pytest tests/test_app.py tests/test_postgres.py tests/test_server.py tests/test_viewer.py tests/test_viewer_server.py -k "managed_memory or development_standard or business_documentation or remember_merges" -v`

Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`

Expected: PASS with all tests green.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/DEVELOPER-GUIDE.md tests/test_app.py tests/test_postgres.py tests/test_server.py tests/test_viewer.py tests/test_viewer_server.py
git commit -m "docs: describe managed memory workflows"
```

## Notes For Execution

- Keep proposal normalization minimal: approved MCP proposals should become `development_standard`, not a new sidecar entity.
- Preserve proposer and approver identities distinctly in payloads and UI.
- For direct viewer uploads, set `approved_by` to the same authorized actor who published the managed memory so governance remains explicit.
- Prefer additive changes over large refactors in viewer rendering.
- Do not load `documentation` or `business_documentation` into `boot_session`.
- Keep `remember` backward-compatible by making managed-type filtering optional.
