from __future__ import annotations

import asyncio
import base64
import json
import re
import secrets
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from olinkb.app import OlinKBApp
from olinkb.config import Settings, get_viewer_settings
from olinkb.domain import APPROVER_MEMBER_ROLES, is_managed_memory_type
from olinkb.storage.postgres import PostgresStorage
from olinkb.viewer import build_empty_viewer_payload, build_viewer_payload, render_viewer_html


DEFAULT_VIEWER_PAGE_SIZE = 50
MAX_VIEWER_PAGE_SIZE = 100
MAX_VIEWER_QUERY_LENGTH = 200
TITLE_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
VIEWER_SESSION_COOKIE = "olinkb_viewer_session"
VIEWER_LOGIN_ACCOUNTS = {
    "admin": {
        "password": "admin",
        "role": "admin",
        "display_name": "Viewer Admin",
    }
}
VIEWER_ALLOWED_DOCUMENTATION_TYPES = {"documentation", "business_documentation"}
VIEWER_FALLBACK_TEAM = "viewer"


class ViewerAuthenticationError(PermissionError):
    pass


class ViewerAuthorizationError(PermissionError):
    pass


class _LiveViewerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], title: str) -> None:
        super().__init__(server_address, _LiveViewerRequestHandler)
        self.title = title
        self.settings = get_viewer_settings()
        self.auth_sessions: dict[str, dict[str, Any]] = {}
        self.index_html = render_viewer_html(
            build_empty_viewer_payload(),
            title=title,
            live_api_path="/api/viewer",
        ).encode("utf-8")

    def create_auth_session(self, payload: dict[str, Any]) -> str:
        session_id = secrets.token_urlsafe(24)
        self.auth_sessions[session_id] = payload
        return session_id

    def get_auth_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        session = self.auth_sessions.get(session_id)
        if session is None:
            return None
        return dict(session)

    def clear_auth_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        self.auth_sessions.pop(session_id, None)


class _LiveViewerRequestHandler(BaseHTTPRequestHandler):
    server: _LiveViewerHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(self.server.index_html)
            return

        if parsed.path == "/api/auth/session":
            self._send_json(_build_viewer_auth_payload(self._get_viewer_session()))
            return

        if parsed.path == "/api/viewer":
            try:
                payload = asyncio.run(
                    _load_viewer_payload(
                        self.server.settings.pg_url,
                        params=parse_qs(parsed.query),
                        username=self.server.settings.user or None,
                        team=self.server.settings.team or None,
                        project=self.server.settings.default_project,
                        pool_max_size=self.server.settings.pg_pool_max_size,
                    )
                )
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            self._send_json(payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/login":
            try:
                payload = self._read_json_body()
                login_payload = _normalize_login_payload(payload)
                session = asyncio.run(
                    _login_viewer_session(
                        self.server.settings.pg_url,
                        username=login_payload["username"],
                        password=login_payload["password"],
                        team=self.server.settings.team or None,
                        project=self.server.settings.default_project,
                        pool_max_size=self.server.settings.pg_pool_max_size,
                    )
                )
            except ViewerAuthenticationError as error:
                self.send_error(HTTPStatus.UNAUTHORIZED, str(error))
                return
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return

            session_id = self.server.create_auth_session(session)
            self._send_json(
                _build_viewer_auth_payload(session),
                headers={"Set-Cookie": _build_viewer_session_cookie(session_id)},
            )
            return

        if parsed.path == "/api/auth/logout":
            session_id = self._get_viewer_session_id()
            self.server.clear_auth_session(session_id)
            self._send_json(
                _build_viewer_auth_payload(None),
                headers={"Set-Cookie": _build_viewer_logout_cookie()},
            )
            return

        if parsed.path != "/api/memories":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        try:
            session = _authenticate_documentation_session(self._get_viewer_session())
            payload = self._read_json_body()
            result = asyncio.run(
                _create_memory_payload(
                    self.server.settings.pg_url,
                    payload=payload,
                    username=str(session["username"]),
                    role=str(session.get("role") or ""),
                    team=str(session.get("team") or self.server.settings.team or ""),
                    project=session.get("project") or self.server.settings.default_project,
                    pool_max_size=self.server.settings.pg_pool_max_size,
                )
            )
        except ViewerAuthenticationError as error:
            self.send_error(HTTPStatus.UNAUTHORIZED, str(error))
            return
        except ViewerAuthorizationError as error:
            self.send_error(HTTPStatus.FORBIDDEN, str(error))
            return
        except ValueError as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        self._send_json(result)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_headers("text/html; charset=utf-8", len(self.server.index_html))
            return

        if parsed.path == "/api/viewer":
            try:
                payload = asyncio.run(
                    _load_viewer_payload(
                        self.server.settings.pg_url,
                        params=parse_qs(parsed.query),
                        username=self.server.settings.user or None,
                        team=self.server.settings.team or None,
                        project=self.server.settings.default_project,
                        pool_max_size=self.server.settings.pg_pool_max_size,
                    )
                )
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_headers("application/json; charset=utf-8", len(body))
            return

        if parsed.path == "/api/auth/session":
            body = json.dumps(_build_viewer_auth_payload(self._get_viewer_session()), ensure_ascii=False).encode("utf-8")
            self._send_headers("application/json; charset=utf-8", len(body))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_html(self, body: bytes) -> None:
        self._send_headers("text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers("application/json; charset=utf-8", len(body), status=status, headers=headers)
        self.wfile.write(body)

    def _get_viewer_session_id(self) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        morsel = cookie.get(VIEWER_SESSION_COOKIE)
        if morsel is None:
            return None
        return morsel.value

    def _get_viewer_session(self) -> dict[str, Any] | None:
        return self.server.get_auth_session(self._get_viewer_session_id())

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length <= 0:
            raise ValueError("Request body must be valid JSON")
        try:
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _send_headers(
        self,
        content_type: str,
        content_length: int,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(content_length))
        for header_name, header_value in (headers or {}).items():
            self.send_header(header_name, header_value)
        self.end_headers()


async def _load_viewer_payload(
    pg_url: str,
    *,
    params: dict[str, list[str]],
    username: str | None,
    team: str | None,
    project: str | None,
    pool_max_size: int = 5,
) -> dict[str, Any]:
    storage = PostgresStorage(pg_url, pool_max_size=pool_max_size)
    await storage.connect()
    try:
        query = _sanitize_query(_first_param(params, "q"))
        raw_limit = _first_param(params, "limit")
        limit = _sanitize_limit(raw_limit)
        cursor = _decode_cursor(_first_param(params, "cursor"))
        search_team = _sanitize_optional_filter(_first_param(params, "team"))
        search_project = _sanitize_optional_filter(_first_param(params, "project"))
        is_default_landing_view = (
            not query
            and cursor is None
            and search_team is None
            and search_project is None
            and (raw_limit is None or limit == DEFAULT_VIEWER_PAGE_SIZE)
        )
        if is_default_landing_view:
            limit = max(1, await storage.count_viewer_memories(query="", team=None, project=None))

        page = await storage.search_viewer_memories(
            query=query,
            limit=limit,
            cursor=cursor,
            team=search_team,
            project=search_project,
        )
        author_usernames = sorted(
            {
                str(memory.get("author_username"))
                for memory in page["memories"]
                if memory.get("author_username")
            }
        )
        team_members = await storage.load_team_members(author_usernames)
        sessions = await storage.load_recent_sessions_for_authors(author_usernames)
        pending_approvals = {"enabled": False, "total_count": 0, "proposals": []}
        if username and project:
            project_member = await storage.get_project_member(username=username, project=project)
            if project_member and project_member.get("role") in APPROVER_MEMBER_ROLES:
                preview = await storage.load_pending_proposals(project=project, limit=5)
                pending_approvals = {
                    "enabled": True,
                    "total_count": preview["total_count"],
                    "proposals": preview["proposals"],
                }
                if preview["total_count"] > len(preview["proposals"]):
                    full_queue = await storage.load_pending_proposals(project=project, limit=preview["total_count"])
                    pending_approvals["proposals"] = full_queue["proposals"]
        payload = build_viewer_payload(
            memories=page["memories"],
            sessions=sessions,
            audit_log=[],
            team_members=team_members,
            pending_approvals=pending_approvals,
        )
        payload["pageInfo"] = {
            "query": page["page_info"]["query"],
            "has_next": page["page_info"]["has_next"],
            "next_cursor": _encode_cursor(page["page_info"]["next_cursor"]),
            "returned_count": page["page_info"]["returned_count"],
            "limit": limit,
        }
        return payload
    finally:
        await storage.close()


def _first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    if not values:
        return None
    return values[0]


def _sanitize_optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_login_payload(payload: dict[str, Any]) -> dict[str, str]:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not username:
        raise ValueError("username is required")
    if not password:
        raise ValueError("password is required")
    return {"username": username, "password": password}


def _build_viewer_auth_payload(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {
            "authenticated": False,
            "username": None,
            "role": None,
            "can_manage_documentation": False,
        }
    return {
        "authenticated": True,
        "username": session.get("username"),
        "role": session.get("role"),
        "can_manage_documentation": bool(session.get("role") in APPROVER_MEMBER_ROLES),
    }


def _authenticate_documentation_session(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        raise ViewerAuthenticationError("Please sign in to add documentation")
    if session.get("role") not in APPROVER_MEMBER_ROLES:
        raise ViewerAuthorizationError("Only admins or leads can add documentation")
    return session


def _build_viewer_session_cookie(session_id: str) -> str:
    return f"{VIEWER_SESSION_COOKIE}={session_id}; HttpOnly; Path=/; SameSite=Lax"


def _build_viewer_logout_cookie() -> str:
    return f"{VIEWER_SESSION_COOKIE}=; HttpOnly; Max-Age=0; Path=/; SameSite=Lax"


def _normalize_applicable_projects(raw_projects: Any) -> list[str]:
    if raw_projects is None:
        return []
    if not isinstance(raw_projects, list):
        raise ValueError("applicable_projects must be an array")

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_projects:
        project_name = str(value or "").strip()
        if not project_name or project_name in seen:
            continue
        seen.add(project_name)
        normalized.append(project_name)
    return normalized


def _normalize_create_memory_payload(
    payload: dict[str, Any],
    *,
    role: str | None,
    default_project: str | None,
    default_team: str | None,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    raw_content = str(payload.get("content") or "")
    content = raw_content.strip()
    memory_type = str(payload.get("memory_type") or "documentation").strip()
    target_scope = str(payload.get("target_scope") or "global").strip()
    file_name = str(payload.get("file_name") or "").strip()
    applicable_projects = _normalize_applicable_projects(payload.get("applicable_projects"))
    if not title:
        raise ValueError("title is required")
    if not content:
        raise ValueError("content is required")
    if not is_managed_memory_type(memory_type) or memory_type not in VIEWER_ALLOWED_DOCUMENTATION_TYPES:
        raise ValueError("documentation type must be documentation or business_documentation")
    if target_scope not in {"global", "repo"}:
        raise ValueError("target_scope must be global or repo")
    if memory_type == "business_documentation" and role != "admin":
        raise ViewerAuthorizationError("Only admins can add business documentation")
    if target_scope == "repo" and not applicable_projects:
        raise ValueError("Select at least one repo")

    scope = "org"
    scope_key = "shared"
    if target_scope == "repo" and len(applicable_projects) == 1:
        scope = "project"
        scope_key = applicable_projects[0]

    metadata = {
        "managed": True,
        "authoring_surface": "viewer",
        "content_format": "markdown",
        "documentation_scope": target_scope,
        "applicable_projects": applicable_projects,
    }
    if file_name:
        metadata["source_file_name"] = file_name

    return {
        "title": title,
        "content": raw_content,
        "memory_type": memory_type,
        "scope": scope,
        "scope_key": scope_key,
        "tags": "",
        "metadata": metadata,
    }


def _slugify_title(title: str) -> str:
    return TITLE_SLUG_PATTERN.sub("-", title.strip().lower()).strip("-") or "note"


def _build_memory_uri(*, scope: str, scope_key: str, title: str) -> str:
    slug = _slugify_title(title)
    if scope == "project":
        return f"project://{scope_key}/notes/{slug}"
    if scope == "team":
        return f"team://{scope_key}/notes/{slug}"
    if scope == "org":
        return f"org://{scope_key}/notes/{slug}"
    return f"system://{scope_key}/{slug}"


async def _create_memory_payload(
    pg_url: str,
    *,
    payload: dict[str, Any],
    username: str | None,
    role: str | None,
    team: str | None,
    project: str | None,
    pool_max_size: int = 5,
) -> dict[str, Any]:
    normalized = _normalize_create_memory_payload(
        payload,
        role=role,
        default_project=project,
        default_team=team,
    )
    app = OlinKBApp(
        settings=Settings(
            pg_url=pg_url,
            user=username or "",
            team=team or VIEWER_FALLBACK_TEAM,
            default_project=project,
            cache_ttl_seconds=300,
            cache_max_entries=256,
            pg_pool_max_size=pool_max_size,
            server_name="OlinKB",
        )
    )
    app.storage = PostgresStorage(pg_url, pool_max_size=pool_max_size)
    try:
        return await app.save_memory(
            uri=_build_memory_uri(
                scope=normalized["scope"],
                scope_key=normalized["scope_key"],
                title=normalized["title"],
            ),
            title=normalized["title"],
            content=normalized["content"],
            memory_type=normalized["memory_type"],
            scope=normalized["scope"],
            tags=normalized["tags"],
            metadata=normalized["metadata"],
            author=username,
        )
    finally:
        await app.storage.close()


async def _login_viewer_session(
    pg_url: str,
    *,
    username: str,
    password: str,
    team: str | None,
    project: str | None,
    pool_max_size: int = 5,
) -> dict[str, Any]:
    account = VIEWER_LOGIN_ACCOUNTS.get(username)
    if account is None or account["password"] != password:
        raise ViewerAuthenticationError("Invalid viewer credentials")

    normalized_team = team or VIEWER_FALLBACK_TEAM
    role = str(account["role"])
    storage = PostgresStorage(pg_url, pool_max_size=pool_max_size)
    try:
        member = await storage.create_or_update_member(
            username=username,
            team=normalized_team,
            role=role,
            display_name=str(account.get("display_name") or username),
        )
        if project:
            await storage.create_or_update_project_member(
                member_id=member["id"],
                username=username,
                project=project,
                team=normalized_team,
                role=role,
            )
    finally:
        await storage.close()

    return {
        "username": username,
        "role": role,
        "team": normalized_team,
        "project": project,
        "can_manage_documentation": role in APPROVER_MEMBER_ROLES,
    }


def _sanitize_query(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()[:MAX_VIEWER_QUERY_LENGTH]


def _sanitize_limit(value: str | None) -> int:
    if value is None:
        return DEFAULT_VIEWER_PAGE_SIZE
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError("limit must be an integer") from error
    return max(1, min(MAX_VIEWER_PAGE_SIZE, parsed))


def _encode_cursor(cursor: dict[str, Any] | None) -> str | None:
    if cursor is None:
        return None
    payload = json.dumps(cursor, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding).decode("utf-8"))
        relevance = float(payload["relevance"])
        updated_at = str(payload["updated_at"]).strip()
        memory_id = str(UUID(str(payload["id"])))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("cursor is invalid") from error
    if not updated_at:
        raise ValueError("cursor is invalid")
    return {
        "relevance": relevance,
        "updated_at": updated_at,
        "id": memory_id,
    }


def run_live_viewer_server(host: str = "127.0.0.1", port: int = 8123, title: str = "OlinKB Viewer") -> None:
    server = _LiveViewerHTTPServer((host, port), title=title)
    try:
        print(f"Live viewer running at http://{host}:{port}")
        print("PostgreSQL-backed live search is the primary path for large datasets")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()