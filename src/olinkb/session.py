from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActiveSession:
    session_id: str
    author: str
    team: str
    project: str | None
    started_at: datetime
    ended_at: datetime | None = None
    memories_read: int = 0
    memories_written: int = 0
    working_memory: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ActiveSession] = {}

    def start(self, session_id: str, author: str, team: str = "", project: str | None = None) -> ActiveSession:
        session = ActiveSession(
            session_id=session_id,
            author=author,
            team=team,
            project=project,
            started_at=utcnow(),
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ActiveSession | None:
        return self._sessions.get(session_id)

    def bump_reads(self, session_id: str, count: int = 1) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.memories_read += count

    def bump_writes(self, session_id: str, count: int = 1) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.memories_written += count

    def end(self, session_id: str) -> ActiveSession:
        session = self._sessions.pop(session_id)
        session.ended_at = utcnow()
        return session
