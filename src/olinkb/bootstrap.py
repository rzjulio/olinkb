from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from olinkb.templates import render_instructions_template, render_mcp_template


PROTOCOL_HEADER = "## OlinKB Memory Protocol"
PROTOCOL_BLOCK_PATTERN = re.compile(
    r"(?ms)^## OlinKB Memory Protocol\n.*?(?=^##\s|\Z)"
)


def detect_project_name(workspace_path: str | Path) -> str | None:
    workspace_root = Path(workspace_path).resolve()
    return workspace_root.name or None


def get_global_mcp_config_path() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Code" / "User" / "mcp.json"
        return home / "AppData" / "Roaming" / "Code" / "User" / "mcp.json"
    return home / ".config" / "Code" / "User" / "mcp.json"


def bootstrap_workspace(
    *,
    workspace_path: str | Path,
    pg_url: str,
    team: str,
    scope: str = "repository",
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace_path).resolve()
    if scope not in {"repository", "global"}:
        raise ValueError(f"Unsupported bootstrap scope: {scope}")

    resolved_project = None
    if scope == "repository":
        resolved_project = project if project is not None else detect_project_name(workspace_root)

    mcp_path = get_global_mcp_config_path() if scope == "global" else workspace_root / ".vscode" / "mcp.json"
    instructions_path = None if scope == "global" else workspace_root / ".github" / "copilot-instructions.md"

    mcp_document = merge_mcp_document(
        mcp_path=mcp_path,
        pg_url=pg_url,
        team=team,
        user_env=user_env,
        project=resolved_project,
    )
    instructions_text = None
    instructions_status = "skipped"
    if instructions_path is not None:
        instructions_text, instructions_status = merge_instructions_document(instructions_path)

    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(mcp_document, indent=2) + "\n", encoding="utf-8")

    if instructions_path is not None and instructions_text is not None:
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        instructions_path.write_text(instructions_text, encoding="utf-8")

    return {
        "scope": scope,
        "workspace": str(workspace_root),
        "project": resolved_project,
        "mcp_path": str(mcp_path),
        "instructions_path": str(instructions_path) if instructions_path is not None else None,
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
    if PROTOCOL_HEADER in existing:
        updated = PROTOCOL_BLOCK_PATTERN.sub(protocol_block, existing, count=1)
        if updated == existing:
            if existing.endswith("\n"):
                return existing, "unchanged"
            return existing + "\n", "unchanged"
        if updated.endswith("\n"):
            return updated, "updated"
        return updated + "\n", "updated"

    separator = "\n\n" if existing.strip() else ""
    return existing.rstrip() + separator + protocol_block + "\n", "updated"