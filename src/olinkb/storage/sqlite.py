from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from olinkb.domain import extract_namespace, scope_filters_for_query, validate_member_role
from olinkb.storage.postgres import PostgresStorage


SQLITE_SCHEMA_VERSION = "sqlite-init-v1"


class SqliteStorage:
    def __init__(self, path: str | Path | None) -> None:
        if path is None:
            raise ValueError("SQLite storage requires a database path")
        self._path = Path(path).expanduser()
        self._connection: sqlite3.Connection | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._connection = connection
        await self.run_migrations()

    async def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    async def run_migrations(self) -> list[str]:
        await self.connect()
        connection = self._require_connection()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        row = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (SQLITE_SCHEMA_VERSION,),
        ).fetchone()
        if row is not None:
            return []

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS team_members (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT,
                role TEXT NOT NULL,
                team TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS project_members (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                member_id TEXT NOT NULL,
                username TEXT NOT NULL,
                team TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project, username)
            );

            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                uri TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                namespace TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_username TEXT NOT NULL,
                tags TEXT NOT NULL,
                metadata TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                vitality_score REAL NOT NULL DEFAULT 1.0,
                retrieval_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                deleted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approval_status TEXT NOT NULL DEFAULT 'approved',
                proposed_memory_type TEXT,
                proposed_by TEXT,
                proposed_by_username TEXT,
                proposed_at TEXT,
                proposal_note TEXT,
                reviewed_by TEXT,
                reviewed_by_username TEXT,
                reviewed_at TEXT,
                review_note TEXT
            );

            CREATE TABLE IF NOT EXISTS managed_memory_targets (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(memory_id, target_type, target_value)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                author_id TEXT NOT NULL,
                author_username TEXT NOT NULL,
                project TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                summary TEXT,
                memories_read INTEGER NOT NULL DEFAULT 0,
                memories_written INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                memory_id TEXT,
                uri TEXT,
                old_content TEXT,
                new_content TEXT,
                metadata TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
            CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
            CREATE INDEX IF NOT EXISTS idx_memories_author_username ON memories(author_username);
            CREATE INDEX IF NOT EXISTS idx_memories_approval_status ON memories(approval_status);
            CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project);
            CREATE INDEX IF NOT EXISTS idx_project_members_username ON project_members(username);
            CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_memory_id ON managed_memory_targets(memory_id);
            CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_target ON managed_memory_targets(target_type, target_value);
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SQLITE_SCHEMA_VERSION, self._now()),
        )
        connection.commit()
        return [SQLITE_SCHEMA_VERSION]

    async def create_or_update_member(
        self,
        username: str,
        team: str,
        role: str = "developer",
        display_name: str | None = None,
    ) -> dict[str, Any]:
        await self.connect()
        validate_member_role(role)
        connection = self._require_connection()
        now = self._now()
        row = connection.execute(
            "SELECT id, username, display_name, role, team, is_active, created_at FROM team_members WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            member_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO team_members (id, username, display_name, role, team, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (member_id, username, display_name, role, team, now),
            )
        else:
            member_id = str(row["id"])
            connection.execute(
                """
                UPDATE team_members
                SET display_name = COALESCE(?, display_name),
                    role = ?,
                    team = ?,
                    is_active = 1
                WHERE username = ?
                """,
                (display_name, role, team, username),
            )
        connection.commit()
        return await self.ensure_member(username=username, team=team)

    async def ensure_member(self, username: str, team: str) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        row = connection.execute(
            "SELECT id, username, display_name, role, team, is_active, created_at FROM team_members WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return await self.create_or_update_member(username=username, team=team)
        return self._serialize_member(row)

    async def create_or_update_project_member(
        self,
        *,
        member_id: str,
        username: str,
        project: str,
        team: str,
        role: str = "developer",
    ) -> dict[str, Any]:
        await self.connect()
        validate_member_role(role)
        connection = self._require_connection()
        row = connection.execute(
            "SELECT id FROM project_members WHERE project = ? AND username = ?",
            (project, username),
        ).fetchone()
        now = self._now()
        if row is None:
            connection.execute(
                """
                INSERT INTO project_members (id, project, member_id, username, team, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (str(uuid4()), project, member_id, username, team, role, now, now),
            )
        else:
            connection.execute(
                """
                UPDATE project_members
                SET member_id = ?, team = ?, role = ?, is_active = 1, updated_at = ?
                WHERE project = ? AND username = ?
                """,
                (member_id, team, role, now, project, username),
            )
        connection.commit()
        return (await self.get_project_member(username=username, project=project)) or {}

    async def ensure_project_member(
        self,
        *,
        member_id: str,
        username: str,
        project: str,
        team: str,
        default_role: str = "developer",
    ) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM project_members WHERE project = ? AND username = ?",
            (project, username),
        ).fetchone()
        if row is None:
            return await self.create_or_update_project_member(
                member_id=member_id,
                username=username,
                project=project,
                team=team,
                role=default_role,
            )
        if str(row["member_id"]) != str(member_id) or str(row["team"]) != team or int(row["is_active"] or 0) != 1:
            connection.execute(
                """
                UPDATE project_members
                SET member_id = ?, team = ?, is_active = 1, updated_at = ?
                WHERE project = ? AND username = ?
                """,
                (member_id, team, self._now(), project, username),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM project_members WHERE project = ? AND username = ?",
                (project, username),
            ).fetchone()
        return self._serialize_project_member(row)

    async def get_project_member(self, *, username: str, project: str) -> dict[str, Any] | None:
        await self.connect()
        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM project_members WHERE project = ? AND username = ?",
            (project, username),
        ).fetchone()
        if row is None:
            return None
        return self._serialize_project_member(row)

    async def load_pending_proposals(self, *, project: str, limit: int = 5) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        namespace = f"project://{project}"
        total_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM memories WHERE namespace = ? AND approval_status = 'pending' AND deleted_at IS NULL",
                (namespace,),
            ).fetchone()[0]
        )
        rows = connection.execute(
            """
            SELECT * FROM memories
            WHERE namespace = ? AND approval_status = 'pending' AND deleted_at IS NULL
            ORDER BY COALESCE(proposed_at, updated_at) DESC
            LIMIT ?
            """,
            (namespace, limit),
        ).fetchall()
        return {
            "total_count": total_count,
            "proposals": [self._serialize_memory_row(row, include_content=True) for row in rows],
        }

    async def propose_memory_promotion(
        self,
        *,
        uri: str,
        proposed_memory_type: str,
        rationale: str,
        actor_id: str,
        actor_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        row = connection.execute("SELECT * FROM memories WHERE uri = ? AND deleted_at IS NULL", (uri,)).fetchone()
        if row is None:
            raise ValueError(f"Memory not found: {uri}")
        now = self._now()
        connection.execute(
            """
            UPDATE memories
            SET approval_status = 'pending',
                proposed_memory_type = ?,
                proposed_by = ?,
                proposed_by_username = ?,
                proposed_at = ?,
                proposal_note = ?,
                updated_at = ?
            WHERE uri = ?
            """,
            (proposed_memory_type, actor_id, actor_username, now, rationale, now, uri),
        )
        connection.execute(
            """
            INSERT INTO audit_log (timestamp, actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                now,
                actor_id,
                actor_username,
                "propose_memory_promotion",
                str(row["id"]),
                uri,
                json.dumps({"proposed_memory_type": proposed_memory_type, "rationale": rationale}),
            ),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM memories WHERE uri = ?", (uri,)).fetchone()
        assert updated is not None
        payload = self._serialize_memory_row(updated, include_content=True)
        payload["status"] = "pending"
        return payload

    async def review_memory_proposal(
        self,
        *,
        uri: str,
        action: str,
        note: str,
        reviewer_id: str,
        reviewer_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        normalized_action = action.strip().lower()
        if normalized_action not in {"approve", "reject"}:
            raise ValueError("action must be approve or reject")
        connection = self._require_connection()
        row = connection.execute("SELECT * FROM memories WHERE uri = ? AND deleted_at IS NULL", (uri,)).fetchone()
        if row is None:
            raise ValueError(f"Memory not found: {uri}")
        now = self._now()
        approval_status = "approved" if normalized_action == "approve" else "rejected"
        memory_type = row["proposed_memory_type"] if normalized_action == "approve" and row["proposed_memory_type"] else row["memory_type"]
        connection.execute(
            """
            UPDATE memories
            SET memory_type = ?,
                approval_status = ?,
                reviewed_by = ?,
                reviewed_by_username = ?,
                reviewed_at = ?,
                review_note = ?,
                updated_at = ?
            WHERE uri = ?
            """,
            (memory_type, approval_status, reviewer_id, reviewer_username, now, note, now, uri),
        )
        connection.execute(
            """
            INSERT INTO audit_log (timestamp, actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                now,
                reviewer_id,
                reviewer_username,
                "review_memory_proposal",
                str(row["id"]),
                uri,
                json.dumps({"action": normalized_action, "note": note}),
            ),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM memories WHERE uri = ?", (uri,)).fetchone()
        assert updated is not None
        payload = self._serialize_memory_row(updated, include_content=True)
        payload["status"] = approval_status
        return payload

    async def start_session(self, author_id: str, author_username: str, project: str | None) -> str:
        await self.connect()
        session_id = str(uuid4())
        connection = self._require_connection()
        connection.execute(
            """
            INSERT INTO sessions (id, author_id, author_username, project, started_at, ended_at, summary, memories_read, memories_written)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, 0, 0)
            """,
            (session_id, author_id, author_username, project, self._now()),
        )
        connection.commit()
        return session_id

    async def end_session(
        self,
        *,
        session_id: str,
        summary: str,
        memories_read: int,
        memories_written: int,
    ) -> None:
        await self.connect()
        connection = self._require_connection()
        connection.execute(
            """
            UPDATE sessions
            SET summary = ?, ended_at = ?, memories_read = ?, memories_written = ?
            WHERE id = ?
            """,
            (summary, self._now(), memories_read, memories_written, session_id),
        )
        connection.commit()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        await self.connect()
        row = self._require_connection().execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._serialize_row(row)

    async def load_boot_memories(
        self,
        *,
        username: str,
        project: str | None,
        limit: int = 40,
        full_content_limit: int = 5,
    ) -> list[dict[str, Any]]:
        await self.connect()
        rows = [
            row
            for row in self._require_connection().execute(
                "SELECT * FROM memories WHERE deleted_at IS NULL ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
            if self._matches_boot_scope(row, username=username, project=project)
        ][:limit]
        memories = [self._serialize_memory_row(row, include_content=True) for row in rows]
        selected_indexes = PostgresStorage._select_boot_full_content_indexes(memories, full_content_limit)
        return [
            memory if index in selected_indexes else PostgresStorage._finalize_memory_payload(dict(memory), include_content=False)
            for index, memory in enumerate(memories)
        ]

    async def search_memories(
        self,
        *,
        query: str,
        scope: str,
        limit: int,
        include_content: bool,
        username: str,
        team: str,
        project: str | None,
    ) -> list[dict[str, Any]]:
        await self.connect()
        allowed_scopes = set(scope_filters_for_query(scope))
        terms = PostgresStorage._build_search_terms(query)
        normalized_query = PostgresStorage._normalize_search_text(query)
        matches: list[tuple[float, dict[str, Any]]] = []
        for row in self._require_connection().execute(
            "SELECT * FROM memories WHERE deleted_at IS NULL ORDER BY updated_at DESC, created_at DESC"
        ).fetchall():
            if row["scope"] not in allowed_scopes:
                continue
            if not self._matches_search_scope(row, username=username, team=team, project=project):
                continue
            score = self._score_memory(row, terms=terms, normalized_query=normalized_query)
            if score <= 0:
                continue
            payload = self._serialize_memory_row(row, include_content=include_content)
            payload["relevance"] = score
            matches.append((score, payload))

        matches.sort(key=lambda item: (item[0], item[1].get("retrieval_count", 0), item[1].get("updated_at", "")), reverse=True)
        return [payload for _, payload in matches[:limit]]

    async def search_session_summaries(
        self,
        *,
        query: str,
        limit: int,
        project: str | None,
    ) -> list[dict[str, Any]]:
        await self.connect()
        terms = PostgresStorage._build_search_terms(query)
        normalized_query = PostgresStorage._normalize_search_text(query)
        matches: list[tuple[float, dict[str, Any]]] = []
        rows = self._require_connection().execute(
            "SELECT * FROM sessions WHERE summary IS NOT NULL ORDER BY COALESCE(ended_at, started_at) DESC"
        ).fetchall()
        for row in rows:
            if project is not None and row["project"] != project:
                continue
            haystack = PostgresStorage._normalize_search_text(str(row["summary"] or ""))
            score = 0.0
            if normalized_query and normalized_query in haystack:
                score += 1.5
            score += sum(1 for term in terms if term in haystack)
            if score <= 0:
                continue
            serialized = self._serialize_row(row)
            matches.append(
                (
                    score,
                    {
                        "result_type": "session_summary",
                        "session_id": serialized["id"],
                        "uri": f"project://{serialized['project']}/sessions/{serialized['id']}" if serialized.get("project") else f"system://sessions/{serialized['id']}",
                        "title": f"Session summary {serialized.get('project') or serialized.get('author_username') or 'unknown'} {serialized['id'][:8]}",
                        "summary": serialized.get("summary") or "",
                        "memory_type": "session_summary",
                        "scope": "project" if serialized.get("project") else "system",
                        "namespace": f"project://{serialized['project']}" if serialized.get("project") else "system://sessions",
                        "author_username": serialized.get("author_username"),
                        "metadata": PostgresStorage._extract_metadata_from_content(serialized.get("summary") or ""),
                        "relevance": score,
                        "started_at": serialized.get("started_at"),
                        "ended_at": serialized.get("ended_at"),
                        "updated_at": serialized.get("ended_at") or serialized.get("started_at"),
                        "retrieval_count": 0,
                        "project": serialized.get("project"),
                    },
                )
            )
        matches.sort(key=lambda item: (item[0], item[1].get("updated_at", "")), reverse=True)
        return [payload for _, payload in matches[:limit]]

    async def search_viewer_memories(
        self,
        *,
        query: str,
        limit: int,
        cursor: dict[str, Any] | None,
        team: str | None,
        project: str | None,
    ) -> dict[str, Any]:
        await self.connect()
        terms = PostgresStorage._build_search_terms(query)
        normalized_query = PostgresStorage._normalize_search_text(query)
        rows = [
            row
            for row in self._require_connection().execute(
                "SELECT * FROM memories WHERE scope != 'personal' ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
            if self._matches_viewer_filters(row, team=team, project=project)
        ]
        ranked: list[tuple[float, dict[str, Any], tuple[float, str, str]]] = []
        for row in rows:
            score = self._score_memory(row, terms=terms, normalized_query=normalized_query)
            if query.strip() and score <= 0:
                continue
            if not query.strip():
                score = 1.0
            payload = self._serialize_memory_row(row, include_content=True)
            payload["relevance"] = score
            sort_key = (-score, payload.get("updated_at") or "", payload["id"])
            ranked.append((score, payload, sort_key))

        ranked.sort(key=lambda item: (item[0], item[1].get("updated_at", ""), item[1]["id"]), reverse=True)
        start_index = 0
        if cursor is not None:
            for index, (_, payload, _) in enumerate(ranked):
                if self._cursor_is_after(payload, cursor):
                    start_index = index
                    break
            else:
                start_index = len(ranked)
        page_items = ranked[start_index:start_index + limit]
        next_cursor = None
        if start_index + limit < len(ranked) and page_items:
            last_payload = page_items[-1][1]
            next_cursor = {
                "relevance": last_payload["relevance"],
                "updated_at": last_payload["updated_at"],
                "id": last_payload["id"],
            }
        return {
            "memories": [item[1] for item in page_items],
            "page_info": {
                "query": query,
                "has_next": start_index + limit < len(ranked),
                "next_cursor": next_cursor,
                "returned_count": len(page_items),
            },
        }

    async def count_viewer_memories(self, *, query: str, team: str | None, project: str | None) -> int:
        page = await self.search_viewer_memories(query=query, limit=1000000, cursor=None, team=team, project=project)
        return len(page["memories"])

    async def load_team_members(self, usernames: list[str]) -> list[dict[str, Any]]:
        await self.connect()
        if not usernames:
            return []
        placeholders = ", ".join("?" for _ in usernames)
        rows = self._require_connection().execute(
            f"SELECT * FROM team_members WHERE username IN ({placeholders}) ORDER BY username",
            tuple(usernames),
        ).fetchall()
        return [self._serialize_member(row) for row in rows]

    async def load_recent_sessions_for_authors(self, author_usernames: list[str]) -> list[dict[str, Any]]:
        await self.connect()
        if not author_usernames:
            return []
        placeholders = ", ".join("?" for _ in author_usernames)
        rows = self._require_connection().execute(
            f"SELECT * FROM sessions WHERE author_username IN ({placeholders}) ORDER BY COALESCE(ended_at, started_at) DESC",
            tuple(author_usernames),
        ).fetchall()
        return [self._serialize_row(row) for row in rows]

    async def touch_memories(self, memory_ids: list[str]) -> None:
        await self.connect()
        if not memory_ids:
            return
        connection = self._require_connection()
        now = self._now()
        for memory_id in memory_ids:
            connection.execute(
                "UPDATE memories SET retrieval_count = retrieval_count + 1, last_accessed = ? WHERE id = ?",
                (now, memory_id),
            )
        connection.commit()

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
        author_id: str,
        author_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        normalized_metadata = PostgresStorage._normalize_metadata(content, metadata)
        serialized_tags = json.dumps(tags)
        serialized_metadata = json.dumps(normalized_metadata, ensure_ascii=False)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        namespace = extract_namespace(uri)
        now = self._now()
        existing = connection.execute("SELECT * FROM memories WHERE uri = ?", (uri,)).fetchone()
        if existing is not None:
            unchanged = (
                existing["title"] == title
                and existing["content_hash"] == content_hash
                and existing["memory_type"] == memory_type
                and existing["scope"] == scope
                and existing["author_username"] == author_username
                and existing["tags"] == serialized_tags
                and existing["metadata"] == serialized_metadata
                and existing["deleted_at"] is None
            )
            if unchanged:
                return {
                    "status": "unchanged",
                    "uri": uri,
                    "id": str(existing["id"]),
                    "namespace": namespace,
                    "scope": scope,
                }

            connection.execute(
                """
                UPDATE memories
                SET title = ?, content = ?, memory_type = ?, scope = ?, namespace = ?, author_id = ?, author_username = ?,
                    tags = ?, metadata = ?, content_hash = ?, deleted_at = NULL, updated_at = ?, approval_status = 'approved',
                    proposed_memory_type = NULL, proposed_by = NULL, proposed_by_username = NULL, proposed_at = NULL,
                    proposal_note = NULL, reviewed_by = NULL, reviewed_by_username = NULL, reviewed_at = NULL, review_note = NULL
                WHERE uri = ?
                """,
                (
                    title,
                    content,
                    memory_type,
                    scope,
                    namespace,
                    author_id,
                    author_username,
                    serialized_tags,
                    serialized_metadata,
                    content_hash,
                    now,
                    uri,
                ),
            )
            memory_id = str(existing["id"])
            status = "updated"
            old_content = existing["content"]
        else:
            memory_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO memories (
                    id, uri, title, content, memory_type, scope, namespace, author_id, author_username,
                    tags, metadata, content_hash, vitality_score, retrieval_count, last_accessed, deleted_at,
                    created_at, updated_at, approval_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 0, NULL, NULL, ?, ?, 'approved')
                """,
                (
                    memory_id,
                    uri,
                    title,
                    content,
                    memory_type,
                    scope,
                    namespace,
                    author_id,
                    author_username,
                    serialized_tags,
                    serialized_metadata,
                    content_hash,
                    now,
                    now,
                ),
            )
            status = "created"
            old_content = None

        self._sync_managed_memory_targets(connection, memory_id=memory_id, metadata=normalized_metadata)
        connection.execute(
            """
            INSERT INTO audit_log (timestamp, actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                author_id,
                author_username,
                "save_memory",
                memory_id,
                uri,
                old_content,
                content,
                json.dumps({"memory_type": memory_type, "scope": scope}, ensure_ascii=False),
            ),
        )
        connection.commit()
        return {
            "status": status,
            "uri": uri,
            "id": memory_id,
            "namespace": namespace,
            "scope": scope,
        }

    async def forget_memory(
        self,
        *,
        uri: str,
        reason: str,
        actor_id: str,
        actor_username: str,
    ) -> dict[str, Any]:
        await self.connect()
        connection = self._require_connection()
        row = connection.execute("SELECT * FROM memories WHERE uri = ?", (uri,)).fetchone()
        if row is None:
            raise ValueError(f"Memory not found: {uri}")
        if row["deleted_at"] is not None:
            return {"status": "already_forgotten", "uri": uri}
        now = self._now()
        connection.execute("UPDATE memories SET deleted_at = ?, updated_at = ? WHERE uri = ?", (now, now, uri))
        connection.execute(
            """
            INSERT INTO audit_log (timestamp, actor_id, actor_username, action, memory_id, uri, old_content, new_content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                now,
                actor_id,
                actor_username,
                "forget_memory",
                str(row["id"]),
                uri,
                row["content"],
                json.dumps({"reason": reason}, ensure_ascii=False),
            ),
        )
        connection.commit()
        return {"status": "forgotten", "uri": uri}

    async def export_viewer_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        await self.connect()
        connection = self._require_connection()
        return {
            "memories": [self._serialize_memory_row(row, include_content=True) for row in connection.execute("SELECT * FROM memories ORDER BY updated_at DESC").fetchall()],
            "sessions": [self._serialize_row(row) for row in connection.execute("SELECT * FROM sessions ORDER BY COALESCE(ended_at, started_at) DESC").fetchall()],
            "audit_log": [self._serialize_audit_row(row) for row in connection.execute("SELECT * FROM audit_log ORDER BY timestamp DESC").fetchall()],
            "team_members": [self._serialize_member(row) for row in connection.execute("SELECT * FROM team_members ORDER BY username").fetchall()],
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
        rows = self._require_connection().execute(
            "SELECT * FROM memories ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (sample_size,),
        ).fetchall()
        sample_full = [self._serialize_memory_row(row, include_content=True) for row in rows]
        sample_lean = [self._serialize_memory_row(row, include_content=False) for row in rows]
        full_boot_metrics = PostgresStorage._measure_payload(boot_full)
        hybrid_boot_metrics = PostgresStorage._measure_payload(boot_hybrid)
        full_sample_metrics = PostgresStorage._measure_payload(sample_full)
        lean_sample_metrics = PostgresStorage._measure_payload(sample_lean)
        return {
            "boot": {
                "limit": boot_limit,
                "full_content_limit": boot_full_content_limit,
                "full": full_boot_metrics,
                "hybrid": hybrid_boot_metrics,
                "savings": PostgresStorage._measure_payload_savings(full_boot_metrics, hybrid_boot_metrics),
            },
            "sample": {
                "size": len(rows),
                "full": full_sample_metrics,
                "lean": lean_sample_metrics,
                "savings": PostgresStorage._measure_payload_savings(full_sample_metrics, lean_sample_metrics),
            },
        }

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLite connection is not initialized")
        return self._connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialize_row(row: sqlite3.Row) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    def _serialize_member(self, row: sqlite3.Row) -> dict[str, Any]:
        serialized = self._serialize_row(row)
        serialized["is_active"] = bool(serialized.get("is_active"))
        return serialized

    def _serialize_project_member(self, row: sqlite3.Row) -> dict[str, Any]:
        serialized = self._serialize_row(row)
        serialized["is_active"] = bool(serialized.get("is_active"))
        return serialized

    def _serialize_audit_row(self, row: sqlite3.Row) -> dict[str, Any]:
        serialized = self._serialize_row(row)
        serialized["metadata"] = self._loads_json(serialized.get("metadata"), {})
        return serialized

    def _serialize_memory_row(self, row: sqlite3.Row, *, include_content: bool) -> dict[str, Any]:
        serialized = self._serialize_row(row)
        serialized["metadata"] = self._loads_json(serialized.get("metadata"), {})
        serialized["tags"] = self._loads_json(serialized.get("tags"), [])
        serialized["retrieval_count"] = int(serialized.get("retrieval_count") or 0)
        serialized["vitality_score"] = float(serialized.get("vitality_score") or 1.0)
        return PostgresStorage._finalize_memory_payload(serialized, include_content=include_content)

    @staticmethod
    def _loads_json(raw_value: Any, fallback: Any) -> Any:
        if raw_value in (None, ""):
            return fallback
        if isinstance(raw_value, (dict, list)):
            return raw_value
        try:
            return json.loads(str(raw_value))
        except json.JSONDecodeError:
            return fallback

    def _sync_managed_memory_targets(self, connection: sqlite3.Connection, *, memory_id: str, metadata: dict[str, Any]) -> None:
        connection.execute("DELETE FROM managed_memory_targets WHERE memory_id = ?", (memory_id,))
        documentation_scope = str(metadata.get("documentation_scope") or "").strip().lower()
        applicable_projects = metadata.get("applicable_projects") if isinstance(metadata.get("applicable_projects"), list) else []
        now = self._now()
        if documentation_scope == "global":
            connection.execute(
                "INSERT INTO managed_memory_targets (id, memory_id, target_type, target_value, created_at) VALUES (?, ?, 'global', '*', ?)",
                (str(uuid4()), memory_id, now),
            )
        for project in applicable_projects:
            project_name = str(project or "").strip()
            if not project_name:
                continue
            connection.execute(
                "INSERT INTO managed_memory_targets (id, memory_id, target_type, target_value, created_at) VALUES (?, ?, 'project', ?, ?)",
                (str(uuid4()), memory_id, project_name, now),
            )

    def _matches_boot_scope(self, row: sqlite3.Row, *, username: str, project: str | None) -> bool:
        uri = str(row["uri"])
        return (
            uri.startswith("system://")
            or uri.startswith("team://conventions/")
            or (project is not None and uri.startswith(f"project://{project}/"))
            or uri.startswith(f"personal://{username}/")
        )

    def _matches_search_scope(self, row: sqlite3.Row, *, username: str, team: str, project: str | None) -> bool:
        scope = str(row["scope"])
        namespace = str(row["namespace"])
        if scope == "personal":
            return namespace == f"personal://{username}"
        if scope == "project":
            return project is not None and namespace == f"project://{project}"
        if scope == "team":
            return namespace == f"team://{team}"
        return True

    def _matches_viewer_filters(self, row: sqlite3.Row, *, team: str | None, project: str | None) -> bool:
        namespace = str(row["namespace"])
        if team is not None and namespace.startswith("team://") and namespace != f"team://{team}":
            return False
        if project is not None and namespace.startswith("project://") and namespace != f"project://{project}":
            return False
        return True

    @staticmethod
    def _cursor_is_after(payload: dict[str, Any], cursor: dict[str, Any]) -> bool:
        payload_key = (
            float(payload.get("relevance") or 0),
            str(payload.get("updated_at") or ""),
            str(payload.get("id") or ""),
        )
        cursor_key = (
            float(cursor.get("relevance") or 0),
            str(cursor.get("updated_at") or ""),
            str(cursor.get("id") or ""),
        )
        return payload_key < cursor_key

    def _score_memory(self, row: sqlite3.Row, *, terms: list[str], normalized_query: str) -> float:
        payload = self._serialize_memory_row(row, include_content=True)
        haystacks = [
            PostgresStorage._normalize_search_text(str(payload.get("uri") or "")),
            PostgresStorage._normalize_search_text(str(payload.get("title") or "")),
            PostgresStorage._normalize_search_text(str(payload.get("content") or "")),
            PostgresStorage._normalize_search_text(" ".join(str(tag) for tag in payload.get("tags", []))),
            PostgresStorage._normalize_search_text(json.dumps(payload.get("metadata", {}), ensure_ascii=False)),
        ]
        score = 0.0
        if not normalized_query and not terms:
            return 1.0
        if normalized_query:
            if normalized_query in haystacks[1]:
                score += 3.0
            if normalized_query in haystacks[2]:
                score += 2.0
            if normalized_query in haystacks[0]:
                score += 1.5
        for term in terms:
            if term in haystacks[1]:
                score += 1.2
            if term in haystacks[2]:
                score += 1.0
            if term in haystacks[0]:
                score += 0.8
            if term in haystacks[3] or term in haystacks[4]:
                score += 0.6
        return score