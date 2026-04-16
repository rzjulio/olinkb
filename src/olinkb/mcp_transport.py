from __future__ import annotations

import asyncio
import json
from typing import Any

from olinkb import __version__
from olinkb.domain import ALLOWED_MEMORY_TYPES, ALLOWED_SCOPES
from olinkb.tool_handlers import dispatch_tool_call


LOW_LEVEL_SERVER_INSTRUCTIONS = "Shared MCP memory server for development teams"
REMEMBER_SCOPES = ["all", *sorted(ALLOWED_SCOPES)]
PROMOTION_TARGET_MEMORY_TYPES = ["convention", "standard"]
REVIEW_ACTIONS = ["approve", "reject"]

mcp = None


def _missing_mcp_dependency_error() -> RuntimeError:
    return RuntimeError(
        "The optional OlinKB MCP transport is not installed. Install the matching `olinkb-mcp` addon "
        "into the same environment as `olinkb`, for example by injecting the addon wheel into the base pipx environment or installing the addon release artifact with pip."
    )


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


def _string_array_property(description: str) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": {"type": "string"}}


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


def _automation_properties() -> dict[str, dict[str, Any]]:
    return {
        "content": _string_property("Content to analyze for relevance, type inference, and possible capture."),
        "title": _string_property("Optional explicit title. When omitted, OlinKB infers one from the content."),
        "project": _string_property("Optional project override used for project-scoped capture and URI generation."),
        "scope_hint": {
            "type": "string",
            "enum": sorted(ALLOWED_SCOPES),
            "description": "Optional scope hint used during classification and URI generation.",
        },
        "memory_type_hint": {
            "type": "string",
            "enum": sorted(ALLOWED_MEMORY_TYPES),
            "description": "Optional hint to bias classification toward a specific memory type.",
        },
        "tags": _string_property("Optional comma-separated tags to seed the inferred memory tags."),
        "metadata": _object_property("Optional metadata merged into the inferred structured metadata."),
        "session_id": _string_property("Optional active session identifier."),
        "author": _string_property("Optional username override for the actor."),
        "source_surface": _string_property("Optional source label such as cli, editor, or review."),
        "files": _string_array_property("Optional related file paths used as additional relevance signals."),
        "commands": _string_array_property("Optional related commands used as additional relevance signals."),
    }


def _get_mcp_types():
    try:
        import mcp.types as mcp_types
    except ModuleNotFoundError as exc:
        raise _missing_mcp_dependency_error() from exc

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
            name="analyze_memory",
            description="Analyze content to decide whether it should become memory, which type it looks like, and whether it resembles documentation.",
            inputSchema=_tool_schema(
                properties=_automation_properties(),
                required=["content"],
            ),
        ),
        types.Tool(
            name="capture_memory",
            description="Analyze content and automatically persist it when confidence is high enough, otherwise return a structured suggestion.",
            inputSchema=_tool_schema(
                properties={
                    **_automation_properties(),
                    "auto_save": _boolean_property("Persist automatically when the analyzer returns a save action."),
                },
                required=["content"],
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
                    "uri": _string_property("Optional canonical memory URI. When omitted, OlinKB infers one from the content, project, and memory type."),
                    "title": _string_property("Optional human-readable title for the memory. When omitted, OlinKB infers one from the content."),
                    "content": _string_property("Full memory body to persist."),
                    "memory_type": {
                        "type": "string",
                        "enum": sorted(ALLOWED_MEMORY_TYPES),
                        "description": "Memory classification used for validation and retrieval.",
                    },
                    "project": _string_property("Optional project override used when inferring project-scoped memory URIs."),
                    "scope": {
                        "type": "string",
                        "enum": sorted(ALLOWED_SCOPES),
                        "description": "Optional declared scope. When omitted, OlinKB infers it from the project or URI.",
                    },
                    "scope_hint": {
                        "type": "string",
                        "enum": sorted(ALLOWED_SCOPES),
                        "description": "Optional scope hint used during URI inference when uri is omitted.",
                    },
                    "tags": _string_property("Comma-separated tags to associate with the memory."),
                    "metadata": _object_property("Optional structured metadata stored alongside the memory."),
                    "session_id": _string_property("Optional active session identifier."),
                    "author": _string_property("Optional username override for the write actor."),
                    "source_surface": _string_property("Optional source label such as cli, editor, or review."),
                    "files": _string_array_property("Optional related file paths used as additional relevance signals."),
                    "commands": _string_array_property("Optional related commands used as additional relevance signals."),
                },
                required=["content", "memory_type"],
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
                    "session_id": _string_property("Optional session identifier returned by boot_session. When omitted, OlinKB tries to resolve a single open session for the current author/project context."),
                    "summary": _string_property("Human summary captured when ending the session."),
                    "author": _string_property("Optional username override used when resolving a missing session_id."),
                    "project": _string_property("Optional project override used when resolving a missing session_id."),
                },
                required=["summary"],
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
    result = await dispatch_tool_call(name, arguments)
    if isinstance(result, dict):
        return result
    return (_json_content(result), {"result": result})


def _get_mcp_server() -> Any:
    global mcp
    if mcp is not None:
        return mcp

    try:
        from mcp.server.lowlevel import Server
    except ModuleNotFoundError as exc:
        raise _missing_mcp_dependency_error() from exc

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
        try:
            return await _dispatch_tool_call(name, arguments)
        except Exception as exc:
            error_type = type(exc).__name__
            return _json_content({"error": {"type": error_type, "message": str(exc)}})

    mcp = server
    return mcp


async def _run_stdio_server() -> None:
    try:
        from mcp.server.lowlevel import NotificationOptions
        from mcp.server.stdio import stdio_server
    except ModuleNotFoundError as exc:
        raise _missing_mcp_dependency_error() from exc

    server = _get_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(notification_options=NotificationOptions()),
        )


def run_server() -> None:
    asyncio.run(_run_stdio_server())