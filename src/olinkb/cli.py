from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from olinkb.bootstrap import bootstrap_workspace
from olinkb.config import SettingsError, get_settings
from olinkb.server import run_server
from olinkb.storage.postgres import PostgresStorage
from olinkb.templates import render_instructions_template, render_mcp_template
from olinkb.viewer import build_empty_viewer_payload, build_viewer_output, render_viewer_html
from olinkb.viewer_server import run_live_viewer_server


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
    parser.add_argument("--workspace-path", default=".", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the OlinKB MCP server over stdio")
    subparsers.add_parser("mcp", help="Alias for serving the OlinKB MCP server over stdio")
    subparsers.add_parser("migrate", help="Apply PostgreSQL migrations")

    add_member = subparsers.add_parser("add-member", help="Create or update a team member")
    add_member.add_argument("--username", required=True)
    add_member.add_argument("--team")
    add_member.add_argument("--role", default="developer")
    add_member.add_argument("--display-name")

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
        help="Run the live HTTP viewer backed directly by PostgreSQL",
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

    template_subparsers.add_parser("instructions", help="Render repository instructions for automatic OlinKB usage")

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


async def _run_admin_command(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = PostgresStorage(settings.pg_url)
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
        return render_instructions_template()

    pg_url = getattr(args, "pg_url", None)
    team = getattr(args, "team", None)
    project = getattr(args, "project", None)
    user_env = getattr(args, "user_env", "${env:USER}")

    settings = None
    if not pg_url or not team:
        settings = get_settings()

    return render_mcp_template(
        pg_url=pg_url or settings.pg_url,
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

    pg_url = _prompt_required_value(
        "PostgreSQL URL",
        default=settings.pg_url if settings is not None else None,
    )
    team = _prompt_required_value(
        "Team",
        default=settings.team if settings is not None else None,
    )

    result = bootstrap_workspace(
        workspace_path=workspace_root,
        pg_url=pg_url,
        team=team,
        scope=scope,
    )
    print(f"Initialization scope: {result['scope']}")
    if result["project"]:
        print(f"- Project: {result['project']}")
    print(f"- MCP config: {result['mcp_path']}")
    if result["instructions_path"]:
        print(f"- Instructions: {result['instructions_path']}")
    else:
        print("- Instructions: skipped for global install")
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
        run_server()
        return 0

    if args.command == "viewer" and args.viewer_command == "serve":
        run_live_viewer_server(host=args.host, port=args.port, title=args.title)
        return 0

    if args.command == "template":
        print(render_template_output(args))
        return 0

    return asyncio.run(_run_admin_command(args))


if __name__ == "__main__":
    raise SystemExit(main())