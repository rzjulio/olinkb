from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from olinkb.tool_handlers import dispatch_tool_call


def _coalesce_json_input(json_input: Any) -> str | None:
    if json_input is None:
        return None
    if isinstance(json_input, list):
        joined = " ".join(str(part) for part in json_input if str(part).strip())
        return joined or None
    return str(json_input)


def _json_parse_candidates(raw_payload: str) -> list[str]:
    stripped = raw_payload.strip()
    candidates: list[str] = [raw_payload]
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        unwrapped = stripped[1:-1]
        if unwrapped and unwrapped not in candidates:
            candidates.append(unwrapped)

    shell_escaped = stripped.startswith("{\\\"") or stripped.startswith("[\\\"")
    if shell_escaped:
        unescaped = stripped.replace('\\"', '"')
        if unescaped not in candidates:
            candidates.append(unescaped)
        if len(unescaped) >= 2 and unescaped[0] == unescaped[-1] and unescaped[0] in {"'", '"'}:
            unwrapped = unescaped[1:-1]
            if unwrapped and unwrapped not in candidates:
                candidates.append(unwrapped)

    return candidates


def load_payload(args: Any) -> dict[str, Any]:
    raw_payload: str | None = None
    if getattr(args, "json_input", None):
        raw_payload = _coalesce_json_input(args.json_input)
    elif getattr(args, "input_file", None):
        raw_payload = Path(args.input_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        stdin_payload = sys.stdin.read()
        raw_payload = stdin_payload if stdin_payload.strip() else None

    if raw_payload is None:
        return {}

    payload = None
    decode_error: json.JSONDecodeError | None = None
    for candidate in _json_parse_candidates(raw_payload):
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError as exc:
            decode_error = exc

    if payload is None:
        raise ValueError("Tool input must be valid JSON") from decode_error

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