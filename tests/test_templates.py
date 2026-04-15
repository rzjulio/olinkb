import json

from olinkb.templates import (
    render_instructions_template,
    render_mcp_template,
    render_memory_relevance_skill_template,
)


def test_render_mcp_template_uses_mcp_alias() -> None:
    rendered = render_mcp_template(
        pg_url="postgresql://olinkb:olinkb@localhost:5433/olinkb",
        team="example-team",
    )

    config = json.loads(rendered)

    assert config["servers"]["olinkb"]["command"] == "olinkb"
    assert config["servers"]["olinkb"]["args"] == ["mcp"]
    assert config["servers"]["olinkb"]["type"] == "stdio"
    assert config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "example-team"


def test_render_instructions_mentions_boot_and_end_session() -> None:
    rendered = render_instructions_template()

    assert "boot_session" in rendered
    assert "remember" in rendered
    assert "save_memory" in rendered
    assert "end_session" in rendered


def test_render_instructions_encourages_richer_context_blocks() -> None:
    rendered = render_instructions_template()

    assert "default memory workflow across repositories" in rendered
    assert "richer context blocks" in rendered
    assert "Do not wait until `end_session`" in rendered
    assert "Do not save a one-line summary" in rendered
    assert "real operational depth" in rendered
    assert "What:" in rendered
    assert "Why:" in rendered
    assert "Where:" in rendered
    assert "Learned:" in rendered
    assert "Context:" in rendered
    assert "Decision:" in rendered
    assert "Evidence:" in rendered
    assert "Next Steps:" in rendered
    assert "without reopening every touched file first" in rendered
    assert "include_content=false" in rendered
    assert "explicitly calls `propose_memory_promotion(...)`" in rendered
    assert "specialized repository skill exists" in rendered


def test_render_memory_relevance_skill_template_contains_triage_contract() -> None:
    rendered = render_memory_relevance_skill_template()

    assert "name: memory-relevance-triage" in rendered
    assert "## Decision Rule" in rendered
    assert "## Result-Aware Triage" in rendered
    assert "## Output Contract" in rendered
    assert "SAVE" in rendered
    assert "SKIP" in rendered


def test_render_cli_instructions_switches_transport_language() -> None:
    rendered = render_instructions_template(mode="cli")

    assert "via the local OlinKB CLI transport" in rendered
    assert "olinkb tool boot_session --json" in rendered
    assert "run the corresponding `olinkb tool ...` command" in rendered
    assert "analyze_memory" in rendered
    assert "capture_memory" in rendered
    assert "MCP tools" not in rendered