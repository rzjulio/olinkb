from __future__ import annotations

import argparse
import asyncio

from olinkb.bootstrap import bootstrap_workspace
from olinkb.config import get_settings
from olinkb.server import run_server
from olinkb.storage.postgres import PostgresStorage
from olinkb.templates import render_instructions_template, render_mcp_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olinkb", description="OlinKB MCP server utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Run the OlinKB MCP server over stdio")
    subparsers.add_parser("mcp", help="Alias for serving the OlinKB MCP server over stdio")
    subparsers.add_parser("migrate", help="Apply PostgreSQL migrations")

    setup = subparsers.add_parser(
        "setup-workspace",
        help="Write VS Code MCP config and repository instructions for this workspace",
    )
    setup.add_argument("--pg-url")
    setup.add_argument("--team")
    setup.add_argument("--user-env", default="${env:USER}")
    setup.add_argument("--project")
    setup.add_argument("--workspace-path", default=".")

    add_member = subparsers.add_parser("add-member", help="Create or update a team member")
    add_member.add_argument("--username", required=True)
    add_member.add_argument("--team")
    add_member.add_argument("--role", default="developer")
    add_member.add_argument("--display-name")

    template = subparsers.add_parser("template", help="Render integration templates for VS Code and repo instructions")
    template_subparsers = template.add_subparsers(dest="template_name", required=True)

    template_mcp = template_subparsers.add_parser("mcp", help="Render a VS Code mcp.json snippet")
    template_mcp.add_argument("--pg-url")
    template_mcp.add_argument("--team")
    template_mcp.add_argument("--user-env", default="${env:USER}")
    template_mcp.add_argument("--project")

    template_subparsers.add_parser("instructions", help="Render repository instructions for automatic OlinKB usage")

    return parser


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


def run_setup_workspace(args: argparse.Namespace) -> int:
    pg_url = getattr(args, "pg_url", None)
    team = getattr(args, "team", None)
    project = getattr(args, "project", None)
    user_env = getattr(args, "user_env", "${env:USER}")

    settings = None
    if not pg_url or not team:
        settings = get_settings()

    result = bootstrap_workspace(
        workspace_path=args.workspace_path,
        pg_url=pg_url or settings.pg_url,
        team=team or settings.team,
        user_env=user_env,
        project=project if project is not None else (settings.default_project if settings is not None else None),
    )
    print(f"Workspace configured: {result['workspace']}")
    print(f"- MCP config: {result['mcp_path']}")
    print(f"- Instructions: {result['instructions_path']}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"serve", "mcp"}:
        run_server()
        return 0

    if args.command == "setup-workspace":
        return run_setup_workspace(args)

    if args.command == "template":
        print(render_template_output(args))
        return 0

    return asyncio.run(_run_admin_command(args))


if __name__ == "__main__":
    raise SystemExit(main())