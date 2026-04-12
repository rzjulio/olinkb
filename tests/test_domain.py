import pytest

from olinkb.domain import extract_namespace, parse_tags, scope_filters_for_query, validate_scope


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