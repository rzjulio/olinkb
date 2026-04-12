import pytest

from olinkb import server


class FakeApp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def save_memory(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "created", "uri": kwargs["uri"]}


@pytest.mark.asyncio
async def test_server_save_memory_passes_metadata_to_app(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    metadata = {"what": "Persist richer memory context", "decision": "Store metadata"}
    result = await server.save_memory(
        uri="project://olinkb/decisions/richer-memory-context",
        title="Persist richer memory context",
        content="What: Persist richer memory context",
        memory_type="decision",
        scope="project",
        metadata=metadata,
    )

    assert result["status"] == "created"
    assert app.calls[0]["metadata"] == metadata