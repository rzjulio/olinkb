from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
from typing import Any
from uuid import UUID

import asyncpg

from olinkb.domain import extract_namespace, parse_tags, scope_filters_for_query


STRUCTURED_METADATA_PATTERN = re.compile(
    r"^(?P<label>What|Why|Where|Learned|Context|Decision|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):\s*(?P<value>.*?)(?=^(?:What|Why|Where|Learned|Context|Decision|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


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

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        await self.connect()
        assert self._pool is not None

        row = await self._pool.fetchrow(
            """
            SELECT id::text AS id, author_username, project, summary, memories_read, memories_written, ended_at
            FROM sessions
            WHERE id = $1::uuid
            """,
            session_id,
        )
        if row is None:
            return None
        return dict(row)

    async def load_boot_memories(self, username: str, project: str | None, limit: int = 40) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        project_prefix = f"project://{project}/%" if project else "__no_project_match__"
        personal_prefix = f"personal://{username}/%"
        rows = await self._pool.fetch(
            """
            SELECT uri, title, content, memory_type, scope, namespace, author_username, metadata, updated_at
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
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username, metadata, updated_at,
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

    async def search_session_summaries(
        self,
        *,
        query: str,
        limit: int,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        rows = await self._pool.fetch(
            """
            SELECT id::text AS session_id, author_username, project, started_at, ended_at, summary,
                   GREATEST(
                       similarity(COALESCE(summary, ''), $1),
                       similarity(COALESCE(project, ''), $1),
                       similarity(author_username, $1)
                   ) AS relevance
            FROM sessions
            WHERE ended_at IS NOT NULL
              AND summary IS NOT NULL
              AND btrim(summary) <> ''
              AND ($2::text IS NULL OR project = $2)
              AND (
                    summary % $1
                 OR summary ILIKE '%' || $1 || '%'
                 OR author_username % $1
                 OR author_username ILIKE '%' || $1 || '%'
                 OR COALESCE(project, '') % $1
                 OR COALESCE(project, '') ILIKE '%' || $1 || '%'
              )
            ORDER BY relevance DESC, ended_at DESC, started_at DESC
            LIMIT $3
            """,
            query,
            project,
            limit,
        )
        return [self._serialize_session_summary(row) for row in rows]

    async def search_viewer_memories(
        self,
        *,
        query: str,
        limit: int,
        cursor: dict[str, Any] | None,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        normalized_query = query.strip()
        fetch_limit = max(1, limit) + 1
        cursor_relevance = None if cursor is None else float(cursor["relevance"])
        cursor_updated_at = None if cursor is None else cursor["updated_at"]
        cursor_id = None if cursor is None else cursor["id"]

        rows = await self._pool.fetch(
            """
            WITH ranked AS (
                SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
                       metadata, tags, vitality_score, retrieval_count, last_accessed, deleted_at,
                       created_at, updated_at,
                       CASE
                           WHEN $1::text = '' THEN 0::double precision
                           ELSE GREATEST(similarity(title, $1), similarity(content, $1))
                       END AS relevance
                FROM memories
                WHERE scope <> 'personal'
                  AND (
                        $1::text = ''
                     OR title % $1
                     OR content % $1
                     OR title ILIKE '%' || $1 || '%'
                     OR content ILIKE '%' || $1 || '%'
                  )
            )
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
                   metadata, tags, vitality_score, retrieval_count, last_accessed, deleted_at,
                   created_at, updated_at, relevance
            FROM ranked
            WHERE $2::double precision IS NULL
               OR ROW(relevance, updated_at, id) < ROW($2, $3::timestamptz, $4::uuid)
            ORDER BY relevance DESC, updated_at DESC, id DESC
            LIMIT $5
            """,
            normalized_query,
            cursor_relevance,
            cursor_updated_at,
            cursor_id,
            fetch_limit,
        )

        has_next = len(rows) > limit
        visible_rows = rows[:limit]
        next_cursor = None
        if has_next and visible_rows:
            last_row = visible_rows[-1]
            next_cursor = {
                "relevance": float(last_row["relevance"]),
                "updated_at": last_row["updated_at"].isoformat(),
                "id": str(last_row["id"]),
            }

        return {
            "memories": [self._serialize_memory(row) for row in visible_rows],
            "page_info": {
                "has_next": has_next,
                "next_cursor": next_cursor,
                "returned_count": len(visible_rows),
                "query": normalized_query,
            },
        }

    async def load_team_members(self, usernames: list[str]) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        if not usernames:
            return []

        rows = await self._pool.fetch(
            """
            SELECT username, display_name, role, team, is_active, created_at
            FROM team_members
            WHERE username = ANY($1::text[])
            ORDER BY username ASC
            """,
            usernames,
        )
        return [self._serialize_record(row) for row in rows]

    async def load_recent_sessions_for_authors(
        self,
        usernames: list[str],
        *,
        limit_per_author: int = 4,
    ) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        if not usernames:
            return []

        rows = await self._pool.fetch(
            """
            SELECT id, author_username, project, started_at, ended_at, summary,
                   memories_read, memories_written
            FROM (
                SELECT id, author_username, project, started_at, ended_at, summary,
                       memories_read, memories_written,
                       ROW_NUMBER() OVER (
                           PARTITION BY author_username
                           ORDER BY started_at DESC, id DESC
                       ) AS author_rank
                FROM sessions
                WHERE author_username = ANY($1::text[])
            ) ranked_sessions
            WHERE author_rank <= $2
            ORDER BY started_at DESC, id DESC
            """,
            usernames,
            max(1, limit_per_author),
        )
        return [self._serialize_record(row) for row in rows]

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
        metadata: dict[str, Any] | None,
        author_id: UUID,
        author_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        namespace = extract_namespace(uri)
        structured_metadata = self._normalize_metadata(content=content, metadata=metadata)

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, content, content_hash, memory_type, scope, namespace, metadata FROM memories WHERE uri = $1",
                uri,
            )
            existing_metadata = dict(existing).get("metadata") if existing is not None else None
            if existing is not None and existing["content_hash"] == content_hash and (existing_metadata or {}) == structured_metadata:
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
                            author_id, author_username, tags, content_hash, metadata
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::text[], $10, $11::jsonb)
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
                        json.dumps(structured_metadata),
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
                            metadata = $9::jsonb,
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
                        json.dumps(structured_metadata),
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
                    json.dumps(
                        {
                            "scope": scope,
                            "memory_type": memory_type,
                            "tags": tags,
                            "memory_metadata": structured_metadata,
                        }
                    ),
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

    async def export_viewer_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        await self.connect()
        assert self._pool is not None

        memories = await self._pool.fetch(
            """
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
                 tags, metadata, vitality_score, retrieval_count, last_accessed, deleted_at,
                   created_at, updated_at
            FROM memories
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        sessions = await self._pool.fetch(
            """
            SELECT id, author_username, project, started_at, ended_at, summary,
                   memories_read, memories_written
            FROM sessions
            ORDER BY started_at DESC
            """
        )
        audit_log = await self._pool.fetch(
            """
            SELECT id, timestamp, actor_username, action, memory_id, uri, metadata
            FROM audit_log
            ORDER BY timestamp DESC
            """
        )
        team_members = await self._pool.fetch(
            """
            SELECT username, display_name, role, team, is_active, created_at
            FROM team_members
            ORDER BY username ASC
            """
        )

        return {
            "memories": [self._serialize_memory(row) for row in memories],
            "sessions": [self._serialize_record(row) for row in sessions],
            "audit_log": [self._serialize_record(row) for row in audit_log],
            "team_members": [self._serialize_record(row) for row in team_members],
        }

    def _serialize_memory(self, row: asyncpg.Record) -> dict[str, Any]:
        serialized = self._serialize_record(row)
        metadata = serialized.get("metadata")
        if isinstance(metadata, str):
            stripped_metadata = metadata.strip()
            if stripped_metadata:
                try:
                    metadata = json.loads(stripped_metadata)
                except json.JSONDecodeError:
                    serialized["metadata"] = metadata
                    return serialized
            else:
                metadata = None

        if metadata:
            serialized["metadata"] = metadata
            return serialized

        serialized["metadata"] = self._extract_metadata_from_content(serialized.get("content") or "")
        return serialized

    def _serialize_session_summary(self, row: asyncpg.Record) -> dict[str, Any]:
        serialized = self._serialize_record(row)
        summary = str(serialized.get("summary") or "")
        project = serialized.get("project")
        session_id = serialized["session_id"]
        return {
            "result_type": "session_summary",
            "session_id": session_id,
            "uri": f"project://{project}/sessions/{session_id}" if project else f"system://sessions/{session_id}",
            "title": f"Session summary {project or serialized.get('author_username') or 'unknown'} {session_id[:8]}",
            "content": summary,
            "summary": summary,
            "memory_type": "session_summary",
            "scope": "project" if project else "system",
            "namespace": f"project://{project}" if project else "system://sessions",
            "author_username": serialized.get("author_username"),
            "metadata": self._extract_metadata_from_content(summary),
            "relevance": serialized.get("relevance", 0),
            "started_at": serialized.get("started_at"),
            "ended_at": serialized.get("ended_at"),
            "updated_at": serialized.get("ended_at") or serialized.get("started_at"),
            "retrieval_count": 0,
            "project": project,
        }

    @staticmethod
    def _normalize_metadata(content: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
        if metadata is None:
            return PostgresStorage._extract_metadata_from_content(content)
        return {
            str(key): value
            for key, value in metadata.items()
            if value not in (None, "")
        }

    @staticmethod
    def _extract_metadata_from_content(content: str) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for match in STRUCTURED_METADATA_PATTERN.finditer(content):
            label = re.sub(r"[\s_]+", " ", match.group("label").strip().lower())
            value = match.group("value").strip()
            if not value:
                continue
            key = "next_steps" if label == "next steps" else label
            metadata[key] = value
        return metadata

    def _serialize_record(self, row: asyncpg.Record) -> dict[str, Any]:
        serialized = dict(row)
        for key, value in list(serialized.items()):
            if isinstance(value, UUID):
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
        return serialized
