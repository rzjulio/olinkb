from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


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
    "documentation",
    "business_documentation",
    "development_standard",
}

MANAGED_MEMORY_TYPES = {
    "documentation",
    "business_documentation",
    "development_standard",
}

ALLOWED_SCOPES = {"personal", "project", "team", "org", "system"}
ALLOWED_MEMBER_ROLES = {"admin", "lead", "developer", "viewer"}
APPROVER_MEMBER_ROLES = {"admin", "lead"}

QUERYABLE_SCOPES = ["personal", "project", "team", "org", "system"]
MANAGED_MEMORY_AUTO_TAGS = {
    "documentation": (
        "documentation",
        "docs",
        "technical-documentation",
        "technical-docs",
        "documentacion",
        "documentacion-tecnica",
    ),
    "business_documentation": (
        "documentation",
        "docs",
        "business-documentation",
        "business-docs",
        "documentacion",
        "documentacion-negocio",
        "documentacion-de-negocio",
    ),
    "development_standard": (
        "documentation",
        "docs",
        "development-standard",
        "engineering-standard",
        "documentacion",
        "estandar-desarrollo",
    ),
}
DOCUMENTATION_SCOPE_AUTO_TAGS = {
    "global": ("global", "global-documentation", "documentacion-global"),
    "repo": ("repo", "repository-documentation", "documentacion-repo"),
}
TAG_KEY_PATTERN = re.compile(r"[^a-z0-9]+")


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


def extract_scope_key(uri: str) -> str:
    return extract_namespace(uri).split("://", 1)[1]


def parse_tags(raw_tags: str | Iterable[str]) -> list[str]:
    if isinstance(raw_tags, str):
        items = raw_tags.split(",")
    else:
        items = list(raw_tags)
    return [item.strip() for item in items if item and item.strip()]


def enrich_memory_tags(
    memory_type: str,
    raw_tags: str | Iterable[str],
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        value = str(tag or "").strip()
        if not value:
            return
        key = _tag_key(value)
        if not key or key in seen:
            return
        seen.add(key)
        tags.append(value)

    for tag in parse_tags(raw_tags):
        add(tag)

    if not is_managed_memory_type(memory_type):
        return tags

    for tag in MANAGED_MEMORY_AUTO_TAGS.get(memory_type, ()):
        add(tag)

    if not isinstance(metadata, dict):
        return tags

    documentation_scope = _tag_key(str(metadata.get("documentation_scope") or ""))
    for tag in DOCUMENTATION_SCOPE_AUTO_TAGS.get(documentation_scope, ()):
        add(tag)

    applicable_projects = metadata.get("applicable_projects")
    if isinstance(applicable_projects, list):
        for project in applicable_projects:
            slug = _tag_key(str(project or ""))
            if not slug:
                continue
            add(slug)
            add(f"project-{slug}")
            add(f"repo-{slug}")

    return tags


def _tag_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return TAG_KEY_PATTERN.sub("-", ascii_value.lower()).strip("-")


def validate_scope(scope: str) -> str:
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Unsupported scope: {scope}")
    return scope


def validate_memory_type(memory_type: str) -> str:
    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise ValueError(f"Unsupported memory_type: {memory_type}")
    return memory_type


def is_managed_memory_type(memory_type: str) -> bool:
    return memory_type in MANAGED_MEMORY_TYPES


def validate_member_role(role: str) -> str:
    if role not in ALLOWED_MEMBER_ROLES:
        raise ValueError(f"Unsupported member role: {role}")
    return role


def scope_filters_for_query(scope: str) -> list[str]:
    if scope == "all":
        return list(QUERYABLE_SCOPES)
    return [validate_scope(scope)]


def validate_uri_matches_scope(uri: str, scope: str) -> None:
    uri_scope = infer_scope_from_uri(uri)
    if uri_scope != scope:
        raise ValueError(f"URI scope '{uri_scope}' does not match declared scope '{scope}'")
