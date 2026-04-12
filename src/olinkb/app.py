from __future__ import annotations

from typing import Any

from olinkb.config import Settings, get_settings
from olinkb.domain import parse_tags, validate_memory_type, validate_scope, validate_uri_matches_scope
from olinkb.session import SessionManager
from olinkb.storage import PostgresStorage, ReadCache


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
        cache_key = self._remember_cache_key(query, scope, limit)
        results = self.cache.get(cache_key)
        if results is None:
            results = await self.storage.search_memories(query=query, scope=scope, limit=limit)
            self.cache.set(cache_key, results)

        memory_ids = [result["id"] for result in results if "id" in result]
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
            author_id=member["id"],
            author_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id and result["status"] != "unchanged":
            self.sessions.bump_writes(session_id)
        return result

    async def end_session(self, session_id: str, summary: str) -> dict[str, Any]:
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

    @staticmethod
    def _remember_cache_key(query: str, scope: str, limit: int) -> str:
        return f"remember:{scope}:{limit}:{query.strip().lower()}"
