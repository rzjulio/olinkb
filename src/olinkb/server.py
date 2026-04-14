from __future__ import annotations

import asyncio
import json
from typing import Any, TYPE_CHECKING

from olinkb import __version__
from olinkb.domain import ALLOWED_MEMORY_TYPES, ALLOWED_SCOPES

if TYPE_CHECKING:
    from olinkb.app import OlinKBApp


LOW_LEVEL_SERVER_INSTRUCTIONS = "Shared MCP memory server for development teams"
REMEMBER_SCOPES = ["all", *sorted(ALLOWED_SCOPES)]
PROMOTION_TARGET_MEMORY_TYPES = ["convention", "standard"]
REVIEW_ACTIONS = ["approve", "reject"]

mcp = None
_app: OlinKBApp | None = None


def get_app() -> OlinKBApp:
    global _app
    if _app is None:
        from olinkb.app import OlinKBApp as OlinKBAppImpl

        _app = OlinKBAppImpl()
    return _app


def _string_property(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _integer_property(description: str, *, minimum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    return schema


def _boolean_property(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _object_property(description: str) -> dict[str, Any]:
    return {"type": "object", "description": description, "additionalProperties": True}


def _tool_schema(
    *,
    properties: dict[str, dict[str, Any]],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _get_mcp_types():
    import mcp.types as mcp_types

    return mcp_types


def _tool_definitions() -> list[Any]:
    types = _get_mcp_types()
    return [
        types.Tool(
            name="boot_session",
            description="Start a working session and preload relevant memory for the current developer.",
            inputSchema=_tool_schema(
                properties={
                    "author": _string_property("Optional username to use for the session author."),
                    "team": _string_property("Optional team override for this session."),
                    "project": _string_property("Optional project override for this session."),
                }
            ),
        ),
        types.Tool(
            name="remember",
            description="Search stored memories using PostgreSQL trigram matching and local read cache.",
            inputSchema=_tool_schema(
                properties={
                    "query": _string_property("Search query to match against memory content and metadata."),
                    "scope": {
                        "type": "string",
                        "enum": REMEMBER_SCOPES,
                        "description": "Search scope. Use 'all' to query across all supported scopes.",
                    },
                    "limit": _integer_property("Maximum number of results to return.", minimum=1),
                    "session_id": _string_property("Optional active session identifier."),
                    "include_content": _boolean_property("Include the full memory body in results when true."),
                },
                required=["query"],
            ),
        ),
        types.Tool(
            name="save_memory",
            description="Create or update a memory entry with audit logging, optional metadata, and SHA256 deduplication.",
            inputSchema=_tool_schema(
                properties={
                    "uri": _string_property("Canonical memory URI, such as project://olinkb/decisions/example."),
                    "title": _string_property("Human-readable title for the memory."),
                    "content": _string_property("Full memory body to persist."),
                    "memory_type": {
                        "type": "string",
                        "enum": sorted(ALLOWED_MEMORY_TYPES),
                        "description": "Memory classification used for validation and retrieval.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": sorted(ALLOWED_SCOPES),
                        "description": "Declared scope for the memory URI.",
                    },
                    "tags": _string_property("Comma-separated tags to associate with the memory."),
                    "metadata": _object_property("Optional structured metadata stored alongside the memory."),
                    "session_id": _string_property("Optional active session identifier."),
                    "author": _string_property("Optional username override for the write actor."),
                },
                required=["uri", "title", "content", "memory_type"],
            ),
        ),
        types.Tool(
            name="propose_memory_promotion",
            description="Propose a project memory to become an approved convention or standard without promoting it immediately.",
            inputSchema=_tool_schema(
                properties={
                    "uri": _string_property("Project memory URI to promote."),
                    "rationale": _string_property("Why the memory should become a project standard."),
                    "target_memory_type": {
                        "type": "string",
                        "enum": PROMOTION_TARGET_MEMORY_TYPES,
                        "description": "Promotion target. 'standard' is normalized to convention internally.",
                    },
                    "session_id": _string_property("Optional active session identifier."),
                    "author": _string_property("Optional username override for the actor."),
                },
                required=["uri", "rationale"],
            ),
        ),
        types.Tool(
            name="list_pending_approvals",
            description="List pending convention proposals for the current project. Only project leads and admins can use this.",
            inputSchema=_tool_schema(
                properties={
                    "project": _string_property("Optional project override to inspect."),
                    "limit": _integer_property("Maximum number of proposals to return.", minimum=1),
                    "author": _string_property("Optional username override for the reviewer."),
                }
            ),
        ),
        types.Tool(
            name="review_memory_proposal",
            description="Approve or reject a pending project convention proposal. Only project leads and admins can use this.",
            inputSchema=_tool_schema(
                properties={
                    "uri": _string_property("Project memory URI under review."),
                    "action": {
                        "type": "string",
                        "enum": REVIEW_ACTIONS,
                        "description": "Review action to apply to the pending proposal.",
                    },
                    "note": _string_property("Optional review note persisted with the decision."),
                    "session_id": _string_property("Optional active session identifier."),
                    "author": _string_property("Optional username override for the reviewer."),
                },
                required=["uri", "action"],
            ),
        ),
        types.Tool(
            name="end_session",
            description="Close a working session and persist summary plus in-memory usage counters.",
            inputSchema=_tool_schema(
                properties={
                    "session_id": _string_property("Session identifier returned by boot_session."),
                    "summary": _string_property("Human summary captured when ending the session."),
                },
                required=["session_id", "summary"],
            ),
        ),
        types.Tool(
            name="forget",
            description="Soft-delete a memory with an audit trail entry.",
            inputSchema=_tool_schema(
                properties={
                    "uri": _string_property("Canonical URI of the memory to forget."),
                    "reason": _string_property("Why the memory should be forgotten."),
                    "session_id": _string_property("Optional active session identifier."),
                    "author": _string_property("Optional username override for the actor."),
                },
                required=["uri", "reason"],
            ),
        ),
    ]


def _json_content(value: Any) -> list[Any]:
    types = _get_mcp_types()
    return [types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False, default=str, indent=2))]


async def _dispatch_tool_call(name: str, arguments: dict[str, Any]) -> Any:
    handlers = {
        "boot_session": boot_session,
        "remember": remember,
        "save_memory": save_memory,
        "propose_memory_promotion": propose_memory_promotion,
        "list_pending_approvals": list_pending_approvals,
        "review_memory_proposal": review_memory_proposal,
        "end_session": end_session,
        "forget": forget,
    }
    handler = handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    result = await handler(**arguments)
    if isinstance(result, dict):
        return result

    return (_json_content(result), {"result": result})


def _get_mcp_server() -> Any:
    global mcp
    if mcp is not None:
        return mcp

    from mcp.server.lowlevel import Server

    server = Server(
        "OlinKB",
        version=__version__,
        instructions=LOW_LEVEL_SERVER_INSTRUCTIONS,
    )

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return _tool_definitions()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        return await _dispatch_tool_call(name, arguments)

    mcp = server
    return mcp


async def boot_session(author: str | None = None, team: str | None = None, project: str | None = None) -> dict:
    """Start a working session and preload relevant memory for the current developer."""
    return await get_app().boot_session(author=author, team=team, project=project)


async def remember(
    query: str,
    scope: str = "all",
    limit: int = 5,
    session_id: str | None = None,
    include_content: bool = False,
) -> list[dict]:
    """Search stored memories using PostgreSQL trigram matching and local read cache.

    Set include_content=true only when the full memory body is needed; the default lean mode omits it to save tokens.
    """
    return await get_app().remember(
        query=query,
        scope=scope,
        limit=limit,
        session_id=session_id,
        include_content=include_content,
    )


async def save_memory(
    uri: str,
    title: str,
    content: str,
    memory_type: str,
    scope: str = "personal",
    tags: str = "",
    metadata: dict | None = None,
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    """Create or update a memory entry with audit logging, optional metadata, and SHA256 deduplication."""
    return await get_app().save_memory(
        uri=uri,
        title=title,
        content=content,
        memory_type=memory_type,
        scope=scope,
        tags=tags,
        metadata=metadata,
        session_id=session_id,
        author=author,
    )


async def propose_memory_promotion(
    uri: str,
    rationale: str,
    target_memory_type: str = "convention",
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    """Propose a project memory to become an approved convention or standard without promoting it immediately."""
    return await get_app().propose_memory_promotion(
        uri=uri,
        rationale=rationale,
        target_memory_type=target_memory_type,
        session_id=session_id,
        author=author,
    )


async def list_pending_approvals(
    project: str | None = None,
    limit: int = 10,
    author: str | None = None,
) -> dict:
    """List pending convention proposals for the current project. Only project leads and admins can use this."""
    return await get_app().list_pending_approvals(project=project, limit=limit, author=author)


async def review_memory_proposal(
    uri: str,
    action: str,
    note: str = "",
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    """Approve or reject a pending project convention proposal. Only project leads and admins can use this."""
    return await get_app().review_memory_proposal(
        uri=uri,
        action=action,
        note=note,
        session_id=session_id,
        author=author,
    )


async def end_session(session_id: str, summary: str) -> dict:
    """Close a working session and persist summary plus in-memory usage counters."""
    return await get_app().end_session(session_id=session_id, summary=summary)


async def forget(uri: str, reason: str, session_id: str | None = None, author: str | None = None) -> dict:
    """Soft-delete a memory with an audit trail entry."""
    return await get_app().forget(uri=uri, reason=reason, session_id=session_id, author=author)


async def _run_stdio_server() -> None:
    from mcp.server.lowlevel import NotificationOptions
    from mcp.server.stdio import stdio_server

    server = _get_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(notification_options=NotificationOptions()),
        )


def run_server() -> None:
    asyncio.run(_run_stdio_server())


if __name__ == "__main__":
    run_server()
