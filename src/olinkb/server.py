from __future__ import annotations

from fastmcp import FastMCP

from olinkb.app import OlinKBApp


mcp = FastMCP("OlinKB")
_app: OlinKBApp | None = None


def get_app() -> OlinKBApp:
    global _app
    if _app is None:
        _app = OlinKBApp()
    return _app


@mcp.tool
async def boot_session(author: str | None = None, team: str | None = None, project: str | None = None) -> dict:
    """Start a working session and preload relevant memory for the current developer."""
    return await get_app().boot_session(author=author, team=team, project=project)


@mcp.tool
async def remember(query: str, scope: str = "all", limit: int = 5, session_id: str | None = None) -> list[dict]:
    """Search stored memories using PostgreSQL trigram matching and local read cache."""
    return await get_app().remember(query=query, scope=scope, limit=limit, session_id=session_id)


@mcp.tool
async def save_memory(
    uri: str,
    title: str,
    content: str,
    memory_type: str,
    scope: str = "personal",
    tags: str = "",
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    """Create or update a memory entry with audit logging and SHA256 deduplication."""
    return await get_app().save_memory(
        uri=uri,
        title=title,
        content=content,
        memory_type=memory_type,
        scope=scope,
        tags=tags,
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
