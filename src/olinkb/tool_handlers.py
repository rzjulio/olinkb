from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from olinkb.app import OlinKBApp


TOOL_NAMES = (
    "boot_session",
    "remember",
    "save_memory",
    "propose_memory_promotion",
    "list_pending_approvals",
    "review_memory_proposal",
    "end_session",
    "forget",
)


_app: OlinKBApp | None = None


def get_app() -> OlinKBApp:
    global _app
    if _app is None:
        from olinkb.app import OlinKBApp as OlinKBAppImpl

        _app = OlinKBAppImpl()
    return _app


async def boot_session(author: str | None = None, team: str | None = None, project: str | None = None) -> dict:
    return await get_app().boot_session(author=author, team=team, project=project)


async def remember(
    query: str,
    scope: str = "all",
    limit: int = 5,
    session_id: str | None = None,
    include_content: bool = False,
) -> list[dict]:
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
    return await get_app().list_pending_approvals(project=project, limit=limit, author=author)


async def review_memory_proposal(
    uri: str,
    action: str,
    note: str = "",
    session_id: str | None = None,
    author: str | None = None,
) -> dict:
    return await get_app().review_memory_proposal(
        uri=uri,
        action=action,
        note=note,
        session_id=session_id,
        author=author,
    )


async def end_session(session_id: str, summary: str) -> dict:
    return await get_app().end_session(session_id=session_id, summary=summary)


async def forget(uri: str, reason: str, session_id: str | None = None, author: str | None = None) -> dict:
    return await get_app().forget(uri=uri, reason=reason, session_id=session_id, author=author)


async def dispatch_tool_call(name: str, arguments: dict[str, Any]) -> Any:
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
    return await handler(**arguments)