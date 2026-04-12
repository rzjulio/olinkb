from __future__ import annotations

from typing import Any

from olinkb.config import Settings, get_settings
from olinkb.domain import parse_tags, validate_memory_type, validate_scope, validate_uri_matches_scope
from olinkb.session import SessionManager
from olinkb.storage import PostgresStorage, ReadCache


SESSION_SUMMARY_MEMORY_TAGS = ["session-summary", "end_session", "sessions"]
SESSION_SUMMARY_HEADING_MARKERS = (
    "goal:",
    "instructions:",
    "discoveries:",
    "accomplished:",
    "next steps:",
    "what:",
    "why:",
    "where:",
    "learned:",
    "context:",
    "decision:",
    "evidence:",
)


class OlinKBApp:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.storage = PostgresStorage(self.settings.pg_url)
        self.cache = ReadCache(
            max_size=self.settings.cache_max_entries,
            ttl_seconds=self.settings.cache_ttl_seconds,
        )
        self.sessions = SessionManager()

    async def boot_session(
        self,
        author: str | None = None,
        team: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        username = author or self.settings.user
        team_name = team or self.settings.team
        project_name = project or self.settings.default_project
        member = await self.storage.ensure_member(username=username, team=team_name)
        session_id = await self.storage.start_session(
            author_id=member["id"],
            author_username=username,
            project=project_name,
        )
        self.sessions.start(session_id=session_id, author=username, project=project_name)

        cache_key = self._boot_cache_key(username, project_name)
        memories = self.cache.get(cache_key)
        if memories is None:
            memories = await self.storage.load_boot_memories(username=username, project=project_name)
            self.cache.set(cache_key, memories)

        return {
            "session_id": session_id,
            "author": username,
            "team": member["team"],
            "project": project_name,
            "loaded_count": len(memories),
            "memories": memories,
        }

    async def remember(
        self,
        query: str,
        scope: str = "all",
        limit: int = 5,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        project_name = self._remember_project_name(session_id, scope)
        cache_key = self._remember_cache_key(query, scope, limit, project_name)
        results = self.cache.get(cache_key)
        if results is None:
            memory_results = await self.storage.search_memories(query=query, scope=scope, limit=limit)
            session_results: list[dict[str, Any]] = []
            if scope in {"all", "project"}:
                session_results = await self.storage.search_session_summaries(
                    query=query,
                    limit=limit,
                    project=project_name,
                )
            results = self._merge_remember_results(memory_results, session_results, limit)
            self.cache.set(cache_key, results)

        memory_ids = [
            result["id"]
            for result in results
            if result.get("result_type", "memory") == "memory" and "id" in result
        ]
        await self.storage.touch_memories(memory_ids)
        if session_id:
            self.sessions.bump_reads(session_id, len(results))
        return results

    async def save_memory(
        self,
        *,
        uri: str,
        title: str,
        content: str,
        memory_type: str,
        scope: str = "personal",
        tags: str = "",
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        validate_scope(scope)
        validate_memory_type(memory_type)
        validate_uri_matches_scope(uri, scope)

        username = author or self.settings.user
        member = await self.storage.ensure_member(username=username, team=self.settings.team)
        result = await self.storage.save_memory(
            uri=uri,
            title=title,
            content=content,
            memory_type=memory_type,
            scope=scope,
            tags=parse_tags(tags),
            metadata=metadata,
            author_id=member["id"],
            author_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id and result["status"] != "unchanged":
            self.sessions.bump_writes(session_id)
        return result

    async def end_session(self, session_id: str, summary: str) -> dict[str, Any]:
        active_session = self.sessions.get(session_id)
        if active_session is not None:
            summary_saved = await self._persist_session_summary_memory(
                session_id=session_id,
                summary=summary,
                author=active_session.author,
                project=active_session.project,
            )
            if summary_saved:
                self.sessions.bump_writes(session_id)
            session = self.sessions.end(session_id)
            await self.storage.end_session(
                session_id=session_id,
                summary=summary,
                memories_read=session.memories_read,
                memories_written=session.memories_written,
            )
            return {
                "session_id": session_id,
                "author": session.author,
                "project": session.project,
                "memories_read": session.memories_read,
                "memories_written": session.memories_written,
                "summary": summary,
            }

        stored_session = await self.storage.get_session(session_id)
        if stored_session is None:
            raise ValueError(f"Unknown session_id: {session_id}")

        if stored_session["ended_at"] is None:
            summary_saved = await self._persist_session_summary_memory(
                session_id=session_id,
                summary=summary,
                author=stored_session["author_username"],
                project=stored_session["project"],
            )
            memories_written = stored_session["memories_written"] + (1 if summary_saved else 0)
            await self.storage.end_session(
                session_id=session_id,
                summary=summary,
                memories_read=stored_session["memories_read"],
                memories_written=memories_written,
            )
            return {
                "session_id": session_id,
                "author": stored_session["author_username"],
                "project": stored_session["project"],
                "memories_read": stored_session["memories_read"],
                "memories_written": memories_written,
                "summary": summary,
                "status": "recovered",
            }

        return {
            "session_id": session_id,
            "author": stored_session["author_username"],
            "project": stored_session["project"],
            "memories_read": stored_session["memories_read"],
            "memories_written": stored_session["memories_written"],
            "summary": stored_session["summary"] or summary,
            "status": "already_ended",
        }

    async def forget(
        self,
        uri: str,
        reason: str,
        session_id: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        username = author or self.settings.user
        member = await self.storage.ensure_member(username=username, team=self.settings.team)
        result = await self.storage.forget_memory(
            uri=uri,
            reason=reason,
            actor_id=member["id"],
            actor_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id and result["status"] == "forgotten":
            self.sessions.bump_writes(session_id)
        return result

    @staticmethod
    def _boot_cache_key(author: str, project: str | None) -> str:
        return f"boot:{author}:{project or '-'}"

    @staticmethod
    def _boot_cache_prefix(author: str) -> str:
        return f"boot:{author}:"

    def _remember_project_name(self, session_id: str | None, scope: str) -> str | None:
        if scope not in {"all", "project"}:
            return None
        if session_id:
            session = self.sessions.get(session_id)
            if session is not None:
                return session.project
        return self.settings.default_project

    @staticmethod
    def _remember_cache_key(query: str, scope: str, limit: int, project: str | None) -> str:
        return f"remember:{scope}:{project or '-'}:{limit}:{query.strip().lower()}"

    @staticmethod
    def _merge_remember_results(
        memory_results: list[dict[str, Any]],
        session_results: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for result in [*memory_results, *session_results]:
            key = ("uri", result["uri"]) if result.get("uri") else ("session", result.get("session_id"), result.get("title"))
            existing = merged.get(key)
            if existing is None:
                merged[key] = result
                continue

            existing_type = existing.get("result_type", "memory")
            result_type = result.get("result_type", "memory")
            if existing_type != "memory" and result_type == "memory":
                merged[key] = result
                continue

            if result.get("relevance", 0) > existing.get("relevance", 0):
                merged[key] = result

        ordered = sorted(
            merged.values(),
            key=lambda item: (
                item.get("relevance", 0),
                item.get("retrieval_count", 0),
                item.get("updated_at") or item.get("ended_at") or "",
            ),
            reverse=True,
        )
        return ordered[:limit]

    async def _persist_session_summary_memory(
        self,
        *,
        session_id: str,
        summary: str,
        author: str,
        project: str | None,
    ) -> bool:
        if not project or not self._should_promote_session_summary(summary):
            return False

        result = await self.save_memory(
            uri=f"project://{project}/sessions/{session_id}",
            title=f"Session summary {project} {session_id[:8]}",
            content=summary,
            memory_type="event",
            scope="project",
            tags=SESSION_SUMMARY_MEMORY_TAGS,
            author=author,
        )
        return result["status"] != "unchanged"

    @staticmethod
    def _should_promote_session_summary(summary: str) -> bool:
        stripped = summary.strip()
        if not stripped:
            return False
        lowered = stripped.lower()
        if any(marker in lowered for marker in SESSION_SUMMARY_HEADING_MARKERS):
            return True
        return len(stripped.split()) >= 30
