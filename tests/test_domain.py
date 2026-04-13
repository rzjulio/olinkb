import pytest

from olinkb.domain import (
    enrich_memory_tags,
    extract_namespace,
    is_managed_memory_type,
    parse_tags,
    scope_filters_for_query,
    validate_memory_type,
    validate_scope,
)


def test_extract_namespace_uses_first_path_segment() -> None:
    assert extract_namespace("team://conventions/naming") == "team://conventions"
    assert extract_namespace("personal://rzjulio/context") == "personal://rzjulio"


def test_parse_tags_normalizes_commas_and_whitespace() -> None:
    assert parse_tags(" api, postgres,  cache ,, ") == ["api", "postgres", "cache"]


def test_scope_filters_for_query_expands_all() -> None:
    assert scope_filters_for_query("all") == ["personal", "project", "team", "org", "system"]


def test_validate_scope_rejects_unknown_scope() -> None:
    with pytest.raises(ValueError):
        validate_scope("unknown")


def test_validate_memory_type_accepts_bugfix() -> None:
    assert validate_memory_type("bugfix") == "bugfix"


def test_validate_memory_type_accepts_managed_memory_types() -> None:
    assert validate_memory_type("documentation") == "documentation"
    assert validate_memory_type("business_documentation") == "business_documentation"
    assert validate_memory_type("development_standard") == "development_standard"
    assert is_managed_memory_type("documentation") is True
    assert is_managed_memory_type("business_documentation") is True
    assert is_managed_memory_type("development_standard") is True
    assert is_managed_memory_type("decision") is False


def test_validate_memory_type_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        validate_memory_type("unknown")


def test_enrich_memory_tags_adds_managed_documentation_type_and_scope_tags() -> None:
    tags = enrich_memory_tags(
        "documentation",
        [],
        {"documentation_scope": "global", "applicable_projects": []},
    )

    assert "documentation" in tags
    assert "technical-documentation" in tags
    assert "documentacion" in tags
    assert "documentacion-tecnica" in tags
    assert "global" in tags
    assert "documentacion-global" in tags


def test_enrich_memory_tags_adds_business_and_project_tags() -> None:
    tags = enrich_memory_tags(
        "business_documentation",
        ["quarterly"],
        {"documentation_scope": "repo", "applicable_projects": ["OlinKB"]},
    )

    assert "quarterly" in tags
    assert "business-documentation" in tags
    assert "documentacion-negocio" in tags
    assert "repo" in tags
    assert "documentacion-repo" in tags
    assert "olinkb" in tags
    assert "project-olinkb" in tags