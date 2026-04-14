import json
import os
from pathlib import Path
import subprocess
import pytest
import mcp.types as types

from olinkb import server


class FakeApp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def remember(self, **kwargs):
        self.calls.append(kwargs)
        return []

    async def save_memory(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "created", "uri": kwargs["uri"]}

    async def propose_memory_promotion(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "pending", "uri": kwargs["uri"]}

    async def list_pending_approvals(self, **kwargs):
        self.calls.append(kwargs)
        return {"total_count": 1, "proposals": []}

    async def review_memory_proposal(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": kwargs["action"], "uri": kwargs["uri"]}


def test_importing_server_does_not_eagerly_import_mcp() -> None:
    src_path = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(src_path)
    )

    result = subprocess.run(
        [
            os.environ.get("PYTHON", "python3"),
            "-c",
            "import json, sys; import olinkb.server; print(json.dumps({'mcp': 'mcp' in sys.modules}))",
        ],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )

    assert json.loads(result.stdout) == {"mcp": False}


@pytest.mark.asyncio
async def test_server_remember_exposes_include_content_flag(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    await server.remember(query="lean recall", scope="project", include_content=True)

    assert app.calls[0]["include_content"] is True


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


@pytest.mark.asyncio
async def test_server_propose_memory_promotion_passes_target_type(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    result = await server.propose_memory_promotion(
        uri="project://olinkb/decisions/richer-memory-context",
        rationale="Should become the project standard.",
        target_memory_type="standard",
    )

    assert result["status"] == "pending"
    assert app.calls[0]["target_memory_type"] == "standard"


@pytest.mark.asyncio
async def test_server_list_pending_approvals_passes_limit(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    result = await server.list_pending_approvals(project="olinkb", limit=7)

    assert result["total_count"] == 1
    assert app.calls[0]["limit"] == 7


@pytest.mark.asyncio
async def test_server_review_memory_proposal_passes_action(monkeypatch) -> None:
    app = FakeApp()
    monkeypatch.setattr(server, "get_app", lambda: app)

    result = await server.review_memory_proposal(
        uri="project://olinkb/decisions/richer-memory-context",
        action="approve",
        note="Looks good.",
    )

    assert result["status"] == "approve"
    assert app.calls[0]["action"] == "approve"


def test_tool_definitions_expose_expected_names_and_remember_schema() -> None:
    tools = {tool.name: tool for tool in server._tool_definitions()}

    assert set(tools) == {
        "boot_session",
        "remember",
        "save_memory",
        "propose_memory_promotion",
        "list_pending_approvals",
        "review_memory_proposal",
        "end_session",
        "forget",
    }
    assert tools["remember"].inputSchema["required"] == ["query"]
    assert "include_content" in tools["remember"].inputSchema["properties"]


@pytest.mark.asyncio
async def test_dispatch_tool_call_wraps_list_results_for_low_level_server(monkeypatch) -> None:
    async def fake_remember(**kwargs):
        assert kwargs == {"query": "alpha"}
        return [{"uri": "project://olinkb/facts/alpha"}]

    monkeypatch.setattr(server, "remember", fake_remember)

    unstructured, structured = await server._dispatch_tool_call("remember", {"query": "alpha"})

    assert structured == {"result": [{"uri": "project://olinkb/facts/alpha"}]}
    assert unstructured == [
        types.TextContent(
            type="text",
            text='[\n  {\n    "uri": "project://olinkb/facts/alpha"\n  }\n]',
        )
    ]