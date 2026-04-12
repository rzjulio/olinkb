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