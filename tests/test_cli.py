import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from olinkb import bootstrap
from olinkb.cli import build_parser
from olinkb import cli


def test_importing_cli_does_not_eagerly_import_runtime_modules() -> None:
    src_path = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(src_path)
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; import olinkb.cli; "
                "print(json.dumps({name: name in sys.modules for name in "
                "['olinkb.server', 'olinkb.storage.postgres', 'olinkb.viewer_server']}))"
            ),
        ],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "olinkb.server": False,
        "olinkb.storage.postgres": False,
        "olinkb.viewer_server": False,
    }


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


def test_cli_parser_accepts_benchmark_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["benchmark", "--sample-size", "50", "--boot-full-content-limit", "7"])

    assert args.command == "benchmark"
    assert args.sample_size == 50
    assert args.boot_full_content_limit == 7


def test_cli_parser_accepts_add_project_member_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["add-project-member", "--username", "rzjulio", "--project", "olinkb", "--role", "lead"])

    assert args.command == "add-project-member"
    assert args.project == "olinkb"
    assert args.role == "lead"


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
        def __init__(self, pg_url: str, pool_max_size: int = 5) -> None:
            self.pg_url = pg_url
            self.pool_max_size = pool_max_size

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def export_viewer_snapshot(self) -> dict[str, list[dict[str, object]]]:
            return {"memories": [], "sessions": [], "audit_log": [], "team_members": []}

    settings = type("Settings", (), {"pg_url": "postgresql://unused", "pg_pool_max_size": 7})()

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "PostgresStorage", FakeStorage)
    monkeypatch.setattr(cli, "build_viewer_output", lambda snapshot, output, title: Path(output))

    exit_code = asyncio.run(cli._run_admin_command(args))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Static viewer snapshot written to olinkb-viewer/index.html" in output
    assert "For large-scale exploration, use: olinkb viewer" in output


def test_benchmark_prints_payload_savings(monkeypatch, capsys) -> None:
    parser = build_parser()
    args = parser.parse_args(["benchmark", "--sample-size", "10"])

    class FakeStorage:
        def __init__(self, pg_url: str, pool_max_size: int = 5) -> None:
            self.pg_url = pg_url
            self.pool_max_size = pool_max_size

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def benchmark_payloads(self, **kwargs) -> dict[str, object]:
            return {
                "boot": {
                    "full": {"bytes": 4000, "approx_tokens": 1000},
                    "hybrid": {"bytes": 2500, "approx_tokens": 620},
                    "savings": {"bytes": 1500, "approx_tokens": 380, "byte_pct": 37.5, "token_pct": 38.0},
                },
                "sample": {
                    "full": {"bytes": 3000, "approx_tokens": 750},
                    "lean": {"bytes": 1700, "approx_tokens": 430},
                    "savings": {"bytes": 1300, "approx_tokens": 320, "byte_pct": 43.33, "token_pct": 42.67},
                },
            }

    settings = type(
        "Settings",
        (),
        {"pg_url": "postgresql://unused", "user": "rzjulio", "default_project": "olinkb", "pg_pool_max_size": 7},
    )()

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "PostgresStorage", FakeStorage)

    exit_code = asyncio.run(cli._run_admin_command(args))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Payload benchmark" in output
    assert "Boot full vs hybrid" in output
    assert "Memory sample full vs lean" in output


def test_add_project_member_prints_project_assignment(monkeypatch, capsys) -> None:
    parser = build_parser()
    args = parser.parse_args(["add-project-member", "--username", "rzjulio", "--project", "olinkb", "--role", "lead"])

    class FakeStorage:
        def __init__(self, pg_url: str, pool_max_size: int = 5) -> None:
            self.pg_url = pg_url
            self.pool_max_size = pool_max_size

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def ensure_member(self, username: str, team: str) -> dict[str, object]:
            return {"id": "member-1", "username": username, "team": team}

        async def create_or_update_project_member(self, **kwargs) -> dict[str, object]:
            return {
                "username": kwargs["username"],
                "project": kwargs["project"],
                "role": kwargs["role"],
            }

    settings = type(
        "Settings",
        (),
        {"pg_url": "postgresql://unused", "user": "rzjulio", "default_project": "olinkb", "pg_pool_max_size": 7, "team": "default-team"},
    )()

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "PostgresStorage", FakeStorage)

    exit_code = asyncio.run(cli._run_admin_command(args))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Project member ready: rzjulio (lead) on project olinkb" in output


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