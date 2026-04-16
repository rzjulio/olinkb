from __future__ import annotations

import asyncio
import json
import re
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


def _split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False

    for char in text:
        if quote is not None:
            current.append(char)
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            current.append(char)
            continue
        if char in "[{(":
            depth += 1
            current.append(char)
            continue
        if char in "]})":
            depth = max(0, depth - 1)
            current.append(char)
            continue
        if char == delimiter and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    parts.append("".join(current).strip())
    return parts


def _split_key_value(entry: str) -> tuple[str, str] | None:
    depth = 0
    quote: str | None = None
    escape = False

    for index, char in enumerate(entry):
        if quote is not None:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            continue
        if char in "[{(":
            depth += 1
            continue
        if char in "]})":
            depth = max(0, depth - 1)
            continue
        if char == ":" and depth == 0:
            return entry[:index].strip(), entry[index + 1 :].strip()

    return None


def _looks_like_object_key(segment: str) -> bool:
    stripped = segment.lstrip()
    if not stripped:
        return False
    if stripped[0] in {'"', "'"}:
        quote = stripped[0]
        closing_index = stripped.find(quote, 1)
        if closing_index <= 0:
            return False
        remainder = stripped[closing_index + 1 :].lstrip()
        return remainder.startswith(":")
    return re.match(r"[A-Za-z_][A-Za-z0-9_\-]*\s*:", stripped) is not None


def _split_object_entries(text: str) -> list[str]:
    entries: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False

    for index, char in enumerate(text):
        if quote is not None:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            continue
        if char in "[{(":
            depth += 1
            continue
        if char in "]})":
            depth = max(0, depth - 1)
            continue
        if char != "," or depth != 0:
            continue
        if not _looks_like_object_key(text[index + 1 :]):
            continue
        entries.append(text[start:index].strip())
        start = index + 1

    entries.append(text[start:].strip())
    return [entry for entry in entries if entry]


def _parse_powershell_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.fullmatch(r"-?(0|[1-9]\d*)", value):
        return int(value)
    if re.fullmatch(r"-?(0|[1-9]\d*)\.\d+", value):
        return float(value)
    return value


def _parse_powershell_value(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""

    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        if stripped[0] == '"':
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return stripped[1:-1]

    if stripped.startswith("{") and stripped.endswith("}"):
        return _parse_powershell_object_literal(stripped)

    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [_parse_powershell_value(part) for part in _split_top_level(inner, ",") if part]

    return _parse_powershell_scalar(stripped)


def _parse_powershell_object_literal(raw_payload: str) -> dict[str, Any] | None:
    stripped = raw_payload.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None

    body = stripped[1:-1].strip()
    if not body:
        return {}

    payload: dict[str, Any] = {}
    for entry in _split_object_entries(body):
        if not entry:
            continue
        pair = _split_key_value(entry)
        if pair is None:
            return None
        key, raw_value = pair
        if not key:
            return None
        normalized_key = key[1:-1] if len(key) >= 2 and key[0] == key[-1] and key[0] in {'"', "'"} else key
        if not normalized_key:
            return None
        payload[normalized_key] = _parse_powershell_value(raw_value)

    return payload


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
        payload = _parse_powershell_object_literal(raw_payload)

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