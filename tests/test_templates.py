import json

from olinkb.templates import render_instructions_template, render_mcp_template


def test_render_mcp_template_uses_mcp_alias() -> None:
    rendered = render_mcp_template(
        pg_url="postgresql://olinkb:olinkb@localhost:5433/olinkb",
        team="mi-equipo",
    )

    config = json.loads(rendered)

    assert config["servers"]["olinkb"]["command"] == "olinkb"
    assert config["servers"]["olinkb"]["args"] == ["mcp"]
    assert config["servers"]["olinkb"]["type"] == "stdio"
    assert config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "mi-equipo"


def test_render_instructions_mentions_boot_and_end_session() -> None:
    rendered = render_instructions_template()

    assert "boot_session" in rendered
    assert "remember" in rendered
    assert "save_memory" in rendered
    assert "end_session" in rendered


def test_render_instructions_encourages_richer_context_blocks() -> None:
    rendered = render_instructions_template()

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