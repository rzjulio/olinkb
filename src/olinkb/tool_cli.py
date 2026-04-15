from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from olinkb.tool_handlers import dispatch_tool_call


def load_payload(args: Any) -> dict[str, Any]:
    raw_payload: str | None = None
    if getattr(args, "json_input", None):
        raw_payload = args.json_input
    elif getattr(args, "input_file", None):
        raw_payload = Path(args.input_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        stdin_payload = sys.stdin.read()
        raw_payload = stdin_payload if stdin_payload.strip() else None

    if raw_payload is None:
        return {}

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Tool input must be valid JSON") from exc

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Tool input must decode to a JSON object")
    return payload


async def invoke_tool(tool_name: str, payload: dict[str, Any]) -> Any:
    return await dispatch_tool_call(tool_name, payload)


def _print_error(error: Exception) -> int:
    print(
        json.dumps(
            {
                "error": {
                    "type": error.__class__.__name__,
                    "message": str(error),
                }
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


def run_tool_command(args: Any) -> int:
    try:
        payload = load_payload(args)
        result = asyncio.run(invoke_tool(args.tool_name, payload))
    except Exception as exc:
        return _print_error(exc)

    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0