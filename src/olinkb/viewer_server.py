from __future__ import annotations

import asyncio
import base64
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from olinkb.config import get_settings
from olinkb.storage.postgres import PostgresStorage
from olinkb.viewer import build_empty_viewer_payload, build_viewer_payload, render_viewer_html


DEFAULT_VIEWER_PAGE_SIZE = 50
MAX_VIEWER_PAGE_SIZE = 100
MAX_VIEWER_QUERY_LENGTH = 200


class _LiveViewerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], title: str) -> None:
        super().__init__(server_address, _LiveViewerRequestHandler)
        self.title = title
        self.settings = get_settings()
        self.index_html = render_viewer_html(
            build_empty_viewer_payload(),
            title=title,
            live_api_path="/api/viewer",
        ).encode("utf-8")


class _LiveViewerRequestHandler(BaseHTTPRequestHandler):
    server: _LiveViewerHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(self.server.index_html)
            return

        if parsed.path == "/api/viewer":
            try:
                payload = asyncio.run(_load_viewer_payload(self.server.settings.pg_url, params=parse_qs(parsed.query)))
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            self._send_json(payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_headers("text/html; charset=utf-8", len(self.server.index_html))
            return

        if parsed.path == "/api/viewer":
            try:
                payload = asyncio.run(_load_viewer_payload(self.server.settings.pg_url, params=parse_qs(parsed.query)))
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_headers("application/json; charset=utf-8", len(body))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_html(self, body: bytes) -> None:
        self._send_headers("text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers("application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_headers(self, content_type: str, content_length: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(content_length))
        self.end_headers()


async def _load_viewer_payload(pg_url: str, *, params: dict[str, list[str]]) -> dict[str, Any]:
    storage = PostgresStorage(pg_url)
    await storage.connect()
    try:
        query = _sanitize_query(_first_param(params, "q"))
        limit = _sanitize_limit(_first_param(params, "limit"))
        cursor = _decode_cursor(_first_param(params, "cursor"))

        page = await storage.search_viewer_memories(query=query, limit=limit, cursor=cursor)
        author_usernames = sorted(
            {
                str(memory.get("author_username"))
                for memory in page["memories"]
                if memory.get("author_username")
            }
        )
        team_members = await storage.load_team_members(author_usernames)
        sessions = await storage.load_recent_sessions_for_authors(author_usernames)
        payload = build_viewer_payload(
            memories=page["memories"],
            sessions=sessions,
            audit_log=[],
            team_members=team_members,
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