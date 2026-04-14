from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from olinkb.templates import (
    render_instructions_template,
    render_mcp_template,
    render_memory_relevance_skill_template,
)


_NATIVE_PATH_CLASS = type(Path())


PROTOCOL_HEADER = "## OlinKB Memory Protocol"
MEMORY_RELEVANCE_SKILL_NAME = "memory-relevance-triage"
PROTOCOL_BLOCK_PATTERN = re.compile(
    r"(?ms)^## OlinKB Memory Protocol\n.*?(?=^##\s|\Z)"
)


def detect_project_name(workspace_path: str | Path) -> str | None:
    workspace_root = Path(workspace_path).resolve()
    return workspace_root.name or None


def _native_path(value: str | Path) -> Path:
    return _NATIVE_PATH_CLASS(value)


def _get_windows_roaming_path() -> Path:
    appdata = (os.environ.get("APPDATA") or "").strip()
    if appdata:
        return _native_path(appdata)

    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return _native_path(userprofile) / "AppData" / "Roaming"

    try:
        return _NATIVE_PATH_CLASS.home() / "AppData" / "Roaming"
    except RuntimeError as exc:
        raise RuntimeError(
            "Could not determine the Windows roaming profile path for the VS Code MCP configuration. "
            "Set APPDATA or USERPROFILE explicitly."
        ) from exc


def get_global_mcp_config_path() -> Path:
    if sys.platform == "darwin":
        home = _NATIVE_PATH_CLASS.home()
        return home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    if os.name == "nt":
        return _get_windows_roaming_path() / "Code" / "User" / "mcp.json"
    home = _NATIVE_PATH_CLASS.home()
    return home / ".config" / "Code" / "User" / "mcp.json"


def get_global_instructions_path() -> Path:
    return _NATIVE_PATH_CLASS.home() / ".copilot" / "instructions.md"


def get_global_skill_path() -> Path:
    return _NATIVE_PATH_CLASS.home() / ".copilot" / "skills" / MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"


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
    instructions_path = get_global_instructions_path() if scope == "global" else workspace_root / ".github" / "copilot-instructions.md"
    skill_path = get_global_skill_path() if scope == "global" else workspace_root / ".copilot" / "skills" / MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"

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
    skill_text, skill_status = merge_skill_document(skill_path)

    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(mcp_document, indent=2) + "\n", encoding="utf-8")

    if instructions_path is not None and instructions_text is not None:
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        instructions_path.write_text(instructions_text, encoding="utf-8")

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_text, encoding="utf-8")

    return {
        "scope": scope,
        "workspace": str(workspace_root),
        "project": resolved_project,
        "mcp_path": str(mcp_path),
        "instructions_path": str(instructions_path) if instructions_path is not None else None,
        "skill_path": str(skill_path),
        "mcp_status": "updated" if mcp_path.exists() else "created",
        "instructions_status": instructions_status,
        "skill_status": skill_status,
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


def merge_skill_document(skill_path: str | Path) -> tuple[str, str]:
    destination = Path(skill_path)
    skill_text = render_memory_relevance_skill_template().rstrip() + "\n"
    if not destination.exists():
        return skill_text, "created"

    existing = destination.read_text(encoding="utf-8")
    if existing == skill_text:
        return skill_text, "unchanged"
    return skill_text, "updated"