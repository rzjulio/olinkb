import json

from olinkb.cli import build_parser
from olinkb import cli


def test_cli_parser_accepts_mcp_alias() -> None:
    parser = build_parser()

    args = parser.parse_args(["mcp"])

    assert args.command == "mcp"


def test_cli_parser_accepts_template_subcommands() -> None:
    parser = build_parser()

    args = parser.parse_args(["template", "mcp"])

    assert args.command == "template"
    assert args.template_name == "mcp"


def test_cli_parser_accepts_setup_workspace() -> None:
    parser = build_parser()

    args = parser.parse_args(["setup-workspace", "--workspace-path", "."])

    assert args.command == "setup-workspace"


def test_render_template_mcp_does_not_require_settings_when_args_are_explicit(monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "template",
            "mcp",
            "--pg-url",
            "postgresql://olinkb:olinkb@localhost:5433/olinkb",
            "--team",
            "mi-equipo",
        ]
    )

    def fail_settings() -> None:
        raise AssertionError("get_settings should not be called")

    monkeypatch.setattr(cli, "get_settings", fail_settings)

    rendered = cli.render_template_output(args)

    assert '"args": [' in rendered
    assert '"mcp"' in rendered


def test_run_setup_workspace_writes_integration_files(tmp_path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "setup-workspace",
            "--workspace-path",
            str(tmp_path),
            "--pg-url",
            "postgresql://user:pass@db.example.com:5432/olinkb",
            "--team",
            "mi-equipo",
            "--project",
            "olinkb",
        ]
    )

    exit_code = cli.run_setup_workspace(args)

    assert exit_code == 0
    mcp_config = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    instructions = (tmp_path / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")

    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PG_URL"] == "postgresql://user:pass@db.example.com:5432/olinkb"
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "mi-equipo"
    assert "boot_session" in instructions


def test_run_setup_workspace_preserves_existing_servers_and_is_idempotent(tmp_path) -> None:
    vscode_dir = tmp_path / ".vscode"
    github_dir = tmp_path / ".github"
    vscode_dir.mkdir()
    github_dir.mkdir()
    (vscode_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "engram": {
                        "command": "engram",
                        "args": ["mcp"],
                        "type": "stdio",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (github_dir / "copilot-instructions.md").write_text("# Repo Rules\n", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(
        [
            "setup-workspace",
            "--workspace-path",
            str(tmp_path),
            "--pg-url",
            "postgresql://user:pass@db.example.com:5432/olinkb",
            "--team",
            "mi-equipo",
        ]
    )

    cli.run_setup_workspace(args)
    cli.run_setup_workspace(args)

    mcp_config = json.loads((vscode_dir / "mcp.json").read_text(encoding="utf-8"))
    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert "engram" in mcp_config["servers"]
    assert "olinkb" in mcp_config["servers"]
    assert instructions.count("## OlinKB Memory Protocol") == 1