from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from olinkb.domain import extract_namespace, parse_tags, scope_filters_for_query


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def run_migrations(self) -> list[str]:
        await self.connect()
        assert self._pool is not None
        migration_dir = Path(__file__).parent / "migrations"
        applied: list[str] = []

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            existing_rows = await conn.fetch("SELECT version FROM schema_migrations")
            existing_versions = {row["version"] for row in existing_rows}

            for migration in sorted(migration_dir.glob("*.sql")):
                if migration.name in existing_versions:
                    continue
                sql = migration.read_text(encoding="utf-8")
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        migration.name,
                    )
                applied.append(migration.name)

        return applied

    async def create_or_update_member(
        self,
        username: str,
        team: str,
        role: str = "developer",
        display_name: str | None = None,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        row = await self._pool.fetchrow(
            """
            INSERT INTO team_members (username, display_name, role, team, is_active)
            VALUES ($1, $2, $3, $4, TRUE)
            ON CONFLICT (username)
            DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, team_members.display_name),
                role = EXCLUDED.role,
                team = EXCLUDED.team,
                is_active = TRUE
            RETURNING id, username, display_name, role, team, is_active
            """,
            username,
            display_name,
            role,
            team,
        )
        return dict(row)

    async def ensure_member(self, username: str, team: str) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        row = await self._pool.fetchrow(
            "SELECT id, username, display_name, role, team, is_active FROM team_members WHERE username = $1",
            username,
        )
        if row is not None:
            return dict(row)
        return await self.create_or_update_member(username=username, team=team)

    async def start_session(self, author_id: UUID, author_username: str, project: str | None) -> str:
        await self.connect()
        assert self._pool is not None

        session_id = await self._pool.fetchval(
            """
            INSERT INTO sessions (author_id, author_username, project)
            VALUES ($1, $2, $3)
            RETURNING id::text
            """,
            author_id,
            author_username,
            project,
        )
        return str(session_id)

    async def end_session(
        self,
        session_id: str,
        summary: str,
        memories_read: int,
        memories_written: int,
    ) -> None:
        await self.connect()
        assert self._pool is not None

        await self._pool.execute(
            """
            UPDATE sessions
            SET ended_at = NOW(),
                summary = $2,
                memories_read = $3,
                memories_written = $4
            WHERE id = $1::uuid
            """,
            session_id,
            summary,
            memories_read,
            memories_written,
        )

    async def load_boot_memories(self, username: str, project: str | None, limit: int = 40) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        project_prefix = f"project://{project}/%" if project else "__no_project_match__"
        personal_prefix = f"personal://{username}/%"
        rows = await self._pool.fetch(
            """
            SELECT uri, title, content, memory_type, scope, namespace, author_username, updated_at
            FROM memories
            WHERE deleted_at IS NULL
              AND (
                    uri LIKE 'system://%'
                 OR uri LIKE 'team://conventions/%'
                 OR uri LIKE $1
                 OR uri LIKE $2
              )
            ORDER BY
                CASE
                    WHEN uri LIKE 'system://%' THEN 0
                    WHEN uri LIKE 'team://conventions/%' THEN 1
                    WHEN uri LIKE $1 THEN 2
                    WHEN uri LIKE $2 THEN 3
                    ELSE 4
                END,
                updated_at DESC
            LIMIT $3
            """,
            project_prefix,
            personal_prefix,
            limit,
        )
        return [self._serialize_memory(row) for row in rows]

    async def search_memories(
        self,
        query: str,
        scope: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        scope_filters = scope_filters_for_query(scope)
        rows = await self._pool.fetch(
            """
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username, updated_at,
                   GREATEST(
                       similarity(title, $1),
                       similarity(content, $1),
                       similarity(uri, $1)
                   ) AS relevance
            FROM memories
            WHERE deleted_at IS NULL
              AND scope = ANY($2::text[])
              AND (
                    title % $1
                 OR content % $1
                 OR uri % $1
                 OR title ILIKE '%' || $1 || '%'
                 OR content ILIKE '%' || $1 || '%'
              )
            ORDER BY relevance DESC, retrieval_count DESC, updated_at DESC
            LIMIT $3
            """,
            query,
            scope_filters,
            limit,
        )
        return [self._serialize_memory(row) for row in rows]

    async def touch_memories(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        await self.connect()
        assert self._pool is not None
        await self._pool.execute(
            """
            UPDATE memories
            SET retrieval_count = retrieval_count + 1,
                last_accessed = NOW()
            WHERE id = ANY($1::uuid[])
            """,
            [UUID(memory_id) for memory_id in memory_ids],
        )

    async def save_memory(
        self,
        *,
        uri: str,
        title: str,
        content: str,
        memory_type: str,
        scope: str,
        tags: list[str],
        author_id: UUID,
        author_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        namespace = extract_namespace(uri)

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, content, content_hash, memory_type, scope, namespace FROM memories WHERE uri = $1",
                uri,
            )
            if existing is not None and existing["content_hash"] == content_hash:
                return {
                    "status": "unchanged",
                    "id": str(existing["id"]),
                    "uri": uri,
                    "namespace": existing["namespace"],
                    "scope": existing["scope"],
                }

            async with conn.transaction():
                if existing is None:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO memories (
                            uri, title, content, memory_type, scope, namespace,
                            author_id, author_username, tags, content_hash
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::text[], $10)
                        RETURNING id, uri, namespace, scope
                        """,
                        uri,
                        title,
                        content,
                        memory_type,
                        scope,
                        namespace,
                        author_id,
                        author_username,
                        tags,
                        content_hash,
                    )
                    operation = "create"
                    old_content = None
                else:
                    row = await conn.fetchrow(
                        """
                        UPDATE memories
                        SET title = $2,
                            content = $3,
                            memory_type = $4,
                            scope = $5,
                            namespace = $6,
                            tags = $7::text[],
                            content_hash = $8,
                            deleted_at = NULL,
                            updated_at = NOW()
                        WHERE uri = $1
                        RETURNING id, uri, namespace, scope
                        """,
                        uri,
                        title,
                        content,
                        memory_type,
                        scope,
                        namespace,
                        tags,
                        content_hash,
                    )
                    operation = "update"
                    old_content = existing["content"]

                await conn.execute(
                    """
                    INSERT INTO audit_log (actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                    """,
                    author_id,
                    author_username,
                    operation,
                    row["id"],
                    uri,
                    old_content,
                    content,
                    json.dumps({"scope": scope, "memory_type": memory_type, "tags": tags}),
                )

        return {
            "status": operation,
            "id": str(row["id"]),
            "uri": row["uri"],
            "namespace": row["namespace"],
            "scope": row["scope"],
        }

    async def forget_memory(
        self,
        *,
        uri: str,
        reason: str,
        actor_id: UUID,
        actor_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, content, deleted_at FROM memories WHERE uri = $1",
                uri,
            )
            if existing is None:
                raise ValueError(f"Memory not found for URI: {uri}")
            if existing["deleted_at"] is not None:
                return {"status": "already_deleted", "id": str(existing["id"]), "uri": uri}

            async with conn.transaction():
                await conn.execute(
                    "UPDATE memories SET deleted_at = NOW(), updated_at = NOW() WHERE uri = $1",
                    uri,
                )
                await conn.execute(
                    """
                    INSERT INTO audit_log (actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
                    VALUES ($1, $2, 'forget', $3, $4, $5, NULL, $6::jsonb)
                    """,
                    actor_id,
                    actor_username,
                    existing["id"],
                    uri,
                    existing["content"],
                    json.dumps({"reason": reason}),
                )

        return {"status": "forgotten", "id": str(existing["id"]), "uri": uri}

    def _serialize_memory(self, row: asyncpg.Record) -> dict[str, Any]:
        serialized = dict(row)
        if "id" in serialized and serialized["id"] is not None:
            serialized["id"] = str(serialized["id"])
        if "updated_at" in serialized and serialized["updated_at"] is not None:
            serialized["updated_at"] = serialized["updated_at"].isoformat()
        return serialized
