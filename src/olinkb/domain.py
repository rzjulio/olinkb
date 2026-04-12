from __future__ import annotations

from typing import Iterable


ALLOWED_MEMORY_TYPES = {
    "fact",
    "preference",
    "event",
    "constraint",
    "procedure",
    "failure_pattern",
    "tool_affordance",
    "convention",
    "decision",
    "discovery",
    "bugfix",
}

ALLOWED_SCOPES = {"personal", "project", "team", "org", "system"}

QUERYABLE_SCOPES = ["personal", "project", "team", "org", "system"]


def extract_namespace(uri: str) -> str:
    if "://" not in uri:
        raise ValueError(f"Invalid URI: {uri}")

    scheme, remainder = uri.split("://", 1)
    segments = [segment for segment in remainder.split("/") if segment]
    if not segments:
        raise ValueError(f"URI must include at least one path segment: {uri}")
    return f"{scheme}://{segments[0]}"


def infer_scope_from_uri(uri: str) -> str:
    if "://" not in uri:
        raise ValueError(f"Invalid URI: {uri}")

    scope, _ = uri.split("://", 1)
    validate_scope(scope)
    return scope


def parse_tags(raw_tags: str | Iterable[str]) -> list[str]:
    if isinstance(raw_tags, str):
        items = raw_tags.split(",")
    else:
        items = list(raw_tags)
    return [item.strip() for item in items if item and item.strip()]


def validate_scope(scope: str) -> str:
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Unsupported scope: {scope}")
    return scope


def validate_memory_type(memory_type: str) -> str:
    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise ValueError(f"Unsupported memory_type: {memory_type}")
    return memory_type


def scope_filters_for_query(scope: str) -> list[str]:
    if scope == "all":
        return list(QUERYABLE_SCOPES)
    return [validate_scope(scope)]


def validate_uri_matches_scope(uri: str, scope: str) -> None:
    uri_scope = infer_scope_from_uri(uri)
    if uri_scope != scope:
        raise ValueError(f"URI scope '{uri_scope}' does not match declared scope '{scope}'")
