from dataclasses import replace

import pytest

from olinkb.app import OlinKBApp
from olinkb.config import Settings


class FakeStorage:
    def __init__(self) -> None:
        self.ensure_member_calls: list[tuple[str, str]] = []

    async def ensure_member(self, username: str, team: str) -> dict:
        self.ensure_member_calls.append((username, team))
        return {"id": "member-1", "team": team}

    async def start_session(self, author_id: str, author_username: str, project: str | None) -> str:
        return "session-1"

    async def load_boot_memories(self, username: str, project: str | None) -> list[dict]:
        return []


@pytest.mark.asyncio
async def test_boot_session_accepts_explicit_team_override() -> None:
    settings = Settings(
        pg_url="postgresql://unused",
        user="rzjulio",
        team="default-team",
        default_project="olinkb",
        cache_ttl_seconds=300,
        cache_max_entries=100,
        server_name="OlinKB",
    )
    app = OlinKBApp(settings=settings)
    app.storage = FakeStorage()

    result = await app.boot_session(author="rzjulio", team="override-team", project="olinkb")

    assert app.storage.ensure_member_calls == [("rzjulio", "override-team")]
    assert result["team"] == "override-team"