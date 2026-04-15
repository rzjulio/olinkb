import argparse
import json

import pytest

from olinkb import tool_cli


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


def test_load_payload_reads_json_file(tmp_path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"query":"alpha","limit":2}', encoding="utf-8")
    args = argparse.Namespace(json_input=None, input_file=str(payload_path))

    assert tool_cli.load_payload(args) == {"query": "alpha", "limit": 2}


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