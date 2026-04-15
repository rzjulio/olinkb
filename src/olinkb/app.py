from __future__ import annotations

from typing import Any
from uuid import UUID

from olinkb.config import Settings, get_settings
from olinkb.automation import analyze_memory_candidate
from olinkb.domain import (
    APPROVER_MEMBER_ROLES,
    enrich_memory_tags,
    extract_scope_key,
    infer_scope_from_uri,
    parse_tags,
    validate_memory_type,
    validate_scope,
    validate_uri_matches_scope,
)
from olinkb.session import SessionManager
from olinkb.storage import PostgresStorage, ReadCache, SqliteStorage


SESSION_SUMMARY_MEMORY_TAGS = ["session-summary", "end_session", "sessions"]
BOOT_FULL_CONTENT_LIMIT = 5
WRITER_MEMBER_ROLES = {"admin", "lead", "developer"}
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
        if self.settings.storage_backend == "sqlite":
            self.storage = SqliteStorage(self.settings.sqlite_path)
        else:
            self.storage = PostgresStorage(
                self.settings.pg_url,
                pool_max_size=self.settings.pg_pool_max_size,
            )
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
        self.sessions.start(session_id=session_id, author=username, team=team_name, project=project_name)

        project_member = None
        if project_name:
            project_member = await self.storage.ensure_project_member(
                member_id=member["id"],
                username=username,
                project=project_name,
                team=team_name,
                default_role=member.get("role", "developer"),
            )

        cache_key = self._boot_cache_key(username, project_name)
        memories = self.cache.get(cache_key)
        if memories is None:
            memories = await self.storage.load_boot_memories(
                username=username,
                project=project_name,
                full_content_limit=BOOT_FULL_CONTENT_LIMIT,
            )
            self.cache.set(cache_key, memories)

        review_queue = {"total_count": 0, "proposals": []}
        effective_role = (project_member or member).get("role") if (project_member or member) else None
        if project_name and effective_role in APPROVER_MEMBER_ROLES:
            review_queue = await self.storage.load_pending_proposals(project=project_name, limit=5)

        return {
            "session_id": session_id,
            "author": username,
            "team": member["team"],
            "project": project_name,
            "loaded_count": len(memories),
            "memories": memories,
            "review_queue": review_queue,
        }

    async def remember(
        self,
        query: str,
        scope: str = "all",
        limit: int = 5,
        session_id: str | None = None,
        include_content: bool = False,
    ) -> list[dict[str, Any]]:
        username, team_name, project_name = self._remember_context(session_id, scope)
        cache_key = self._remember_cache_key(
            query,
            scope,
            limit,
            username,
            team_name,
            project_name,
            include_content,
        )
        results = self.cache.get(cache_key)
        if results is None:
            memory_results = await self.storage.search_memories(
                query=query,
                scope=scope,
                limit=limit,
                include_content=include_content,
                username=username,
                team=team_name,
                project=project_name,
            )
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

    async def analyze_memory(
        self,
        *,
        content: str,
        title: str | None = None,
        project: str | None = None,
        scope_hint: str | None = None,
        memory_type_hint: str | None = None,
        tags: str = "",
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        author: str | None = None,
        source_surface: str = "cli",
        files: list[str] | None = None,
        commands: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_project = project or self._session_project(session_id) or self.settings.default_project
        effective_author = author or self.settings.user
        return analyze_memory_candidate(
            content=content,
            title=title,
            project=effective_project,
            scope_hint=scope_hint,
            memory_type_hint=memory_type_hint,
            tags=tags,
            metadata=metadata,
            source_surface=source_surface,
            files=files,
            commands=commands,
            author=effective_author,
        )

    async def capture_memory(
        self,
        *,
        content: str,
        title: str | None = None,
        project: str | None = None,
        scope_hint: str | None = None,
        memory_type_hint: str | None = None,
        tags: str = "",
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        author: str | None = None,
        source_surface: str = "cli",
        files: list[str] | None = None,
        commands: list[str] | None = None,
        auto_save: bool = True,
    ) -> dict[str, Any]:
        analysis = await self.analyze_memory(
            content=content,
            title=title,
            project=project,
            scope_hint=scope_hint,
            memory_type_hint=memory_type_hint,
            tags=tags,
            metadata=metadata,
            session_id=session_id,
            author=author,
            source_surface=source_surface,
            files=files,
            commands=commands,
        )
        analysis["saved"] = False

        if not auto_save or analysis["action"] != "save":
            return analysis

        try:
            result = await self.save_memory(
                uri=analysis["suggested_uri"],
                title=analysis["suggested_title"],
                content=content,
                memory_type=analysis["suggested_memory_type"],
                scope=analysis["suggested_scope"],
                tags=",".join(analysis["suggested_tags"]),
                metadata=analysis["metadata"],
                session_id=session_id,
                author=author,
            )
        except PermissionError as exc:
            analysis["action"] = "suggest"
            analysis.setdefault("reasons", []).append(str(exc))
            return analysis

        analysis["saved"] = result.get("status") in {"create", "created", "update", "updated", "unchanged"}
        analysis["memory"] = result
        return analysis

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
        project_member = await self._project_member_for_uri(uri=uri, member=member, username=username)
        self._authorize_memory_write(scope=scope, memory_type=memory_type, username=username, uri=uri, member=member, project_member=project_member)
        resolved_tags = enrich_memory_tags(memory_type, parse_tags(tags), metadata)
        result = await self.storage.save_memory(
            uri=uri,
            title=title,
            content=content,
            memory_type=memory_type,
            scope=scope,
            tags=resolved_tags,
            metadata=metadata,
            author_id=member["id"],
            author_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id and result["status"] != "unchanged":
            self.sessions.bump_writes(session_id)
        return result

    async def propose_memory_promotion(
        self,
        *,
        uri: str,
        rationale: str,
        target_memory_type: str = "convention",
        session_id: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        normalized_target_type = self._normalize_target_memory_type(target_memory_type)
        username = author or self.settings.user
        member = await self.storage.ensure_member(username=username, team=self.settings.team)
        scope = infer_scope_from_uri(uri)
        if scope != "project":
            raise ValueError("Only project memories can be proposed for promotion")

        project_member = await self.storage.ensure_project_member(
            member_id=member["id"],
            username=username,
            project=extract_scope_key(uri),
            team=member["team"],
            default_role=member.get("role", "developer"),
        )
        if project_member.get("role") not in WRITER_MEMBER_ROLES:
            raise PermissionError("Only project contributors can propose a convention or standard")

        result = await self.storage.propose_memory_promotion(
            uri=uri,
            proposed_memory_type=normalized_target_type,
            rationale=rationale,
            actor_id=member["id"],
            actor_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id:
            self.sessions.bump_writes(session_id)
        return result

    async def list_pending_approvals(
        self,
        *,
        project: str | None = None,
        limit: int = 10,
        author: str | None = None,
    ) -> dict[str, Any]:
        username = author or self.settings.user
        member = await self.storage.ensure_member(username=username, team=self.settings.team)
        project_name = project or self.settings.default_project
        if not project_name:
            raise ValueError("A project is required to list pending approvals")
        project_member = await self.storage.ensure_project_member(
            member_id=member["id"],
            username=username,
            project=project_name,
            team=member["team"],
            default_role=member.get("role", "developer"),
        )
        self._authorize_project_review(project_name=project_name, project_member=project_member)
        return await self.storage.load_pending_proposals(project=project_name, limit=limit)

    async def review_memory_proposal(
        self,
        *,
        uri: str,
        action: str,
        note: str = "",
        session_id: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        username = author or self.settings.user
        member = await self.storage.ensure_member(username=username, team=self.settings.team)
        scope = infer_scope_from_uri(uri)
        if scope != "project":
            raise ValueError("Only project memories can be reviewed through the approval queue")
        project_name = extract_scope_key(uri)
        project_member = await self.storage.ensure_project_member(
            member_id=member["id"],
            username=username,
            project=project_name,
            team=member["team"],
            default_role=member.get("role", "developer"),
        )
        self._authorize_project_review(project_name=project_name, project_member=project_member)
        result = await self.storage.review_memory_proposal(
            uri=uri,
            action=action,
            note=note,
            reviewer_id=member["id"],
            reviewer_username=username,
        )
        self.cache.invalidate_prefix(self._boot_cache_prefix(username))
        self.cache.invalidate_prefix("remember:")
        if session_id:
            self.sessions.bump_writes(session_id)
        return result

    async def end_session(self, session_id: str, summary: str) -> dict[str, Any]:
        normalized_session_id, is_valid_session_id = self._normalize_session_id(session_id)
        lookup_session_id = normalized_session_id or session_id.strip()

        active_session = self.sessions.get(lookup_session_id)
        if active_session is not None:
            summary_saved = await self._persist_session_summary_memory(
                session_id=lookup_session_id,
                summary=summary,
                author=active_session.author,
                project=active_session.project,
            )
            if summary_saved:
                self.sessions.bump_writes(lookup_session_id)
            session = self.sessions.end(lookup_session_id)
            await self.storage.end_session(
                session_id=lookup_session_id,
                summary=summary,
                memories_read=session.memories_read,
                memories_written=session.memories_written,
            )
            return {
                "session_id": lookup_session_id,
                "author": session.author,
                "project": session.project,
                "memories_read": session.memories_read,
                "memories_written": session.memories_written,
                "summary": summary,
            }

        if not is_valid_session_id:
            raise ValueError(self._invalid_session_id_message(session_id))

        stored_session = await self.storage.get_session(lookup_session_id)
        if stored_session is None:
            raise ValueError(self._unknown_session_id_message(lookup_session_id))

        if stored_session["ended_at"] is None:
            summary_saved = await self._persist_session_summary_memory(
                session_id=lookup_session_id,
                summary=summary,
                author=stored_session["author_username"],
                project=stored_session["project"],
            )
            memories_written = stored_session["memories_written"] + (1 if summary_saved else 0)
            await self.storage.end_session(
                session_id=lookup_session_id,
                summary=summary,
                memories_read=stored_session["memories_read"],
                memories_written=memories_written,
            )
            return {
                "session_id": lookup_session_id,
                "author": stored_session["author_username"],
                "project": stored_session["project"],
                "memories_read": stored_session["memories_read"],
                "memories_written": memories_written,
                "summary": summary,
                "status": "recovered",
            }

        return {
            "session_id": lookup_session_id,
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
        project_member = await self._project_member_for_uri(uri=uri, member=member, username=username)
        self._authorize_forget(uri=uri, username=username, member=member, project_member=project_member)
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

    def _remember_context(self, session_id: str | None, scope: str) -> tuple[str, str, str | None]:
        username = self.settings.user
        team_name = self.settings.team
        project_name = self.settings.default_project if scope in {"all", "project"} else None
        if session_id:
            session = self.sessions.get(session_id)
            if session is not None:
                username = session.author
                team_name = session.team
                if scope in {"all", "project"}:
                    project_name = session.project
        return username, team_name, project_name

    def _session_project(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        session = self.sessions.get(session_id)
        if session is None:
            return None
        return session.project

    @staticmethod
    def _remember_cache_key(
        query: str,
        scope: str,
        limit: int,
        username: str,
        team: str,
        project: str | None,
        include_content: bool,
    ) -> str:
        return (
            f"remember:{scope}:{username}:{team}:{project or '-'}:{limit}:"
            f"{int(include_content)}:{query.strip().lower()}"
        )

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

    async def _project_member_for_uri(
        self,
        *,
        uri: str,
        member: dict[str, Any],
        username: str,
    ) -> dict[str, Any] | None:
        if infer_scope_from_uri(uri) != "project":
            return None
        return await self.storage.ensure_project_member(
            member_id=member["id"],
            username=username,
            project=extract_scope_key(uri),
            team=member["team"],
            default_role=member.get("role", "developer"),
        )

    @staticmethod
    def _normalize_target_memory_type(target_memory_type: str) -> str:
        normalized = target_memory_type.strip().lower()
        if normalized == "standard":
            normalized = "convention"
        validate_memory_type(normalized)
        if normalized != "convention":
            raise ValueError("Only promotion to convention or standard is supported")
        return normalized

    @staticmethod
    def _authorize_project_review(*, project_name: str, project_member: dict[str, Any]) -> None:
        if project_member.get("role") not in APPROVER_MEMBER_ROLES:
            raise PermissionError(f"Only project leads or admins can review pending conventions for {project_name}")

    @staticmethod
    def _authorize_memory_write(
        *,
        scope: str,
        memory_type: str,
        username: str,
        uri: str,
        member: dict[str, Any],
        project_member: dict[str, Any] | None,
    ) -> None:
        role = member.get("role", "developer")
        if scope == "project":
            project_role = (project_member or {}).get("role", role)
            if project_role not in WRITER_MEMBER_ROLES:
                raise PermissionError(f"Only project contributors can save memories for {extract_scope_key(uri)}")
            if memory_type == "business_documentation" and project_role != "admin":
                raise PermissionError("Only admins can save business documentation")
            if memory_type == "convention" and project_role not in APPROVER_MEMBER_ROLES:
                raise PermissionError(
                    "Only project leads or admins can save conventions directly. Save the memory first and then explicitly call propose_memory_promotion(...) if it should be reviewed as a convention."
                )
            return

        if scope == "personal":
            if extract_scope_key(uri) != username:
                raise PermissionError("You can only write your own personal memories")
            return

        if memory_type == "business_documentation" and role != "admin":
            raise PermissionError("Only admins can save business documentation")
        if role not in APPROVER_MEMBER_ROLES:
            raise PermissionError(f"Only leads or admins can write {scope}-scope memories")

    def _authorize_forget(
        self,
        *,
        uri: str,
        username: str,
        member: dict[str, Any],
        project_member: dict[str, Any] | None,
    ) -> None:
        scope = infer_scope_from_uri(uri)
        if scope == "personal":
            if extract_scope_key(uri) != username:
                raise PermissionError("You can only forget your own personal memories")
            return
        if scope == "project":
            project_role = (project_member or {}).get("role", member.get("role", "developer"))
            if project_role not in APPROVER_MEMBER_ROLES:
                raise PermissionError(
                    f"Only project leads or admins can forget memories for {extract_scope_key(uri)}"
                )
            return
        if member.get("role") not in APPROVER_MEMBER_ROLES:
            raise PermissionError(f"Only leads or admins can forget {scope}-scope memories")

    @staticmethod
    def _normalize_session_id(session_id: str) -> tuple[str | None, bool]:
        candidate = session_id.strip()
        if not candidate:
            return None, False
        try:
            return str(UUID(candidate)), True
        except (ValueError, AttributeError, TypeError):
            return candidate, False

    def _invalid_session_id_message(self, session_id: str) -> str:
        message = (
            f"Invalid session_id format: {session_id}. "
            "Use the exact UUID returned by boot_session()."
        )
        active_session_ids = self.sessions.active_session_ids()
        if len(active_session_ids) == 1:
            message += (
                f" A different active session_id is currently open in this process: {active_session_ids[0]}."
            )
        elif active_session_ids:
            preview = ", ".join(active_session_ids[:3])
            suffix = "..." if len(active_session_ids) > 3 else ""
            message += f" Active session_ids currently open in this process: {preview}{suffix}."
        return message

    def _unknown_session_id_message(self, session_id: str) -> str:
        message = (
            f"Unknown session_id: {session_id}. "
            "The session is not active in this process and no persisted session row was found; "
            "it may be stale, already cleaned up, or from a different OlinKB environment."
        )
        active_session_ids = self.sessions.active_session_ids()
        if len(active_session_ids) == 1:
            message += (
                f" A different active session_id is currently open in this process: {active_session_ids[0]}."
            )
        elif active_session_ids:
            preview = ", ".join(active_session_ids[:3])
            suffix = "..." if len(active_session_ids) > 3 else ""
            message += f" Active session_ids currently open in this process: {preview}{suffix}."
        return message
