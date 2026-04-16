import argparse
import json

import pytest

from olinkb import tool_cli
from olinkb.tool_handlers import dispatch_tool_call


def test_run_tool_command_prints_json_result(monkeypatch, capsys) -> None:
    args = argparse.Namespace(
        tool_name="remember",
        json_input='{"query":"alpha"}',
        input_file=None,
    )

    async def fake_invoke_tool(tool_name: str, payload: dict[str, object]) -> list[dict[str, str]]:
        assert tool_name == "remember"
        assert payload == {"query": "alpha"}
        return [{"uri": "project://olinkb/decisions/alpha"}]

    monkeypatch.setattr(tool_cli, "invoke_tool", fake_invoke_tool)

    exit_code = tool_cli.run_tool_command(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == [{"uri": "project://olinkb/decisions/alpha"}]


def test_run_tool_command_prints_analyze_memory_result(monkeypatch, capsys) -> None:
    args = argparse.Namespace(
        tool_name="analyze_memory",
        json_input='{"content":"# CLI Memory Automation\\n\\nDecision: keep it CLI-first"}',
        input_file=None,
    )

    async def fake_invoke_tool(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        assert tool_name == "analyze_memory"
        assert payload["content"] == "# CLI Memory Automation\n\nDecision: keep it CLI-first"
        return {
            "action": "suggest",
            "suggested_memory_type": "documentation",
            "documentation_candidate": True,
        }

    monkeypatch.setattr(tool_cli, "invoke_tool", fake_invoke_tool)

    exit_code = tool_cli.run_tool_command(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == {
        "action": "suggest",
        "suggested_memory_type": "documentation",
        "documentation_candidate": True,
    }


def test_load_payload_reads_json_file(tmp_path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"query":"alpha","limit":2}', encoding="utf-8")
    args = argparse.Namespace(json_input=None, input_file=str(payload_path))

    assert tool_cli.load_payload(args) == {"query": "alpha", "limit": 2}


def test_load_payload_joins_multitoken_json_input() -> None:
    args = argparse.Namespace(
        json_input=[
            '{"project":"facturacion-electronica","memory_type":"bugfix","title":"PPCC',
            'switch',
            'sizing","content":"What:',
            'Reduced',
            'the',
            'switch."}',
        ],
        input_file=None,
    )

    assert tool_cli.load_payload(args) == {
        "project": "facturacion-electronica",
        "memory_type": "bugfix",
        "title": "PPCC switch sizing",
        "content": "What: Reduced the switch.",
    }


def test_load_payload_accepts_shell_escaped_json_object() -> None:
    args = argparse.Namespace(json_input='{\\"query\\":\\"alpha\\"}', input_file=None)

    assert tool_cli.load_payload(args) == {"query": "alpha"}


def test_load_payload_accepts_powershell_object_literal() -> None:
    args = argparse.Namespace(json_input="{project:olinkb}", input_file=None)

    assert tool_cli.load_payload(args) == {"project": "olinkb"}


def test_load_payload_accepts_powershell_object_literal_with_spaces_and_boolean() -> None:
    args = argparse.Namespace(
        json_input="{include_content:false,query:what does the olinkb project do architecture purpose features}",
        input_file=None,
    )

    assert tool_cli.load_payload(args) == {
        "include_content": False,
        "query": "what does the olinkb project do architecture purpose features",
    }


def test_load_payload_accepts_powershell_object_literal_with_commas_inside_string_values() -> None:
    args = argparse.Namespace(
        json_input=(
            "{summary:Fixed PowerShell CLI JSON parsing for olinkb tool --json, added regression tests, "
            "updated open-session recovery.,session_id:4453b376-c961-4000-910f-bb04e0915078}"
        ),
        input_file=None,
    )

    assert tool_cli.load_payload(args) == {
        "summary": "Fixed PowerShell CLI JSON parsing for olinkb tool --json, added regression tests, updated open-session recovery.",
        "session_id": "4453b376-c961-4000-910f-bb04e0915078",
    }


def test_load_payload_rejects_non_object_json() -> None:
    args = argparse.Namespace(json_input='["alpha"]', input_file=None)

    with pytest.raises(ValueError, match="JSON object"):
        tool_cli.load_payload(args)


def test_run_tool_command_returns_json_error_for_invalid_input(capsys) -> None:
    args = argparse.Namespace(
        tool_name="remember",
        json_input='["alpha"]',
        input_file=None,
    )

    exit_code = tool_cli.run_tool_command(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert json.loads(output) == {
        "error": {
            "type": "ValueError",
            "message": "Tool input must decode to a JSON object",
        }
    }


def test_run_tool_command_returns_json_error_for_tool_failure(monkeypatch, capsys) -> None:
    args = argparse.Namespace(
        tool_name="remember",
        json_input='{"query":"alpha"}',
        input_file=None,
    )

    async def fake_invoke_tool(tool_name: str, payload: dict[str, object]) -> list[dict[str, str]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(tool_cli, "invoke_tool", fake_invoke_tool)

    exit_code = tool_cli.run_tool_command(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert json.loads(output) == {
        "error": {
            "type": "RuntimeError",
            "message": "boom",
        }
    }


@pytest.mark.asyncio
async def test_dispatch_tool_call_rejects_missing_required_arguments() -> None:
    with pytest.raises(ValueError, match="missing required arguments: content, memory_type"):
        await dispatch_tool_call("save_memory", {})


@pytest.mark.asyncio
async def test_dispatch_tool_call_rejects_unexpected_arguments() -> None:
    with pytest.raises(ValueError, match="unexpected arguments: bogus"):
        await dispatch_tool_call("boot_session", {"bogus": "value"})


@pytest.mark.asyncio
async def test_dispatch_tool_call_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unknown tool: nonexistent"):
        await dispatch_tool_call("nonexistent", {})