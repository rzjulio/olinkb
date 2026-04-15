from __future__ import annotations

import argparse
import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from olinkb.config import SettingsError, get_settings
from olinkb.tool_handlers import TOOL_NAMES


PostgresStorage = None
SqliteStorage = None


def bootstrap_workspace(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from olinkb.bootstrap import bootstrap_workspace as bootstrap_workspace_impl

    return bootstrap_workspace_impl(*args, **kwargs)


def uninstall_workspace(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from olinkb.bootstrap import uninstall_workspace as uninstall_workspace_impl

    return uninstall_workspace_impl(*args, **kwargs)


def run_server() -> None:
    from olinkb.server import run_server as run_server_impl

    run_server_impl()


def render_instructions_template(*args: Any, **kwargs: Any) -> str:
    from olinkb.templates import render_instructions_template as render_instructions_template_impl

    return render_instructions_template_impl(*args, **kwargs)


def render_mcp_template(*args: Any, **kwargs: Any) -> str:
    from olinkb.templates import render_mcp_template as render_mcp_template_impl

    return render_mcp_template_impl(*args, **kwargs)


def build_empty_viewer_payload() -> dict[str, Any]:
    from olinkb.viewer import build_empty_viewer_payload as build_empty_viewer_payload_impl

    return build_empty_viewer_payload_impl()


def build_viewer_output(*args: Any, **kwargs: Any) -> Path:
    from olinkb.viewer import build_viewer_output as build_viewer_output_impl

    return build_viewer_output_impl(*args, **kwargs)


def render_viewer_html(*args: Any, **kwargs: Any) -> str:
    from olinkb.viewer import render_viewer_html as render_viewer_html_impl

    return render_viewer_html_impl(*args, **kwargs)


def run_live_viewer_server(*args: Any, **kwargs: Any) -> None:
    from olinkb.viewer_server import run_live_viewer_server as run_live_viewer_server_impl

    run_live_viewer_server_impl(*args, **kwargs)


def run_tool_command(*args: Any, **kwargs: Any) -> int:
    from olinkb.tool_cli import run_tool_command as run_tool_command_impl

    return run_tool_command_impl(*args, **kwargs)


def _get_postgres_storage_class():
    global PostgresStorage
    if PostgresStorage is None:
        from olinkb.storage.postgres import PostgresStorage as postgres_storage_class

        PostgresStorage = postgres_storage_class
    return PostgresStorage


def _get_sqlite_storage_class():
    global SqliteStorage
    if SqliteStorage is None:
        from olinkb.storage.sqlite import SqliteStorage as sqlite_storage_class

        SqliteStorage = sqlite_storage_class
    return SqliteStorage


def _build_storage(settings: Any):
    if getattr(settings, "storage_backend", "postgres") == "sqlite":
        storage_class = _get_sqlite_storage_class()
        return storage_class(getattr(settings, "sqlite_path", None))

    storage_class = _get_postgres_storage_class()
    return storage_class(
        settings.pg_url,
        pool_max_size=getattr(settings, "pg_pool_max_size", 5),
    )


def _default_sqlite_path(workspace_root: Path, scope: str) -> Path:
    if scope == "repository":
        return workspace_root / ".olinkb" / "olinkb.db"
    return Path.home() / ".config" / "olinkb" / "olinkb.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olinkb", description="OlinKB MCP server utilities")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Interactively initialize OlinKB for this repository or globally in VS Code",
    )
    parser.add_argument(
        "--scope",
        choices=["repository", "global"],
        help="Install OlinKB for the current repository or globally in VS Code",
    )
    parser.add_argument(
        "--mode",
        choices=["mcp", "cli"],
        help="Choose MCP transport or the direct CLI transport during bootstrap",
    )
    parser.add_argument("--workspace-path", default=".", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the OlinKB MCP server over stdio")
    subparsers.add_parser("mcp", help="Alias for serving the OlinKB MCP server over stdio")
    subparsers.add_parser("migrate", help="Apply storage migrations for the configured backend")

    benchmark = subparsers.add_parser("benchmark", help="Measure payload savings for lean and hybrid memory payloads")
    benchmark.add_argument("--sample-size", type=int, default=200)
    benchmark.add_argument("--boot-limit", type=int, default=40)
    benchmark.add_argument("--boot-full-content-limit", type=int, default=5)
    benchmark.add_argument("--username")
    benchmark.add_argument("--project")

    add_member = subparsers.add_parser("add-member", help="Create or update a team member")
    add_member.add_argument("--username", required=True)
    add_member.add_argument("--team")
    add_member.add_argument("--role", default="developer")
    add_member.add_argument("--display-name")

    add_project_member = subparsers.add_parser("add-project-member", help="Create or update a project member")
    add_project_member.add_argument("--username", required=True)
    add_project_member.add_argument("--project", required=True)
    add_project_member.add_argument("--team")
    add_project_member.add_argument("--role", default="developer")
    add_project_member.add_argument("--display-name")

    viewer = subparsers.add_parser(
        "viewer",
        help="Run the live HTTP viewer by default, or export a static snapshot",
    )
    viewer.set_defaults(viewer_command="serve")
    viewer_subparsers = viewer.add_subparsers(dest="viewer_command")
    viewer_build = viewer_subparsers.add_parser(
        "build",
        help="Export a static HTML snapshot for sharing or archival",
    )
    viewer_build.add_argument("--output", default="olinkb-viewer/index.html")
    viewer_build.add_argument("--title", default="OlinKB Viewer")
    viewer_serve = viewer_subparsers.add_parser(
        "serve",
        help="Run the live HTTP viewer using the configured storage backend",
    )
    viewer_serve.add_argument("--host", default="127.0.0.1")
    viewer_serve.add_argument("--port", type=int, default=8123)
    viewer_serve.add_argument("--title", default="OlinKB Viewer")

    template = subparsers.add_parser("template", help="Render integration templates for VS Code and repo instructions")
    template_subparsers = template.add_subparsers(dest="template_name", required=True)

    template_mcp = template_subparsers.add_parser("mcp", help="Render a VS Code mcp.json snippet")
    template_mcp.add_argument("--pg-url")
    template_mcp.add_argument("--team")
    template_mcp.add_argument("--user-env", default="${env:USER}")
    template_mcp.add_argument("--project")

    template_instructions = template_subparsers.add_parser("instructions", help="Render repository instructions for automatic OlinKB usage")
    template_instructions.add_argument("--mode", choices=["mcp", "cli"], default="mcp")

    tool = subparsers.add_parser("tool", help="Run OlinKB through the direct CLI JSON transport")
    tool.add_argument("tool_name", choices=TOOL_NAMES)
    tool.add_argument("--json", dest="json_input")
    tool.add_argument("--input-file")

    uninstall = subparsers.add_parser("uninstall", help="Remove OlinKB bootstrap artifacts and uninstall Python packages")
    uninstall.add_argument("--scope", choices=["repository", "global", "all"], default="all")
    uninstall.add_argument("--workspace-path", default=".")
    uninstall.add_argument("--skip-package-uninstall", action="store_true")

    return parser


def _get_optional_settings():
    try:
        return get_settings()
    except SettingsError:
        return None


def _apply_command_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if args.command == "viewer" and args.viewer_command is None:
        args.viewer_command = "serve"
    if args.command == "viewer" and args.viewer_command == "serve":
        if not hasattr(args, "host"):
            args.host = "127.0.0.1"
        if not hasattr(args, "port"):
            args.port = 8123
        if not hasattr(args, "title"):
            args.title = "OlinKB Viewer"
    return args


def _prompt_required_value(label: str, default: str | None = None) -> str:
    prompt = f"{label}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "

    while True:
        value = input(prompt).strip()
        if value:
            return value
        if default:
            return default
        print(f"{label} is required.")


def _prompt_choice(label: str, choices: tuple[str, ...], default: str) -> str:
    indexed_choices = {str(index): choice for index, choice in enumerate(choices, start=1)}
    allowed = {choice.lower(): choice for choice in choices}
    allowed.update(indexed_choices)
    default_key = next(key for key, value in indexed_choices.items() if value == default)
    numbered_choices = " / ".join(f"{index} {choice}" for index, choice in indexed_choices.items())
    prompt = f"{label} [{numbered_choices}] [{default_key}]: "

    while True:
        value = input(prompt).strip().lower()
        if not value:
            return default
        if value in allowed:
            return allowed[value]
        print(f"Choose one of: {', '.join(indexed_choices.keys())}")


def _mcp_addon_installed() -> bool:
    return importlib.util.find_spec("olinkb_mcp") is not None


def resolve_bootstrap_mode(explicit_mode: str | None = None) -> str:
    if explicit_mode is not None:
        return explicit_mode
    return "mcp" if _mcp_addon_installed() else "cli"


async def _run_admin_command(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = _build_storage(settings)
    await storage.connect()
    try:
        if args.command == "migrate":
            applied = await storage.run_migrations()
            if applied:
                print("Applied migrations:")
                for migration in applied:
                    print(f"- {migration}")
            else:
                print("No pending migrations")
            return 0

        if args.command == "add-member":
            member = await storage.create_or_update_member(
                username=args.username,
                display_name=args.display_name,
                role=args.role,
                team=args.team or settings.team,
            )
            print(f"Member ready: {member['username']} ({member['role']}) on team {member['team']}")
            return 0

        if args.command == "add-project-member":
            member = await storage.ensure_member(username=args.username, team=args.team or settings.team)
            project_member = await storage.create_or_update_project_member(
                member_id=member["id"],
                username=args.username,
                project=args.project,
                team=args.team or member["team"],
                role=args.role,
            )
            print(
                f"Project member ready: {project_member['username']} ({project_member['role']}) "
                f"on project {project_member['project']}"
            )
            return 0

        if args.command == "benchmark":
            benchmark = await storage.benchmark_payloads(
                username=args.username or settings.user,
                project=args.project if args.project is not None else settings.default_project,
                sample_size=args.sample_size,
                boot_limit=args.boot_limit,
                boot_full_content_limit=args.boot_full_content_limit,
            )
            print("Payload benchmark")
            print(
                "- Boot full vs hybrid: "
                f"{benchmark['boot']['full']['approx_tokens']} -> {benchmark['boot']['hybrid']['approx_tokens']} approx tokens "
                f"({benchmark['boot']['savings']['approx_tokens']} saved, {benchmark['boot']['savings']['token_pct']}%)"
            )
            print(
                "- Memory sample full vs lean: "
                f"{benchmark['sample']['full']['approx_tokens']} -> {benchmark['sample']['lean']['approx_tokens']} approx tokens "
                f"({benchmark['sample']['savings']['approx_tokens']} saved, {benchmark['sample']['savings']['token_pct']}%)"
            )
            print(
                "- Bytes full vs hybrid boot: "
                f"{benchmark['boot']['full']['bytes']} -> {benchmark['boot']['hybrid']['bytes']} "
                f"({benchmark['boot']['savings']['bytes']} saved, {benchmark['boot']['savings']['byte_pct']}%)"
            )
            return 0

        if args.command == "viewer" and args.viewer_command == "build":
            snapshot = await storage.export_viewer_snapshot()
            output_path = build_viewer_output(snapshot, args.output, title=args.title)
            print(f"Static viewer snapshot written to {output_path}")
            print("For large-scale exploration, use: olinkb viewer")
            return 0

        raise ValueError(f"Unsupported command: {args.command}")
    finally:
        await storage.close()


def render_template_output(args: argparse.Namespace) -> str:
    if args.template_name == "instructions":
        return render_instructions_template(mode=args.mode)

    pg_url = getattr(args, "pg_url", None)
    sqlite_path = getattr(args, "sqlite_path", None)
    storage_backend = getattr(args, "storage_backend", None)
    team = getattr(args, "team", None)
    project = getattr(args, "project", None)
    user_env = getattr(args, "user_env", "${env:USER}")

    if storage_backend is None:
        if pg_url:
            storage_backend = "postgres"
        elif sqlite_path:
            storage_backend = "sqlite"

    settings = None
    if (storage_backend == "postgres" and not pg_url) or (storage_backend == "sqlite" and not sqlite_path) or not team or storage_backend is None:
        settings = get_settings()

    resolved_backend = storage_backend or settings.storage_backend

    return render_mcp_template(
        storage_backend=resolved_backend,
        pg_url=pg_url or (settings.pg_url if settings is not None else None),
        sqlite_path=sqlite_path or (str(settings.sqlite_path) if settings is not None and settings.sqlite_path is not None else None),
        team=team or settings.team,
        user_env=user_env,
        project=project if project is not None else (settings.default_project if settings is not None else None),
    )


def run_init_workspace(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_path).resolve()
    settings = _get_optional_settings()
    scope = args.scope or _prompt_choice("Install scope", ("repository", "global"), default="repository")

    if scope == "repository":
        print(f"Initializing OlinKB for: {workspace_root}")
        print(f"Detected project: {workspace_root.name}")
    else:
        print("Initializing OlinKB for global VS Code usage")

    default_backend = getattr(settings, "storage_backend", "postgres") if settings is not None else "postgres"
    storage_backend = _prompt_choice(
        "Storage backend",
        ("postgres", "sqlite"),
        default=default_backend,
    )

    pg_url: str | None = None
    sqlite_path: Path | None = None
    if storage_backend == "postgres":
        pg_url = _prompt_required_value(
            "PostgreSQL URL",
            default=settings.pg_url if settings is not None and settings.storage_backend == "postgres" else None,
        )
    else:
        sqlite_path = Path(
            _prompt_required_value(
                "SQLite path",
                default=str(
                    settings.sqlite_path
                    if settings is not None and settings.storage_backend == "sqlite" and settings.sqlite_path is not None
                    else _default_sqlite_path(workspace_root, scope)
                ),
            )
        ).expanduser()

    team = _prompt_required_value(
        "Team",
        default=settings.team if settings is not None else None,
    )
    mode = resolve_bootstrap_mode(args.mode)

    result = bootstrap_workspace(
        workspace_path=workspace_root,
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        scope=scope,
        mode=mode,
    )
    print(f"Initialization scope: {result['scope']}")
    print(f"- Mode: {result['mode']}")
    print(f"- Storage backend: {result['storage_backend']}")
    if result["project"]:
        print(f"- Project: {result['project']}")
    if result["mcp_path"]:
        print(f"- MCP config: {result['mcp_path']}")
    else:
        print("- MCP config: skipped")
    if result["instructions_path"]:
        print(f"- Instructions: {result['instructions_path']}")
    else:
        print("- Instructions: skipped for global install")
    if result.get("prompt_path"):
        print(f"- Prompt: {result['prompt_path']}")
    else:
        print("- Prompt: skipped")
    print(f"- Skill: {result['skill_path']}")
    print(f"- Persisted settings: {result['settings_path']}")
    print(f"- Shell env script: {result['shell_env_path']}")
    print(f"- Global command wrapper: {result['command_wrapper_path']}")
    if result["windows_user_path_status"] != "skipped":
        print(f"- Windows user PATH: {result['windows_user_path_status']}")
        print("- Open a new terminal to pick up the global command from the updated user PATH.")
    if result["shell_profile_paths"]:
        print("- Shell profiles updated:")
        for profile_path in result["shell_profile_paths"]:
            print(f"  - {profile_path}")
        print("- Open a new terminal to pick up the global command and exported environment variables.")
    return 0


def uninstall_python_packages() -> dict[str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "olinkb", "olinkb-mcp"],
        capture_output=True,
        text=True,
    )
    details = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).strip()
    if result.returncode == 0:
        return {"status": "uninstalled", "details": details}
    return {"status": "failed", "details": details or f"pip exited with status {result.returncode}"}


def run_uninstall_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_path).resolve()
    result = uninstall_workspace(workspace_path=workspace_root, scope=args.scope)

    print(f"Uninstall scope: {result['scope']}")
    for scope_name in ("repository", "global"):
        scope_result = result.get(scope_name)
        if not scope_result:
            continue
        print(f"- {scope_name.title()} cleanup:")
        for key, value in scope_result.items():
            if key.endswith("_paths") or key.endswith("_statuses"):
                continue
            print(f"  - {key}: {value}")

    if args.skip_package_uninstall:
        print("Python packages: skipped")
        return 0

    package_result = uninstall_python_packages()
    print(f"Python packages: {package_result['status']}")
    if package_result["status"] == "failed" and package_result["details"]:
        print(package_result["details"], file=sys.stderr)
        return 1
    return 0


def ensure_viewer_scaffold(workspace_path: str | Path = ".") -> Path:
    workspace_root = Path(workspace_path).resolve()
    viewer_dir = workspace_root / "olinkb-viewer"
    viewer_dir.mkdir(parents=True, exist_ok=True)

    index_path = viewer_dir / "index.html"
    if not index_path.exists():
        index_path.write_text(render_viewer_html(build_empty_viewer_payload()), encoding="utf-8")

    readme_path = viewer_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "# OlinKB Viewer\n\n"
            "Static read-only snapshot artifact for OlinKB.\n\n"
            "For large-scale exploration, use the live viewer:\n\n"
            "```bash\n"
            "olinkb viewer\n"
            "```\n\n"
            "Generate a fresh snapshot only when you need a portable point-in-time export:\n\n"
            "```bash\n"
            "olinkb viewer build\n"
            "```\n",
            encoding="utf-8",
        )

    return viewer_dir


def main() -> int:
    parser = build_parser()
    args = _apply_command_defaults(parser.parse_args())

    if args.init or args.command == "viewer":
        ensure_viewer_scaffold(args.workspace_path)

    if args.init:
        return run_init_workspace(args)

    if args.command is None:
        parser.error("a command or --init is required")

    if args.command in {"serve", "mcp"}:
        try:
            run_server()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "viewer" and args.viewer_command == "serve":
        run_live_viewer_server(host=args.host, port=args.port, title=args.title)
        return 0

    if args.command == "template":
        print(render_template_output(args))
        return 0

    if args.command == "tool":
        return run_tool_command(args)

    if args.command == "uninstall":
        return run_uninstall_command(args)

    return asyncio.run(_run_admin_command(args))


if __name__ == "__main__":
    raise SystemExit(main())