from __future__ import annotations

import hashlib
import json
from datetime import datetime
import math
from pathlib import Path
import re
from typing import Any
import unicodedata
from uuid import UUID

import asyncpg

from olinkb.domain import extract_namespace, parse_tags, scope_filters_for_query, validate_member_role


STRUCTURED_METADATA_PATTERN = re.compile(
    r"^(?P<label>What|Why|Where|Learned|Context|Decision|Evidence|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):\s*(?P<value>.*?)(?=^(?:What|Why|Where|Learned|Context|Decision|Evidence|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
LEAN_PREVIEW_MAX_CHARS = 120
BOOT_SCOPE_SCORE = {"system": 40, "team": 28, "project": 18, "personal": 8, "org": 6}
BOOT_MEMORY_TYPE_SCORE = {
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
PREVIEW_METADATA_KEYS = (
    "what",
    "decision",
    "why",
    "learned",
    "context",
    "evidence",
    "goal",
    "accomplished",
    "next_steps",
)
SEARCH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_:][a-z0-9]+)*")
SEARCH_STOP_WORDS = {
    "a",
    "about",
    "al",
    "and",
    "are",
    "con",
    "cual",
    "cuentame",
    "de",
    "del",
    "does",
    "donde",
    "el",
    "en",
    "esta",
    "este",
    "exists",
    "existe",
    "for",
    "hay",
    "how",
    "is",
    "la",
    "las",
    "los",
    "me",
    "of",
    "por",
    "que",
    "show",
    "si",
    "sobre",
    "tell",
    "the",
    "there",
    "tiene",
    "un",
    "una",
    "what",
}
SEARCH_TERM_EXPANSIONS = {
    "doc": ("documentation", "documentacion", "docs"),
    "docs": ("documentation", "documentacion", "doc"),
    "documentacion": ("documentation", "docs"),
    "documentation": ("documentacion", "docs"),
    "tecnica": ("technical", "technical-documentation"),
    "tecnico": ("technical", "technical-documentation"),
    "technical": ("tecnica", "technical-documentation"),
    "negocio": ("business", "business-documentation", "documentacion-negocio"),
    "negocios": ("business", "business-documentation", "documentacion-negocio"),
    "business": ("negocio", "business-documentation", "documentacion-negocio"),
    "global": ("global-documentation", "documentacion-global"),
    "repo": ("repository-documentation", "documentacion-repo"),
    "repositorio": ("repo", "repository-documentation", "documentacion-repo"),
}


class PostgresStorage:
    def __init__(self, dsn: str, pool_max_size: int = 5) -> None:
        self._dsn = dsn
        self._pool_max_size = max(1, pool_max_size)
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=self._pool_max_size)

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

    async def create_or_update_project_member(
        self,
        *,
        member_id: UUID,
        username: str,
        project: str,
        team: str,
        role: str = "developer",
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None
        validate_member_role(role)

        row = await self._pool.fetchrow(
            """
            INSERT INTO project_members (project, member_id, username, team, role, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            ON CONFLICT (project, username)
            DO UPDATE SET
                member_id = EXCLUDED.member_id,
                team = EXCLUDED.team,
                role = EXCLUDED.role,
                is_active = TRUE,
                updated_at = NOW()
            RETURNING id, project, member_id, username, team, role, is_active
            """,
            project,
            member_id,
            username,
            team,
            role,
        )
        return dict(row)

    async def ensure_project_member(
        self,
        *,
        member_id: UUID,
        username: str,
        project: str,
        team: str,
        default_role: str = "developer",
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        row = await self._pool.fetchrow(
            """
            SELECT id, project, member_id, username, team, role, is_active
            FROM project_members
            WHERE project = $1 AND username = $2
            """,
            project,
            username,
        )
        if row is None:
            return await self.create_or_update_project_member(
                member_id=member_id,
                username=username,
                project=project,
                team=team,
                role=default_role,
            )
        if row["member_id"] != member_id or row["team"] != team or row["is_active"] is not True:
            row = await self._pool.fetchrow(
                """
                UPDATE project_members
                SET member_id = $3,
                    team = $4,
                    is_active = TRUE,
                    updated_at = NOW()
                WHERE project = $1 AND username = $2
                RETURNING id, project, member_id, username, team, role, is_active
                """,
                project,
                username,
                member_id,
                team,
            )
        return dict(row)

    async def get_project_member(self, *, username: str, project: str) -> dict[str, Any] | None:
        await self.connect()
        assert self._pool is not None

        row = await self._pool.fetchrow(
            """
            SELECT id, project, member_id, username, team, role, is_active
            FROM project_members
            WHERE project = $1 AND username = $2
            """,
            project,
            username,
        )
        if row is None:
            return None
        return dict(row)

    async def load_pending_proposals(self, *, project: str, limit: int = 5) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        namespace = f"project://{project}"
        total_count = await self._pool.fetchval(
            """
            SELECT COUNT(*)
            FROM memories
            WHERE deleted_at IS NULL
              AND scope = 'project'
              AND namespace = $1
              AND approval_status = 'pending'
            """,
            namespace,
        )
        rows = await self._pool.fetch(
            """
            SELECT id, uri, title, content, memory_type, proposed_memory_type, approval_status,
                   author_username, proposed_by_username, proposed_at, proposal_note,
                   scope, namespace, metadata, updated_at
            FROM memories
            WHERE deleted_at IS NULL
              AND scope = 'project'
              AND namespace = $1
              AND approval_status = 'pending'
            ORDER BY proposed_at DESC NULLS LAST, updated_at DESC
            LIMIT $2
            """,
            namespace,
            limit,
        )
        return {
            "total_count": int(total_count or 0),
            "proposals": [self._serialize_memory(row, include_content=False) for row in rows],
        }

    async def propose_memory_promotion(
        self,
        *,
        uri: str,
        proposed_memory_type: str,
        rationale: str,
        actor_id: UUID,
        actor_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT id, uri, scope, namespace, memory_type, proposed_memory_type, approval_status
                FROM memories
                WHERE uri = $1 AND deleted_at IS NULL
                """,
                uri,
            )
            if existing is None:
                raise ValueError(f"Memory not found for URI: {uri}")
            if existing["scope"] != "project":
                raise ValueError("Only project memories can be proposed for promotion")

            row = await conn.fetchrow(
                """
                UPDATE memories
                SET proposed_memory_type = $2,
                    approval_status = 'pending',
                    proposed_by = $3,
                    proposed_by_username = $4,
                    proposed_at = NOW(),
                    proposal_note = $5,
                    reviewed_by = NULL,
                    reviewed_by_username = NULL,
                    reviewed_at = NULL,
                    review_note = NULL,
                    updated_at = NOW()
                WHERE uri = $1
                RETURNING id, uri, namespace, scope, memory_type, proposed_memory_type, approval_status
                """,
                uri,
                proposed_memory_type,
                actor_id,
                actor_username,
                rationale,
            )
            await conn.execute(
                """
                INSERT INTO audit_log (actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
                VALUES ($1, $2, 'propose_promotion', $3, $4, NULL, NULL, $5::jsonb)
                """,
                actor_id,
                actor_username,
                row["id"],
                uri,
                json.dumps(
                    {
                        "proposed_memory_type": proposed_memory_type,
                        "rationale": rationale,
                        "previous_memory_type": existing["memory_type"],
                    }
                ),
            )

        return {
            "status": "pending",
            "id": str(row["id"]),
            "uri": row["uri"],
            "namespace": row["namespace"],
            "scope": row["scope"],
            "memory_type": row["memory_type"],
            "proposed_memory_type": row["proposed_memory_type"],
            "approval_status": row["approval_status"],
        }

    async def review_memory_proposal(
        self,
        *,
        uri: str,
        action: str,
        note: str,
        reviewer_id: UUID,
        reviewer_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        if action not in {"approve", "reject"}:
            raise ValueError(f"Unsupported review action: {action}")

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT id, uri, scope, namespace, memory_type, proposed_memory_type, approval_status
                FROM memories
                WHERE uri = $1 AND deleted_at IS NULL
                """,
                uri,
            )
            if existing is None:
                raise ValueError(f"Memory not found for URI: {uri}")
            if existing["approval_status"] != "pending" or not existing["proposed_memory_type"]:
                raise ValueError(f"Memory does not have a pending proposal: {uri}")

            if action == "approve":
                row = await conn.fetchrow(
                    """
                    UPDATE memories
                    SET memory_type = proposed_memory_type,
                        approval_status = 'approved',
                        reviewed_by = $2,
                        reviewed_by_username = $3,
                        reviewed_at = NOW(),
                        review_note = $4,
                        updated_at = NOW()
                    WHERE uri = $1
                    RETURNING id, uri, namespace, scope, memory_type, proposed_memory_type, approval_status
                    """,
                    uri,
                    reviewer_id,
                    reviewer_username,
                    note,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE memories
                    SET approval_status = 'rejected',
                        reviewed_by = $2,
                        reviewed_by_username = $3,
                        reviewed_at = NOW(),
                        review_note = $4,
                        updated_at = NOW()
                    WHERE uri = $1
                    RETURNING id, uri, namespace, scope, memory_type, proposed_memory_type, approval_status
                    """,
                    uri,
                    reviewer_id,
                    reviewer_username,
                    note,
                )
            await conn.execute(
                """
                INSERT INTO audit_log (actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
                VALUES ($1, $2, $3, $4, $5, NULL, NULL, $6::jsonb)
                """,
                reviewer_id,
                reviewer_username,
                f"{action}_proposal",
                row["id"],
                uri,
                json.dumps(
                    {
                        "note": note,
                        "proposed_memory_type": existing["proposed_memory_type"],
                        "previous_memory_type": existing["memory_type"],
                    }
                ),
            )

        return {
            "status": row["approval_status"],
            "id": str(row["id"]),
            "uri": row["uri"],
            "namespace": row["namespace"],
            "scope": row["scope"],
            "memory_type": row["memory_type"],
            "proposed_memory_type": row["proposed_memory_type"],
            "approval_status": row["approval_status"],
        }

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

    async def load_boot_memories(
        self,
        username: str,
        project: str | None,
        limit: int = 40,
        full_content_limit: int = 5,
    ) -> list[dict[str, Any]]:
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
        serialized_rows = [self._serialize_memory(row, include_content=True) for row in rows]
        full_content_indexes = self._select_boot_full_content_indexes(serialized_rows, full_content_limit)
        return [
            self._finalize_memory_payload(memory.copy(), include_content=index in full_content_indexes)
            for index, memory in enumerate(serialized_rows)
        ]

    async def search_memories(
        self,
        query: str,
        scope: str,
        limit: int,
        include_content: bool = False,
        username: str | None = None,
        team: str | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None

        scope_filters = scope_filters_for_query(scope)
        project_namespace = f"project://{project}" if project else None
        search_terms = self._build_search_terms(query)
        rows = await self._pool.fetch(
            """
            SELECT m.id, m.uri, m.title, m.content, m.memory_type, m.scope, m.namespace,
                   m.author_username, m.metadata, m.updated_at,
                   GREATEST(
                       similarity(m.title, $1),
                       similarity(m.content, $1),
                       similarity(m.uri, $1),
                       COALESCE(
                           (
                               SELECT MAX(
                                   GREATEST(
                                       similarity(m.title, term),
                                       similarity(m.content, term),
                                       similarity(m.uri, term),
                                       similarity(m.memory_type, term),
                                       similarity(COALESCE(array_to_string(m.tags, ' '), ''), term),
                                       similarity(COALESCE(m.metadata::text, ''), term)
                                   )
                               )
                               FROM unnest($7::text[]) AS term
                           ),
                           0::double precision
                       )
                   ) AS relevance
            FROM memories AS m
            LEFT JOIN team_members AS tm ON tm.id = m.author_id
            WHERE m.deleted_at IS NULL
              AND m.scope = ANY($2::text[])
              AND (
                    m.scope = 'system'
                 OR m.scope = 'org'
                 OR (m.scope = 'personal' AND m.author_username = $4)
                 OR (m.scope = 'project' AND $5::text IS NOT NULL AND m.namespace = $5)
                 OR (m.scope = 'team' AND $6::text IS NOT NULL AND tm.team = $6)
              )
              AND (
                    m.title % $1
                 OR m.content % $1
                 OR m.uri % $1
                 OR m.title ILIKE '%' || $1 || '%'
                 OR m.content ILIKE '%' || $1 || '%'
                     OR EXISTS (
                         SELECT 1
                         FROM unnest($7::text[]) AS term
                         WHERE m.title ILIKE '%' || term || '%'
                          OR m.content ILIKE '%' || term || '%'
                          OR m.uri ILIKE '%' || term || '%'
                          OR m.memory_type ILIKE '%' || term || '%'
                          OR COALESCE(m.metadata::text, '') ILIKE '%' || term || '%'
                          OR EXISTS (
                              SELECT 1
                              FROM unnest(COALESCE(m.tags, ARRAY[]::text[])) AS tag
                              WHERE tag ILIKE '%' || term || '%'
                          )
                     )
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
            search_terms,
        )
        return [self._serialize_memory(row, include_content=include_content) for row in rows]

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
        team: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        normalized_query = query.strip()
        fetch_limit = max(1, limit) + 1
        project_namespace = f"project://{project}" if project else None
        search_terms = self._build_search_terms(normalized_query)
        cursor_relevance = None if cursor is None else float(cursor["relevance"])
        cursor_updated_at = None if cursor is None else cursor["updated_at"]
        cursor_id = None if cursor is None else cursor["id"]

        rows = await self._pool.fetch(
            """
            WITH ranked AS (
                SELECT m.id, m.uri, m.title, m.content, m.memory_type, m.scope, m.namespace,
                       m.author_username, m.metadata, m.tags, m.vitality_score, m.retrieval_count,
                       m.last_accessed, m.deleted_at, m.created_at, m.updated_at,
                       CASE
                           WHEN $1::text = '' THEN 0::double precision
                           ELSE GREATEST(
                               similarity(m.title, $1),
                               similarity(m.content, $1),
                               COALESCE(
                                   (
                                       SELECT MAX(
                                           GREATEST(
                                               similarity(m.title, term),
                                               similarity(m.content, term),
                                               similarity(m.memory_type, term),
                                               similarity(COALESCE(array_to_string(m.tags, ' '), ''), term),
                                               similarity(COALESCE(m.metadata::text, ''), term)
                                           )
                                       )
                                       FROM unnest($8::text[]) AS term
                                   ),
                                   0::double precision
                               )
                           )
                       END AS relevance
                FROM memories AS m
                LEFT JOIN team_members AS tm ON tm.id = m.author_id
                WHERE m.scope <> 'personal'
                  AND (
                        m.scope = 'system'
                     OR m.scope = 'org'
                            OR (m.scope = 'project' AND ($2::text IS NULL OR m.namespace = $2))
                            OR (m.scope = 'team' AND ($3::text IS NULL OR tm.team = $3))
                  )
                  AND (
                        $1::text = ''
                     OR m.title % $1
                     OR m.content % $1
                     OR m.title ILIKE '%' || $1 || '%'
                     OR m.content ILIKE '%' || $1 || '%'
                       OR EXISTS (
                           SELECT 1
                           FROM unnest($8::text[]) AS term
                           WHERE m.title ILIKE '%' || term || '%'
                            OR m.content ILIKE '%' || term || '%'
                            OR m.memory_type ILIKE '%' || term || '%'
                            OR COALESCE(m.metadata::text, '') ILIKE '%' || term || '%'
                            OR EXISTS (
                                SELECT 1
                                FROM unnest(COALESCE(m.tags, ARRAY[]::text[])) AS tag
                                WHERE tag ILIKE '%' || term || '%'
                            )
                       )
                  )
            )
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
                   metadata, tags, vitality_score, retrieval_count, last_accessed, deleted_at,
                   created_at, updated_at, relevance
            FROM ranked
            WHERE $4::double precision IS NULL
               OR ROW(relevance, updated_at, id) < ROW($4, $5::timestamptz, $6::uuid)
            ORDER BY relevance DESC, updated_at DESC, id DESC
            LIMIT $7
            """,
            normalized_query,
            project_namespace,
            team,
            cursor_relevance,
            cursor_updated_at,
            cursor_id,
            fetch_limit,
            search_terms,
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

    async def count_viewer_memories(
        self,
        *,
        query: str,
        team: str | None = None,
        project: str | None = None,
    ) -> int:
        await self.connect()
        assert self._pool is not None

        normalized_query = query.strip()
        project_namespace = f"project://{project}" if project else None
        search_terms = self._build_search_terms(normalized_query)

        count = await self._pool.fetchval(
            """
            SELECT COUNT(*)
            FROM memories AS m
            LEFT JOIN team_members AS tm ON tm.id = m.author_id
            WHERE m.scope <> 'personal'
              AND (
                    m.scope = 'system'
                 OR m.scope = 'org'
                 OR (m.scope = 'project' AND ($2::text IS NULL OR m.namespace = $2))
                 OR (m.scope = 'team' AND ($3::text IS NULL OR tm.team = $3))
              )
              AND (
                    $1::text = ''
                 OR m.title % $1
                 OR m.content % $1
                 OR m.title ILIKE '%' || $1 || '%'
                 OR m.content ILIKE '%' || $1 || '%'
                     OR EXISTS (
                         SELECT 1
                         FROM unnest($4::text[]) AS term
                         WHERE m.title ILIKE '%' || term || '%'
                          OR m.content ILIKE '%' || term || '%'
                          OR m.memory_type ILIKE '%' || term || '%'
                          OR COALESCE(m.metadata::text, '') ILIKE '%' || term || '%'
                          OR EXISTS (
                              SELECT 1
                              FROM unnest(COALESCE(m.tags, ARRAY[]::text[])) AS tag
                              WHERE tag ILIKE '%' || term || '%'
                          )
                     )
              )
            """,
            normalized_query,
            project_namespace,
            team,
                search_terms,
        )
        return int(count or 0)

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

    async def benchmark_payloads(
        self,
        *,
        username: str,
        project: str | None,
        sample_size: int = 200,
        boot_limit: int = 40,
        boot_full_content_limit: int = 5,
    ) -> dict[str, Any]:
        await self.connect()
        assert self._pool is not None

        boot_full = await self.load_boot_memories(
            username=username,
            project=project,
            limit=boot_limit,
            full_content_limit=boot_limit,
        )
        boot_hybrid = await self.load_boot_memories(
            username=username,
            project=project,
            limit=boot_limit,
            full_content_limit=boot_full_content_limit,
        )
        sample_rows = await self._pool.fetch(
            """
            SELECT id, uri, title, content, memory_type, scope, namespace, author_username,
                   tags, metadata, vitality_score, retrieval_count, last_accessed, deleted_at,
                   created_at, updated_at
            FROM memories
            ORDER BY updated_at DESC, created_at DESC
            LIMIT $1
            """,
            sample_size,
        )
        sample_full = [self._serialize_memory(row, include_content=True) for row in sample_rows]
        sample_lean = [self._serialize_memory(row, include_content=False) for row in sample_rows]

        full_boot_metrics = self._measure_payload(boot_full)
        hybrid_boot_metrics = self._measure_payload(boot_hybrid)
        full_sample_metrics = self._measure_payload(sample_full)
        lean_sample_metrics = self._measure_payload(sample_lean)

        return {
            "boot": {
                "limit": boot_limit,
                "full_content_limit": boot_full_content_limit,
                "full": full_boot_metrics,
                "hybrid": hybrid_boot_metrics,
                "savings": self._measure_payload_savings(full_boot_metrics, hybrid_boot_metrics),
            },
            "sample": {
                "size": len(sample_rows),
                "full": full_sample_metrics,
                "lean": lean_sample_metrics,
                "savings": self._measure_payload_savings(full_sample_metrics, lean_sample_metrics),
            },
        }

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

    def _serialize_memory(self, row: asyncpg.Record, *, include_content: bool = True) -> dict[str, Any]:
        serialized = self._serialize_record(row)
        metadata = serialized.get("metadata")
        if isinstance(metadata, str):
            stripped_metadata = metadata.strip()
            if stripped_metadata:
                try:
                    metadata = json.loads(stripped_metadata)
                except json.JSONDecodeError:
                    serialized["metadata"] = metadata
                    return self._finalize_memory_payload(serialized, include_content=include_content)
            else:
                metadata = None

        if metadata:
            serialized["metadata"] = metadata
            return self._finalize_memory_payload(serialized, include_content=include_content)

        serialized["metadata"] = self._extract_metadata_from_content(serialized.get("content") or "")
        return self._finalize_memory_payload(serialized, include_content=include_content)

    @staticmethod
    def _finalize_memory_payload(serialized: dict[str, Any], *, include_content: bool) -> dict[str, Any]:
        if not include_content:
            preview = PostgresStorage._build_preview(serialized)
            if preview:
                serialized["preview"] = preview
            serialized.pop("content", None)
        return serialized

    @staticmethod
    def _select_boot_full_content_indexes(memories: list[dict[str, Any]], full_content_limit: int) -> set[int]:
        if full_content_limit <= 0:
            return set()
        scored = [
            (PostgresStorage._boot_memory_score(memory, index), index)
            for index, memory in enumerate(memories)
        ]
        selected = sorted(scored, key=lambda item: (-item[0], item[1]))[: min(full_content_limit, len(memories))]
        return {index for _, index in selected}

    @staticmethod
    def _boot_memory_score(memory: dict[str, Any], index: int) -> int:
        metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
        scope = str(memory.get("scope") or "")
        memory_type = str(memory.get("memory_type") or "")
        score = BOOT_SCOPE_SCORE.get(scope, 0)
        score += BOOT_MEMORY_TYPE_SCORE.get(memory_type, 0)
        score += max(0, 8 - index)
        score += min(len(metadata), 4) * 2
        if metadata.get("what"):
            score += 3
        if metadata.get("decision"):
            score += 3
        if metadata.get("learned"):
            score += 2
        return score

    @staticmethod
    def _build_preview(serialized: dict[str, Any]) -> str | None:
        metadata = serialized.get("metadata")
        if isinstance(metadata, dict):
            for key in PREVIEW_METADATA_KEYS:
                value = metadata.get(key)
                if value:
                    return PostgresStorage._truncate_preview(f"{key.replace('_', ' ').title()}: {str(value).strip()}")

        content = str(serialized.get("content") or "").strip()
        if not content:
            return None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                return PostgresStorage._truncate_preview(stripped)
        return None

    @staticmethod
    def _truncate_preview(value: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip()
        if len(normalized) <= LEAN_PREVIEW_MAX_CHARS:
            return normalized
        return normalized[: LEAN_PREVIEW_MAX_CHARS - 1].rstrip() + "…"

    @staticmethod
    def _measure_payload(payload: Any) -> dict[str, int]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        char_count = len(serialized)
        return {
            "bytes": len(serialized.encode("utf-8")),
            "chars": char_count,
            "approx_tokens": math.ceil(char_count / 4) if char_count else 0,
        }

    @staticmethod
    def _measure_payload_savings(full_metrics: dict[str, int], lean_metrics: dict[str, int]) -> dict[str, int | float]:
        byte_savings = max(0, full_metrics["bytes"] - lean_metrics["bytes"])
        token_savings = max(0, full_metrics["approx_tokens"] - lean_metrics["approx_tokens"])
        byte_pct = 0.0
        token_pct = 0.0
        if full_metrics["bytes"]:
            byte_pct = round((byte_savings / full_metrics["bytes"]) * 100, 2)
        if full_metrics["approx_tokens"]:
            token_pct = round((token_savings / full_metrics["approx_tokens"]) * 100, 2)
        return {
            "bytes": byte_savings,
            "approx_tokens": token_savings,
            "byte_pct": byte_pct,
            "token_pct": token_pct,
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

    @staticmethod
    def _build_search_terms(query: str) -> list[str]:
        normalized = PostgresStorage._normalize_search_text(query)
        terms: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            if len(term) < 3 or term in SEARCH_STOP_WORDS or term in seen:
                return
            seen.add(term)
            terms.append(term)

        for token in SEARCH_TOKEN_PATTERN.findall(normalized):
            add(token)
            for expanded in SEARCH_TERM_EXPANSIONS.get(token, ()): 
                add(expanded)
        return terms

    @staticmethod
    def _normalize_search_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        return ascii_value.lower()

    def _serialize_record(self, row: asyncpg.Record) -> dict[str, Any]:
        serialized = dict(row)
        for key, value in list(serialized.items()):
            if isinstance(value, UUID):
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
        return serialized
