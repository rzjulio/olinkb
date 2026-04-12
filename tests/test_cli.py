import asyncio
import json
from pathlib import Path
import sys
import pytest

from olinkb import bootstrap
from olinkb.cli import build_parser
from olinkb import cli


def test_cli_parser_accepts_mcp_alias() -> None:
    parser = build_parser()

    args = parser.parse_args(["mcp"])

    assert args.command == "mcp"


def test_cli_parser_accepts_viewer_build_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["viewer", "build", "--output", "olinkb-viewer/index.html"])

    assert args.command == "viewer"
    assert args.viewer_command == "build"
    assert args.output == "olinkb-viewer/index.html"


def test_cli_parser_defaults_viewer_to_live_serve() -> None:
    parser = build_parser()

    args = cli._apply_command_defaults(parser.parse_args(["viewer"]))

    assert args.command == "viewer"
    assert args.viewer_command == "serve"


def test_cli_parser_accepts_viewer_serve_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["viewer", "serve", "--host", "127.0.0.1", "--port", "8123"])

    assert args.command == "viewer"
    assert args.viewer_command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 8123


def test_main_runs_live_viewer_when_subcommand_is_omitted(monkeypatch) -> None:
    called: dict[str, object] = {}

    monkeypatch.setattr(sys, "argv", ["olinkb", "viewer"])
    monkeypatch.setattr(cli, "ensure_viewer_scaffold", lambda workspace_path: Path(workspace_path))
    monkeypatch.setattr(
        cli,
        "run_live_viewer_server",
        lambda host, port, title: called.update({"host": host, "port": port, "title": title}),
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert called == {"host": "127.0.0.1", "port": 8123, "title": "OlinKB Viewer"}


def test_cli_parser_accepts_template_subcommands() -> None:
    parser = build_parser()

    args = parser.parse_args(["template", "mcp"])

    assert args.command == "template"
    assert args.template_name == "mcp"


def test_cli_parser_accepts_init_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["--init"])

    assert args.init is True
    assert args.command is None


def test_cli_parser_accepts_init_scope() -> None:
    parser = build_parser()

    args = parser.parse_args(["--init", "--scope", "global"])

    assert args.scope == "global"


def test_cli_parser_rejects_removed_setup_workspace_command() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["setup-workspace"])


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


def test_viewer_build_prints_snapshot_guidance(monkeypatch, capsys) -> None:
    parser = build_parser()
    args = parser.parse_args(["viewer", "build", "--output", "olinkb-viewer/index.html"])

    class FakeStorage:
        def __init__(self, pg_url: str) -> None:
            self.pg_url = pg_url

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def export_viewer_snapshot(self) -> dict[str, list[dict[str, object]]]:
            return {"memories": [], "sessions": [], "audit_log": [], "team_members": []}

    settings = type("Settings", (), {"pg_url": "postgresql://unused"})()

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "PostgresStorage", FakeStorage)
    monkeypatch.setattr(cli, "build_viewer_output", lambda snapshot, output, title: Path(output))

    exit_code = asyncio.run(cli._run_admin_command(args))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Static viewer snapshot written to olinkb-viewer/index.html" in output
    assert "For large-scale exploration, use: olinkb viewer" in output


def test_bootstrap_workspace_preserves_existing_servers_and_is_idempotent(tmp_path) -> None:
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

    bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="mi-equipo",
    )
    bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="mi-equipo",
    )

    mcp_config = json.loads((vscode_dir / "mcp.json").read_text(encoding="utf-8"))
    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert "engram" in mcp_config["servers"]
    assert "olinkb" in mcp_config["servers"]
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PROJECT"] == tmp_path.name
    assert instructions.count("## OlinKB Memory Protocol") == 1


def test_bootstrap_workspace_updates_existing_olinkb_protocol_block(tmp_path) -> None:
    github_dir = tmp_path / ".github"
    github_dir.mkdir()
    old_protocol = """# Repo Rules

## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

### During Work
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory`.

## Another Section

Keep this section.
"""
    (github_dir / "copilot-instructions.md").write_text(old_protocol, encoding="utf-8")

    bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="mi-equipo",
    )

    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert instructions.count("## OlinKB Memory Protocol") == 1
    assert "Do not save a one-line summary" in instructions
    assert "Evidence:" in instructions
    assert "Keep this section." in instructions
    assert "call `save_memory`." not in instructions


def test_run_init_workspace_prompts_and_detects_project(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path)])

    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        if prompt.startswith("Install scope"):
            return "1"
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "mi-equipo"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    mcp_config = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PG_URL"] == "postgresql://user:pass@db.example.com:5432/olinkb"
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "mi-equipo"
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PROJECT"] == tmp_path.name
    assert prompts == [
        "Install scope [1 repository / 2 global] [1]: ",
        "PostgreSQL URL: ",
        "Team: ",
    ]


def test_run_init_workspace_supports_global_scope(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path), "--scope", "global"])
    global_mcp_path = tmp_path / "user-mcp.json"

    def fake_input(prompt: str) -> str:
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "mi-equipo"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    mcp_config = json.loads(global_mcp_path.read_text(encoding="utf-8"))
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PG_URL"] == "postgresql://user:pass@db.example.com:5432/olinkb"
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "mi-equipo"
    assert "OLINKB_PROJECT" not in mcp_config["servers"]["olinkb"]["env"]
    assert not (tmp_path / ".github" / "copilot-instructions.md").exists()