from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.server.server import FastMCP

if TYPE_CHECKING:
    from olinkb.app import OlinKBApp


mcp = FastMCP("OlinKB")
_app: OlinKBApp | None = None


def get_app() -> OlinKBApp:
    global _app
    if _app is None:
        from olinkb.app import OlinKBApp as OlinKBAppImpl

        _app = OlinKBAppImpl()
    return _app


@mcp.tool
async def boot_session(author: str | None = None, team: str | None = None, project: str | None = None) -> dict:
    """Start a working session and preload relevant memory for the current developer."""
    return await get_app().boot_session(author=author, team=team, project=project)


@mcp.tool
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


@mcp.tool
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


@mcp.tool
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


@mcp.tool
async def list_pending_approvals(
    project: str | None = None,
    limit: int = 10,
    author: str | None = None,
) -> dict:
    """List pending convention proposals for the current project. Only project leads and admins can use this."""
    return await get_app().list_pending_approvals(project=project, limit=limit, author=author)


@mcp.tool
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


@mcp.tool
async def end_session(session_id: str, summary: str) -> dict:
    """Close a working session and persist summary plus in-memory usage counters."""
    return await get_app().end_session(session_id=session_id, summary=summary)


@mcp.tool
async def forget(uri: str, reason: str, session_id: str | None = None, author: str | None = None) -> dict:
    """Soft-delete a memory with an audit trail entry."""
    return await get_app().forget(uri=uri, reason=reason, session_id=session_id, author=author)


def run_server() -> None:
    mcp.run()


if __name__ == "__main__":
    run_server()
