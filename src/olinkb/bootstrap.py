from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from olinkb.templates import render_instructions_template, render_mcp_template


def bootstrap_workspace(
    *,
    workspace_path: str | Path,
    pg_url: str,
    team: str,
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace_path).resolve()
    mcp_path = workspace_root / ".vscode" / "mcp.json"
    instructions_path = workspace_root / ".github" / "copilot-instructions.md"

    mcp_document = merge_mcp_document(
        mcp_path=mcp_path,
        pg_url=pg_url,
        team=team,
        user_env=user_env,
        project=project,
    )
    instructions_text, instructions_status = merge_instructions_document(instructions_path)

    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(mcp_document, indent=2) + "\n", encoding="utf-8")

    instructions_path.parent.mkdir(parents=True, exist_ok=True)
    instructions_path.write_text(instructions_text, encoding="utf-8")

    return {
        "workspace": str(workspace_root),
        "mcp_path": str(mcp_path),
        "instructions_path": str(instructions_path),
        "mcp_status": "updated" if mcp_path.exists() else "created",
        "instructions_status": instructions_status,
    }


def merge_mcp_document(
    *,
    mcp_path: str | Path,
    pg_url: str,
    team: str,
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> dict[str, Any]:
    destination = Path(mcp_path)
    document: dict[str, Any] = {}
    if destination.exists():
        document = json.loads(destination.read_text(encoding="utf-8"))

    servers = document.setdefault("servers", {})
    olinkb_document = json.loads(
        render_mcp_template(
            pg_url=pg_url,
            team=team,
            user_env=user_env,
            project=project,
        )
    )
    servers["olinkb"] = olinkb_document["servers"]["olinkb"]
    return document


def merge_instructions_document(instructions_path: str | Path) -> tuple[str, str]:
    destination = Path(instructions_path)
    protocol_block = render_instructions_template().strip()
    if not destination.exists():
        return protocol_block + "\n", "created"

    existing = destination.read_text(encoding="utf-8")
    if "## OlinKB Memory Protocol" in existing:
        if existing.endswith("\n"):
            return existing, "unchanged"
        return existing + "\n", "unchanged"

    separator = "\n\n" if existing.strip() else ""
    return existing.rstrip() + separator + protocol_block + "\n", "updated"