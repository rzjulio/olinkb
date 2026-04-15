import asyncio
import json
import os
from argparse import Namespace
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


def test_cli_parser_accepts_tool_transport_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["tool", "remember", "--json", '{"query":"alpha"}'])

    assert args.command == "tool"
    assert args.tool_name == "remember"
    assert args.json_input == '{"query":"alpha"}'


def test_cli_parser_accepts_analyze_memory_tool_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["tool", "analyze_memory", "--json", '{"content":"Decision: keep it CLI-first"}'])

    assert args.command == "tool"
    assert args.tool_name == "analyze_memory"


def test_cli_parser_accepts_capture_memory_tool_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["tool", "capture_memory", "--json", '{"content":"What: fix"}'])

    assert args.command == "tool"
    assert args.tool_name == "capture_memory"


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


def test_main_returns_clean_error_when_mcp_transport_is_unavailable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["olinkb", "mcp"])
    monkeypatch.setattr(cli, "run_server", lambda: (_ for _ in ()).throw(RuntimeError("missing addon")))

    exit_code = cli.main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert output.err.strip() == "missing addon"


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


def test_cli_parser_accepts_init_mode() -> None:
    parser = build_parser()

    args = parser.parse_args(["--init", "--mode", "cli"])

    assert args.mode == "cli"


def test_run_init_workspace_prompts_for_sqlite_backend(monkeypatch, tmp_path, capsys) -> None:
    args = Namespace(scope=None, mode=None, workspace_path=str(tmp_path))
    prompts = iter(["repository", "sqlite"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(cli, "_prompt_choice", lambda *_args, **_kwargs: next(prompts))
    monkeypatch.setattr(
        cli,
        "_prompt_required_value",
        lambda label, default=None: "example-team" if label == "Team" else str(default),
    )
    monkeypatch.setattr(cli, "resolve_bootstrap_mode", lambda explicit_mode=None: "cli")

    def fake_bootstrap_workspace(**kwargs):
        captured.update(kwargs)
        return {
            "scope": kwargs["scope"],
            "mode": kwargs["mode"],
            "storage_backend": kwargs["storage_backend"],
            "project": tmp_path.name,
            "mcp_path": None,
            "instructions_path": str(tmp_path / ".github" / "copilot-instructions.md"),
            "prompt_path": None,
            "skill_path": str(tmp_path / ".copilot" / "skills" / "memory-relevance-triage" / "SKILL.md"),
            "settings_path": "/tmp/settings.json",
            "shell_env_path": "/tmp/env.sh",
            "command_wrapper_path": "/tmp/olinkb",
            "windows_user_path_status": "skipped",
            "shell_profile_paths": [],
        }

    monkeypatch.setattr(cli, "bootstrap_workspace", fake_bootstrap_workspace)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    assert captured["storage_backend"] == "sqlite"
    assert captured["sqlite_path"] == tmp_path / ".olinkb" / "olinkb.db"
    assert captured["team"] == "example-team"


def test_environment_document_supports_sqlite_backend(tmp_path) -> None:
    sqlite_path = tmp_path / ".olinkb" / "olinkb.db"

    document = bootstrap._environment_document(
        storage_backend="sqlite",
        team="example-team",
        sqlite_path=sqlite_path,
        project="olinkb",
    )

    assert document == {
        "OLINKB_STORAGE_BACKEND": "sqlite",
        "OLINKB_SQLITE_PATH": str(sqlite_path),
        "OLINKB_TEAM": "example-team",
        "OLINKB_PROJECT": "olinkb",
    }


def test_cli_parser_accepts_uninstall_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["uninstall", "--scope", "all", "--skip-package-uninstall"])

    assert args.command == "uninstall"
    assert args.scope == "all"
    assert args.skip_package_uninstall is True


def test_resolve_bootstrap_mode_prefers_explicit_mode(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_mcp_addon_installed", lambda: True)

    assert cli.resolve_bootstrap_mode("cli") == "cli"


def test_resolve_bootstrap_mode_uses_cli_when_mcp_addon_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_mcp_addon_installed", lambda: False)

    assert cli.resolve_bootstrap_mode() == "cli"


def test_resolve_bootstrap_mode_uses_mcp_when_mcp_addon_is_installed(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_mcp_addon_installed", lambda: True)

    assert cli.resolve_bootstrap_mode() == "mcp"


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
            "example-team",
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
    skill_path = tmp_path / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
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
        team="example-team",
        mode="mcp",
    )
    bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="example-team",
        mode="mcp",
    )

    mcp_config = json.loads((vscode_dir / "mcp.json").read_text(encoding="utf-8"))
    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")
    skill_text = skill_path.read_text(encoding="utf-8")

    assert "engram" in mcp_config["servers"]
    assert "olinkb" in mcp_config["servers"]
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PROJECT"] == tmp_path.name
    assert instructions.count("## OlinKB Memory Protocol") == 1
    assert "name: memory-relevance-triage" in skill_text


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
        team="example-team",
    )

    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert instructions.count("## OlinKB Memory Protocol") == 1
    assert "Do not save a one-line summary" in instructions
    assert "Evidence:" in instructions
    assert "Keep this section." in instructions
    assert "call `save_memory`." not in instructions


@pytest.mark.parametrize(
    ("platform_name", "os_name", "expected_suffix"),
    [
        ("darwin", "posix", Path("Library") / "Application Support" / "Code" / "User" / "mcp.json"),
        ("linux", "posix", Path(".config") / "Code" / "User" / "mcp.json"),
    ],
)
def test_get_global_mcp_config_path_uses_expected_unix_locations(
    monkeypatch, tmp_path, platform_name: str, os_name: str, expected_suffix: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setattr(bootstrap.sys, "platform", platform_name)
    monkeypatch.setattr(bootstrap.os, "name", os_name, raising=False)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("APPDATA", raising=False)

    assert bootstrap.get_global_mcp_config_path() == fake_home / expected_suffix


def test_get_global_mcp_config_path_uses_appdata_on_windows(monkeypatch, tmp_path) -> None:
    appdata_root = tmp_path / "roaming"
    appdata_root.mkdir()

    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setattr(bootstrap.os, "name", "nt", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setenv("APPDATA", str(appdata_root))

    assert bootstrap.get_global_mcp_config_path() == appdata_root / "Code" / "User" / "mcp.json"


@pytest.mark.parametrize("appdata_value", [None, "", "   "])
def test_get_global_mcp_config_path_falls_back_when_windows_appdata_is_missing_or_blank(
    monkeypatch, tmp_path, appdata_value: str | None
) -> None:
    userprofile_root = tmp_path / "profile"
    userprofile_root.mkdir()

    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setattr(bootstrap.os, "name", "nt", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(userprofile_root))
    if appdata_value is None:
        monkeypatch.delenv("APPDATA", raising=False)
    else:
        monkeypatch.setenv("APPDATA", appdata_value)

    assert bootstrap.get_global_mcp_config_path() == userprofile_root / "AppData" / "Roaming" / "Code" / "User" / "mcp.json"


def test_get_global_instructions_path_uses_user_home(monkeypatch, tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    assert bootstrap.get_global_instructions_path() == fake_home / ".copilot" / "instructions" / bootstrap.INSTRUCTIONS_FILENAME


@pytest.mark.parametrize(
    ("platform_name", "os_name", "expected_suffix"),
    [
        ("darwin", "posix", Path("Library") / "Application Support" / "Code" / "User" / "prompts"),
        ("linux", "posix", Path(".config") / "Code" / "User" / "prompts"),
    ],
)
def test_get_global_prompts_dir_uses_expected_unix_locations(
    monkeypatch, tmp_path, platform_name: str, os_name: str, expected_suffix: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setattr(bootstrap.sys, "platform", platform_name)
    monkeypatch.setattr(bootstrap.os, "name", os_name, raising=False)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("APPDATA", raising=False)

    assert bootstrap.get_global_prompts_dir() == fake_home / expected_suffix


def test_get_global_prompts_dir_uses_appdata_on_windows(monkeypatch, tmp_path) -> None:
    appdata_root = tmp_path / "roaming"
    appdata_root.mkdir()

    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setattr(bootstrap.os, "name", "nt", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setenv("APPDATA", str(appdata_root))

    assert bootstrap.get_global_prompts_dir() == appdata_root / "Code" / "User" / "prompts"


def test_get_global_skill_path_uses_user_home(monkeypatch, tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    assert bootstrap.get_global_skill_path() == fake_home / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"


def test_get_global_shell_env_path_uses_user_home(monkeypatch, tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    assert bootstrap.get_global_shell_env_path() == fake_home / ".config" / "olinkb" / "env.sh"


def test_get_global_command_wrapper_path_uses_user_home(monkeypatch, tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    assert bootstrap.get_global_command_wrapper_path() == fake_home / ".local" / "bin" / "olinkb"


def test_get_global_command_wrapper_path_uses_windows_local_appdata(monkeypatch, tmp_path) -> None:
    localappdata_root = tmp_path / "localappdata"
    localappdata_root.mkdir()

    monkeypatch.setattr(bootstrap.os, "name", "nt", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata_root))

    assert bootstrap.get_global_command_wrapper_path() == localappdata_root / "olinkb" / "bin" / "olinkb.cmd"


def test_persist_windows_user_path_skips_on_non_windows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.os, "name", "posix", raising=False)

    assert bootstrap.persist_windows_user_path(tmp_path / "bin") == "skipped"


def test_persist_windows_user_path_adds_wrapper_dir_once(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bootstrap.os, "name", "nt", raising=False)
    wrapper_dir = tmp_path / "AppData" / "Local" / "olinkb" / "bin"
    state = {"path": r"C:\Windows\System32"}

    monkeypatch.setattr(bootstrap, "load_windows_user_path", lambda: state["path"])

    def fake_save(value: str) -> None:
        state["path"] = value

    monkeypatch.setattr(bootstrap, "save_windows_user_path", fake_save)
    monkeypatch.setattr(bootstrap, "notify_windows_environment_change", lambda: None)

    status = bootstrap.persist_windows_user_path(wrapper_dir)

    assert status == "updated"
    assert str(wrapper_dir) in state["path"]

    status_again = bootstrap.persist_windows_user_path(wrapper_dir)

    assert status_again == "unchanged"


def test_run_init_workspace_supports_global_scope_on_windows_updates_user_path(tmp_path, monkeypatch) -> None:
    global_mcp_path = tmp_path / "user-mcp.json"
    global_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions.md"
    global_prompts_dir = tmp_path / "user-home" / "AppData" / "Roaming" / "Code" / "User" / "prompts"
    global_skill_path = tmp_path / "user-home" / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
    global_shell_env_path = tmp_path / "user-home" / ".config" / "olinkb" / "env.sh"
    global_wrapper_path = tmp_path / "user-home" / "AppData" / "Local" / "olinkb" / "bin" / "olinkb.cmd"
    global_settings_path = tmp_path / "user-home" / ".config" / "olinkb" / "settings.json"
    path_updates: list[str] = []

    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr(bootstrap, "get_global_instructions_path", lambda: global_instructions_path)
    monkeypatch.setattr(bootstrap, "get_global_prompts_dir", lambda: global_prompts_dir)
    monkeypatch.setattr(bootstrap, "get_global_skill_path", lambda: global_skill_path)
    monkeypatch.setattr(bootstrap, "get_global_shell_env_path", lambda: global_shell_env_path)
    monkeypatch.setattr(bootstrap, "get_global_command_wrapper_path", lambda: global_wrapper_path)
    monkeypatch.setattr(bootstrap, "get_global_settings_path", lambda: global_settings_path)
    monkeypatch.setattr(bootstrap, "get_shell_profile_paths", lambda: [])
    monkeypatch.setattr(bootstrap, "persist_windows_user_path", lambda wrapper_dir: path_updates.append(str(wrapper_dir)) or "updated")

    result = bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="example-team",
        scope="global",
        mode="cli",
    )

    assert result["windows_user_path_status"] == "updated"
    assert path_updates == [str(global_wrapper_path.parent)]
    prompt_path = global_prompts_dir / bootstrap.OLINKB_CLI_MANDATORY_PROMPT_FILENAME
    assert result["prompt_path"] == str(prompt_path)
    assert prompt_path.read_text(encoding="utf-8") == bootstrap.render_cli_mandatory_prompt_template().rstrip() + "\n"


def test_run_init_workspace_prompts_and_detects_project(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path)])
    repo_skill_path = tmp_path / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"

    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        if prompt.startswith("Install scope"):
            return "1"
        if prompt.startswith("Storage backend"):
            return "1"
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "example-team"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(cli, "_mcp_addon_installed", lambda: False)
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    assert not (tmp_path / ".vscode" / "mcp.json").exists()
    assert repo_skill_path.exists()
    instructions = (tmp_path / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "olinkb tool boot_session --json" in instructions
    assert prompts == [
        "Install scope [1 repository / 2 global] [1]: ",
        "Storage backend [1 postgres / 2 sqlite] [1]: ",
        "PostgreSQL URL: ",
        "Team: ",
    ]


def test_run_init_workspace_auto_selects_mcp_when_addon_is_installed(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path)])

    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        if prompt.startswith("Install scope"):
            return "1"
        if prompt.startswith("Storage backend"):
            return "1"
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "example-team"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(cli, "_mcp_addon_installed", lambda: True)
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    mcp_config = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["servers"]["olinkb"]["args"] == ["mcp"]
    assert prompts == [
        "Install scope [1 repository / 2 global] [1]: ",
        "Storage backend [1 postgres / 2 sqlite] [1]: ",
        "PostgreSQL URL: ",
        "Team: ",
    ]


def test_run_init_workspace_supports_global_scope(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path), "--scope", "global", "--mode", "mcp"])
    global_mcp_path = tmp_path / "user-mcp.json"
    global_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions.md"
    global_skill_path = tmp_path / "user-home" / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
    global_shell_env_path = tmp_path / "user-home" / ".config" / "olinkb" / "env.sh"
    global_wrapper_path = tmp_path / "user-home" / ".local" / "bin" / "olinkb"
    global_settings_path = tmp_path / "user-home" / ".config" / "olinkb" / "settings.json"
    zprofile_path = tmp_path / "user-home" / ".zprofile"
    zshrc_path = tmp_path / "user-home" / ".zshrc"

    def fake_input(prompt: str) -> str:
        if prompt.startswith("Storage backend"):
            return "1"
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "example-team"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr(bootstrap, "get_global_instructions_path", lambda: global_instructions_path)
    monkeypatch.setattr(bootstrap, "get_global_skill_path", lambda: global_skill_path)
    monkeypatch.setattr(bootstrap, "get_global_shell_env_path", lambda: global_shell_env_path)
    monkeypatch.setattr(bootstrap, "get_global_command_wrapper_path", lambda: global_wrapper_path)
    monkeypatch.setattr(bootstrap, "get_global_settings_path", lambda: global_settings_path)
    monkeypatch.setattr(bootstrap, "get_shell_profile_paths", lambda: [zprofile_path, zshrc_path])
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    mcp_config = json.loads(global_mcp_path.read_text(encoding="utf-8"))
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_PG_URL"] == "postgresql://user:pass@db.example.com:5432/olinkb"
    assert mcp_config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "example-team"
    assert "OLINKB_PROJECT" not in mcp_config["servers"]["olinkb"]["env"]
    assert global_instructions_path.exists()
    assert global_skill_path.exists()
    assert global_shell_env_path.exists()
    assert global_wrapper_path.exists()
    assert global_settings_path.exists()
    assert "## OlinKB Memory Protocol" in global_instructions_path.read_text(encoding="utf-8")
    assert "name: memory-relevance-triage" in global_skill_path.read_text(encoding="utf-8")
    assert "OLINKB_PG_URL" in global_shell_env_path.read_text(encoding="utf-8")
    assert "python" in global_wrapper_path.read_text(encoding="utf-8")
    assert "olinkb.cli" in global_wrapper_path.read_text(encoding="utf-8")
    assert "olinkb/env.sh" in zprofile_path.read_text(encoding="utf-8")
    assert "olinkb/env.sh" in zshrc_path.read_text(encoding="utf-8")
    assert not (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_bootstrap_workspace_cli_mode_removes_existing_olinkb_server_and_preserves_other_servers(tmp_path) -> None:
    vscode_dir = tmp_path / ".vscode"
    github_dir = tmp_path / ".github"
    vscode_dir.mkdir()
    github_dir.mkdir()
    (vscode_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "olinkb": {
                        "command": "olinkb",
                        "args": ["mcp"],
                        "type": "stdio",
                    },
                    "engram": {
                        "command": "engram",
                        "args": ["mcp"],
                        "type": "stdio",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    result = bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="example-team",
        mode="cli",
    )

    mcp_config = json.loads((vscode_dir / "mcp.json").read_text(encoding="utf-8"))
    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert result["mode"] == "cli"
    assert result["mcp_path"] is None
    assert "olinkb" not in mcp_config["servers"]
    assert "engram" in mcp_config["servers"]
    assert "olinkb tool boot_session --json" in instructions


def test_uninstall_workspace_repository_scope_removes_generated_artifacts(tmp_path) -> None:
    vscode_dir = tmp_path / ".vscode"
    github_dir = tmp_path / ".github"
    skill_dir = tmp_path / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME
    vscode_dir.mkdir(parents=True)
    github_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)

    (vscode_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "olinkb": {"command": "olinkb", "args": ["mcp"], "type": "stdio"},
                    "engram": {"command": "engram", "args": ["mcp"], "type": "stdio"},
                }
            }
        ),
        encoding="utf-8",
    )
    (github_dir / "copilot-instructions.md").write_text(
        "# Repo Rules\n\n## OlinKB Memory Protocol\n\nCLI guidance.\n\n## Keep\n\nKeep this section.\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("name: memory-relevance-triage\n", encoding="utf-8")
    cli.ensure_viewer_scaffold(tmp_path)

    result = bootstrap.uninstall_workspace(workspace_path=tmp_path, scope="repository")

    mcp_config = json.loads((vscode_dir / "mcp.json").read_text(encoding="utf-8"))
    instructions = (github_dir / "copilot-instructions.md").read_text(encoding="utf-8")

    assert result["scope"] == "repository"
    assert result["repository"]["mcp_status"] == "updated"
    assert result["repository"]["instructions_status"] == "updated"
    assert result["repository"]["skill_status"] == "deleted"
    assert result["repository"]["viewer_status"] == "deleted"
    assert "olinkb" not in mcp_config["servers"]
    assert "engram" in mcp_config["servers"]
    assert "## OlinKB Memory Protocol" not in instructions
    assert "Keep this section." in instructions
    assert not (skill_dir / "SKILL.md").exists()
    assert not (tmp_path / "olinkb-viewer").exists()


def test_uninstall_workspace_global_scope_removes_persisted_artifacts_and_hooks(tmp_path, monkeypatch) -> None:
    global_mcp_path = tmp_path / "user-mcp.json"
    global_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions" / bootstrap.INSTRUCTIONS_FILENAME
    legacy_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions.md"
    global_skill_path = tmp_path / "user-home" / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
    global_shell_env_path = tmp_path / "user-home" / ".config" / "olinkb" / "env.sh"
    global_wrapper_path = tmp_path / "user-home" / ".local" / "bin" / "olinkb"
    global_settings_path = tmp_path / "user-home" / ".config" / "olinkb" / "settings.json"
    zprofile_path = tmp_path / "user-home" / ".zprofile"
    zshrc_path = tmp_path / "user-home" / ".zshrc"

    global_mcp_path.parent.mkdir(parents=True, exist_ok=True)
    global_instructions_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_instructions_path.parent.mkdir(parents=True, exist_ok=True)
    global_skill_path.parent.mkdir(parents=True, exist_ok=True)
    global_shell_env_path.parent.mkdir(parents=True, exist_ok=True)
    global_wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    global_settings_path.parent.mkdir(parents=True, exist_ok=True)

    global_mcp_path.write_text(
        json.dumps(
            {
                "servers": {
                    "olinkb": {"command": "olinkb", "args": ["mcp"], "type": "stdio"},
                    "engram": {"command": "engram", "args": ["mcp"], "type": "stdio"},
                }
            }
        ),
        encoding="utf-8",
    )
    global_instructions_path.write_text(
        "# User Rules\n\n## OlinKB Memory Protocol\n\nCurrent guidance.\n\n## Keep\n\nKeep this section.\n",
        encoding="utf-8",
    )
    legacy_instructions_path.write_text(
        "# User Rules\n\n## OlinKB Memory Protocol\n\nLegacy guidance.\n",
        encoding="utf-8",
    )
    global_skill_path.write_text("name: memory-relevance-triage\n", encoding="utf-8")
    global_shell_env_path.write_text("export OLINKB_TEAM=example-team\n", encoding="utf-8")
    global_wrapper_path.write_text("#!/bin/sh\n", encoding="utf-8")
    global_settings_path.write_text('{"OLINKB_TEAM":"example-team"}\n', encoding="utf-8")
    zprofile_path.write_text(
        "# profile\n\n# >>> OlinKB environment >>>\n[ -f \"/tmp/env.sh\" ] && . \"/tmp/env.sh\"\n# <<< OlinKB environment <<<\n",
        encoding="utf-8",
    )
    zshrc_path.write_text(
        "# rc\n\n# >>> OlinKB environment >>>\n[ -f \"/tmp/env.sh\" ] && . \"/tmp/env.sh\"\n# <<< OlinKB environment <<<\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr(bootstrap, "get_global_instructions_path", lambda: global_instructions_path)
    monkeypatch.setattr(bootstrap, "get_legacy_global_instructions_path", lambda: legacy_instructions_path)
    monkeypatch.setattr(bootstrap, "get_global_skill_path", lambda: global_skill_path)
    monkeypatch.setattr(bootstrap, "get_global_shell_env_path", lambda: global_shell_env_path)
    monkeypatch.setattr(bootstrap, "get_global_command_wrapper_path", lambda: global_wrapper_path)
    monkeypatch.setattr(bootstrap, "get_global_settings_path", lambda: global_settings_path)
    monkeypatch.setattr(bootstrap, "get_shell_profile_paths", lambda: [zprofile_path, zshrc_path])
    monkeypatch.setattr(bootstrap, "remove_windows_user_path", lambda wrapper_dir: "skipped")

    result = bootstrap.uninstall_workspace(workspace_path=tmp_path, scope="global")

    mcp_config = json.loads(global_mcp_path.read_text(encoding="utf-8"))

    assert result["scope"] == "global"
    assert result["global"]["mcp_status"] == "updated"
    assert result["global"]["instructions_status"] == "updated"
    assert result["global"]["legacy_instructions_status"] == "updated"
    assert result["global"]["skill_status"] == "deleted"
    assert result["global"]["settings_status"] == "deleted"
    assert result["global"]["shell_env_status"] == "deleted"
    assert result["global"]["command_wrapper_status"] == "deleted"
    assert result["global"]["windows_user_path_status"] == "skipped"
    assert "olinkb" not in mcp_config["servers"]
    assert "engram" in mcp_config["servers"]
    assert "## OlinKB Memory Protocol" not in global_instructions_path.read_text(encoding="utf-8")
    assert legacy_instructions_path.exists()
    assert "## OlinKB Memory Protocol" not in legacy_instructions_path.read_text(encoding="utf-8")
    assert not global_skill_path.exists()
    assert not global_shell_env_path.exists()
    assert not global_wrapper_path.exists()
    assert not global_settings_path.exists()
    assert bootstrap.ENVIRONMENT_BLOCK_MARKER not in zprofile_path.read_text(encoding="utf-8")
    assert bootstrap.ENVIRONMENT_BLOCK_MARKER not in zshrc_path.read_text(encoding="utf-8")


def test_run_uninstall_command_removes_python_packages_by_default(monkeypatch, tmp_path, capsys) -> None:
    parser = build_parser()
    args = parser.parse_args(["uninstall", "--workspace-path", str(tmp_path)])
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        cli,
        "uninstall_workspace",
        lambda **kwargs: {
            "scope": kwargs["scope"],
            "repository": {"viewer_status": "missing"},
            "global": {"settings_status": "missing"},
        },
    )
    monkeypatch.setattr(
        cli,
        "uninstall_python_packages",
        lambda: calls.append({"called": True}) or {"status": "uninstalled", "details": "ok"},
    )

    exit_code = cli.run_uninstall_command(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [{"called": True}]
    assert "Uninstall scope: all" in output
    assert "Python packages: uninstalled" in output


def test_run_uninstall_command_can_skip_python_package_removal(monkeypatch, tmp_path, capsys) -> None:
    parser = build_parser()
    args = parser.parse_args(["uninstall", "--workspace-path", str(tmp_path), "--skip-package-uninstall"])

    monkeypatch.setattr(
        cli,
        "uninstall_workspace",
        lambda **kwargs: {
            "scope": kwargs["scope"],
            "repository": {"viewer_status": "missing"},
            "global": {"settings_status": "missing"},
        },
    )
    monkeypatch.setattr(
        cli,
        "uninstall_python_packages",
        lambda: (_ for _ in ()).throw(AssertionError("package uninstall should be skipped")),
    )

    exit_code = cli.run_uninstall_command(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Python packages: skipped" in output


def test_run_init_workspace_global_scope_leaves_repo_instruction_files_untouched(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(["--init", "--workspace-path", str(tmp_path), "--scope", "global", "--mode", "cli"])
    global_mcp_path = tmp_path / "user-mcp.json"
    global_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions.md"
    global_skill_path = tmp_path / "user-home" / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
    global_shell_env_path = tmp_path / "user-home" / ".config" / "olinkb" / "env.sh"
    global_wrapper_path = tmp_path / "user-home" / ".local" / "bin" / "olinkb"
    global_settings_path = tmp_path / "user-home" / ".config" / "olinkb" / "settings.json"
    github_dir = tmp_path / ".github"
    copilot_dir = tmp_path / ".copilot"
    github_dir.mkdir()
    copilot_dir.mkdir()

    github_instructions = github_dir / "copilot-instructions.md"
    github_instructions.write_text("# Repo Rules\n", encoding="utf-8")
    copilot_instructions = copilot_dir / "instructions.md"
    copilot_instructions.write_text("# Local Tooling Rules\n", encoding="utf-8")

    def fake_input(prompt: str) -> str:
        if prompt.startswith("Storage backend"):
            return "1"
        if prompt.startswith("PostgreSQL URL"):
            return "postgresql://user:pass@db.example.com:5432/olinkb"
        if prompt.startswith("Team"):
            return "example-team"
        raise AssertionError(f"Unexpected prompt: {prompt}")

    monkeypatch.setattr(cli, "_get_optional_settings", lambda: None)
    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr(bootstrap, "get_global_instructions_path", lambda: global_instructions_path)
    monkeypatch.setattr(bootstrap, "get_global_skill_path", lambda: global_skill_path)
    monkeypatch.setattr(bootstrap, "get_global_shell_env_path", lambda: global_shell_env_path)
    monkeypatch.setattr(bootstrap, "get_global_command_wrapper_path", lambda: global_wrapper_path)
    monkeypatch.setattr(bootstrap, "get_global_settings_path", lambda: global_settings_path)
    monkeypatch.setattr(bootstrap, "get_shell_profile_paths", lambda: [])
    monkeypatch.setattr("builtins.input", fake_input)

    exit_code = cli.run_init_workspace(args)

    assert exit_code == 0
    assert global_instructions_path.exists()
    assert global_skill_path.exists()
    assert global_shell_env_path.exists()
    assert global_wrapper_path.exists()
    assert global_settings_path.exists()
    assert github_instructions.read_text(encoding="utf-8") == "# Repo Rules\n"
    assert copilot_instructions.read_text(encoding="utf-8") == "# Local Tooling Rules\n"


def test_global_bootstrap_removes_legacy_olinkb_protocol_block(tmp_path, monkeypatch) -> None:
    global_mcp_path = tmp_path / "user-mcp.json"
    global_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions" / bootstrap.INSTRUCTIONS_FILENAME
    legacy_instructions_path = tmp_path / "user-home" / ".copilot" / "instructions.md"
    global_skill_path = tmp_path / "user-home" / ".copilot" / "skills" / bootstrap.MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
    legacy_instructions_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_instructions_path.write_text(
        "# User Rules\n\n## OlinKB Memory Protocol\n\nOld MCP guidance.\n\n## Keep\n\nKeep this section.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bootstrap, "get_global_mcp_config_path", lambda: global_mcp_path)
    monkeypatch.setattr(bootstrap, "get_global_instructions_path", lambda: global_instructions_path)
    monkeypatch.setattr(bootstrap, "get_global_skill_path", lambda: global_skill_path)
    monkeypatch.setattr(bootstrap, "get_legacy_global_instructions_path", lambda: legacy_instructions_path)

    bootstrap.bootstrap_workspace(
        workspace_path=tmp_path,
        pg_url="postgresql://user:pass@db.example.com:5432/olinkb",
        team="example-team",
        scope="global",
        mode="cli",
    )

    assert global_instructions_path.exists()
    legacy_contents = legacy_instructions_path.read_text(encoding="utf-8")
    assert "## OlinKB Memory Protocol" not in legacy_contents
    assert "Keep this section." in legacy_contents