from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from olinkb.config import clear_settings_cache, get_persisted_settings_path
from olinkb.templates import (
    render_cli_mandatory_prompt_template,
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

INSTRUCTIONS_FILENAME = "olinkb-memory.instructions.md"
OLINKB_CLI_MANDATORY_PROMPT_FILENAME = "olinkb-cli-mandatory.prompt.md"
LEGACY_GLOBAL_INSTRUCTIONS_FILENAME = "instructions.md"
ENVIRONMENT_BLOCK_MARKER = "# >>> OlinKB environment >>>"
ENVIRONMENT_BLOCK_END_MARKER = "# <<< OlinKB environment <<<"


def get_legacy_global_instructions_path() -> Path:
    return _NATIVE_PATH_CLASS.home() / ".copilot" / LEGACY_GLOBAL_INSTRUCTIONS_FILENAME


def get_global_settings_path() -> Path:
    return get_persisted_settings_path()


def get_global_shell_env_path() -> Path:
    return get_global_settings_path().parent / "env.sh"


def get_global_command_wrapper_path() -> Path:
    if os.name == "nt":
        return _get_windows_local_appdata_path() / "olinkb" / "bin" / "olinkb.cmd"
    return _NATIVE_PATH_CLASS.home() / ".local" / "bin" / "olinkb"


def get_shell_profile_paths() -> list[Path]:
    shell_name = Path(os.environ.get("SHELL") or "").name
    home = _NATIVE_PATH_CLASS.home()
    if shell_name == "zsh":
        return [home / ".zprofile", home / ".zshrc"]
    if shell_name == "bash":
        return [home / ".bash_profile", home / ".bashrc"]
    if os.name != "nt":
        return [home / ".profile"]
    return []

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

def _get_windows_local_appdata_path() -> Path:
    localappdata = (os.environ.get("LOCALAPPDATA") or "").strip()
    if localappdata:
        return _native_path(localappdata)

    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return _native_path(userprofile) / "AppData" / "Local"

    try:
        return _NATIVE_PATH_CLASS.home() / "AppData" / "Local"
    except RuntimeError as exc:
        raise RuntimeError(
            "Could not determine the Windows local profile path for the OlinKB command wrapper. "
            "Set LOCALAPPDATA or USERPROFILE explicitly."
        ) from exc

def get_global_mcp_config_path() -> Path:
    if sys.platform == "darwin":
        home = _NATIVE_PATH_CLASS.home()
        return home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    if os.name == "nt":
        return _get_windows_roaming_path() / "Code" / "User" / "mcp.json"
    home = _NATIVE_PATH_CLASS.home()
    return home / ".config" / "Code" / "User" / "mcp.json"


def get_global_prompts_dir() -> Path:
    if sys.platform == "darwin":
        home = _NATIVE_PATH_CLASS.home()
        return home / "Library" / "Application Support" / "Code" / "User" / "prompts"
    if os.name == "nt":
        return _get_windows_roaming_path() / "Code" / "User" / "prompts"
    home = _NATIVE_PATH_CLASS.home()
    return home / ".config" / "Code" / "User" / "prompts"

def get_global_instructions_path() -> Path:
    return _NATIVE_PATH_CLASS.home() / ".copilot" / "instructions" / INSTRUCTIONS_FILENAME

def get_global_skill_path() -> Path:
    return _NATIVE_PATH_CLASS.home() / ".copilot" / "skills" / MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"


def get_global_cli_mandatory_prompt_path() -> Path:
    return get_global_prompts_dir() / OLINKB_CLI_MANDATORY_PROMPT_FILENAME

def bootstrap_workspace(
    *,
    workspace_path: str | Path,
    team: str,
    storage_backend: str = "postgres",
    pg_url: str | None = None,
    sqlite_path: str | Path | None = None,
    scope: str = "repository",
    mode: str = "cli",
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace_path).resolve()
    if scope not in {"repository", "global"}:
        raise ValueError(f"Unsupported bootstrap scope: {scope}")
    if mode not in {"mcp", "cli"}:
        raise ValueError(f"Unsupported bootstrap mode: {mode}")

    resolved_project = None
    if scope == "repository":
        resolved_project = project if project is not None else detect_project_name(workspace_root)

    mcp_path = get_global_mcp_config_path() if scope == "global" else workspace_root / ".vscode" / "mcp.json"
    instructions_path = get_global_instructions_path() if scope == "global" else workspace_root / ".github" / "copilot-instructions.md"
    prompt_path = get_global_cli_mandatory_prompt_path() if scope == "global" else None
    skill_path = get_global_skill_path() if scope == "global" else workspace_root / ".copilot" / "skills" / MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"

    mcp_document, mcp_status = merge_mcp_document(
        mcp_path=mcp_path,
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        user_env=user_env,
        project=resolved_project,
        enabled=mode == "mcp",
    )
    instructions_text = None
    instructions_status = "skipped"
    if instructions_path is not None:
        instructions_text, instructions_status = merge_instructions_document(instructions_path, mode=mode)
    prompt_text = None
    prompt_status = "skipped"
    if prompt_path is not None:
        prompt_text, prompt_status = merge_prompt_document(prompt_path)
    skill_text, skill_status = merge_skill_document(skill_path)

    if mcp_document is not None:
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(json.dumps(mcp_document, indent=2) + "\n", encoding="utf-8")

    if instructions_path is not None and instructions_text is not None:
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        instructions_path.write_text(instructions_text, encoding="utf-8")

    if prompt_path is not None and prompt_text is not None:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt_text, encoding="utf-8")

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_text, encoding="utf-8")

    settings_status = persist_settings_file(
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        project=resolved_project,
    )
    shell_env_status = persist_shell_env_file(
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        project=resolved_project,
    )
    command_wrapper_status = persist_command_wrapper()
    windows_user_path_status = persist_windows_user_path(get_global_command_wrapper_path().parent)
    shell_profiles = get_shell_profile_paths()
    shell_profile_statuses = persist_shell_profile_hooks(shell_profiles)
    clear_settings_cache()

    legacy_instructions_status = "skipped"
    if scope == "global":
        legacy_instructions_status = cleanup_legacy_global_instructions(get_legacy_global_instructions_path())

    return {
        "scope": scope,
        "mode": mode,
        "storage_backend": storage_backend,
        "workspace": str(workspace_root),
        "project": resolved_project,
        "mcp_path": str(mcp_path) if mode == "mcp" else None,
        "instructions_path": str(instructions_path) if instructions_path is not None else None,
        "prompt_path": str(prompt_path) if prompt_path is not None else None,
        "skill_path": str(skill_path),
        "mcp_status": mcp_status,
        "instructions_status": instructions_status,
        "prompt_status": prompt_status,
        "legacy_global_instructions_status": legacy_instructions_status,
        "skill_status": skill_status,
        "settings_path": str(get_global_settings_path()),
        "settings_status": settings_status,
        "shell_env_path": str(get_global_shell_env_path()),
        "shell_env_status": shell_env_status,
        "command_wrapper_path": str(get_global_command_wrapper_path()),
        "command_wrapper_status": command_wrapper_status,
        "windows_user_path_status": windows_user_path_status,
        "shell_profile_paths": [str(path) for path in shell_profiles],
        "shell_profile_statuses": shell_profile_statuses,
    }


def uninstall_workspace(
    *,
    workspace_path: str | Path,
    scope: str = "all",
) -> dict[str, Any]:
    workspace_root = Path(workspace_path).resolve()
    if scope not in {"repository", "global", "all"}:
        raise ValueError(f"Unsupported uninstall scope: {scope}")

    result: dict[str, Any] = {
        "scope": scope,
        "workspace": str(workspace_root),
    }

    if scope in {"repository", "all"}:
        result["repository"] = cleanup_repository_bootstrap(workspace_root)

    if scope in {"global", "all"}:
        result["global"] = cleanup_global_bootstrap()

    clear_settings_cache()
    return result


def _environment_document(
    *,
    storage_backend: str,
    team: str,
    pg_url: str | None = None,
    sqlite_path: str | Path | None = None,
    project: str | None = None,
) -> dict[str, str]:
    document = {
        "OLINKB_STORAGE_BACKEND": storage_backend,
        "OLINKB_TEAM": team,
    }
    if storage_backend == "postgres":
        if not pg_url:
            raise ValueError("PostgreSQL storage requires pg_url")
        document["OLINKB_PG_URL"] = pg_url
    elif storage_backend == "sqlite":
        if sqlite_path is None:
            raise ValueError("SQLite storage requires sqlite_path")
        document["OLINKB_SQLITE_PATH"] = str(Path(sqlite_path).expanduser())
    else:
        raise ValueError(f"Unsupported storage backend: {storage_backend}")
    if project:
        document["OLINKB_PROJECT"] = project
    return document


def persist_settings_file(
    *,
    storage_backend: str,
    team: str,
    pg_url: str | None = None,
    sqlite_path: str | Path | None = None,
    project: str | None = None,
) -> str:
    path = get_global_settings_path()
    document = _environment_document(
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        project=project,
    )
    content = json.dumps(document, indent=2) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == content:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created" if previous is None else "updated"


def delete_file_if_exists(path: str | Path, *, prune_parent: bool = False) -> str:
    destination = Path(path)
    if not destination.exists():
        return "missing"

    destination.unlink()
    if prune_parent:
        try:
            destination.parent.rmdir()
        except OSError:
            pass
    return "deleted"


def persist_shell_env_file(
    *,
    storage_backend: str,
    team: str,
    pg_url: str | None = None,
    sqlite_path: str | Path | None = None,
    project: str | None = None,
) -> str:
    path = get_global_shell_env_path()
    wrapper_dir = get_global_command_wrapper_path().parent
    exports = _environment_document(
        storage_backend=storage_backend,
        pg_url=pg_url,
        sqlite_path=sqlite_path,
        team=team,
        project=project,
    )
    lines = [
        "# Generated by OlinKB. Re-run `olinkb --init` to update.",
    ]
    if os.name != "nt":
        wrapper_dir_text = shlex.quote(str(wrapper_dir))
        lines.extend(
            [
                f'case ":$PATH:" in *":{wrapper_dir_text}:"*) ;; *) export PATH={wrapper_dir_text}:$PATH ;; esac',
            ]
        )
    for key, value in exports.items():
        lines.append(f"export {key}={shlex.quote(value)}")
    content = "\n".join(lines) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if previous is None:
        return "created"
    return "unchanged" if previous == content else "updated"


def persist_command_wrapper() -> str:
    path = get_global_command_wrapper_path()
    if os.name == "nt":
        content = f'@echo off\r\n"{sys.executable}" -m olinkb.cli %*\r\n'
    else:
        content = f'#!/bin/sh\nexec "{sys.executable}" -m olinkb.cli "$@"\n'
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    if previous is None:
        return "created"
    return "unchanged" if previous == content else "updated"


def remove_windows_user_path(wrapper_dir: Path) -> str:
    if os.name != "nt":
        return "skipped"

    existing = load_windows_user_path()
    if not existing:
        return "missing"

    wrapper_text = str(wrapper_dir)
    parts = [part for part in existing.split(os.pathsep) if part]
    filtered = [part for part in parts if part.lower() != wrapper_text.lower()]
    if len(filtered) == len(parts):
        return "unchanged"

    save_windows_user_path(os.pathsep.join(filtered))
    notify_windows_environment_change()
    return "updated"

def load_windows_user_path() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
        try:
            value, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return ""
    return value or ""

def save_windows_user_path(path_value: str) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, path_value)

def notify_windows_environment_change() -> None:
    user32 = getattr(__import__("ctypes").windll, "user32", None)
    if user32 is None:
        return
    hwnd_broadcast = 0xFFFF
    wm_settingchange = 0x001A
    smto_abortifhung = 0x0002
    user32.SendMessageTimeoutW(hwnd_broadcast, wm_settingchange, 0, "Environment", smto_abortifhung, 5000, None)

def persist_windows_user_path(wrapper_dir: Path) -> str:
    if os.name != "nt":
        return "skipped"

    wrapper_text = str(wrapper_dir)
    existing = load_windows_user_path()
    parts = [part for part in existing.split(os.pathsep) if part]
    if any(part.lower() == wrapper_text.lower() for part in parts):
        return "unchanged"

    updated = existing + (os.pathsep if existing else "") + wrapper_text
    save_windows_user_path(updated)
    notify_windows_environment_change()
    return "updated"


def persist_shell_profile_hooks(profile_paths: list[Path]) -> dict[str, str]:
    results: dict[str, str] = {}
    if os.name == "nt":
        return results

    env_path = get_global_shell_env_path()
    block = (
        f"{ENVIRONMENT_BLOCK_MARKER}\n"
        f'[ -f "{env_path}" ] && . "{env_path}"\n'
        f"{ENVIRONMENT_BLOCK_END_MARKER}"
    )
    pattern = re.compile(
        rf"(?ms)^{re.escape(ENVIRONMENT_BLOCK_MARKER)}\n.*?^{re.escape(ENVIRONMENT_BLOCK_END_MARKER)}\n?"
    )
    for path in profile_paths:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing and pattern.search(existing):
            updated = pattern.sub(block + "\n", existing, count=1)
        else:
            separator = "\n" if existing and not existing.endswith("\n") else ""
            updated = existing + separator + ("\n" if existing.strip() else "") + block + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        if not existing:
            results[str(path)] = "created"
        elif updated == existing:
            results[str(path)] = "unchanged"
        else:
            results[str(path)] = "updated"
    return results


def remove_shell_profile_hooks(profile_paths: list[Path]) -> dict[str, str]:
    results: dict[str, str] = {}
    if os.name == "nt":
        return results

    pattern = re.compile(
        rf"(?ms)^\n?{re.escape(ENVIRONMENT_BLOCK_MARKER)}\n.*?^{re.escape(ENVIRONMENT_BLOCK_END_MARKER)}\n?"
    )
    for path in profile_paths:
        if not path.exists():
            results[str(path)] = "missing"
            continue

        existing = path.read_text(encoding="utf-8")
        updated = pattern.sub("\n", existing, count=1)
        updated = re.sub(r"\n{3,}", "\n\n", updated)
        if updated != existing:
            path.write_text(updated.lstrip("\n"), encoding="utf-8")
            results[str(path)] = "updated"
        else:
            results[str(path)] = "unchanged"
    return results

def merge_mcp_document(
    *,
    mcp_path: str | Path,
    team: str,
    storage_backend: str = "postgres",
    pg_url: str | None = None,
    sqlite_path: str | Path | None = None,
    user_env: str = "${env:USER}",
    project: str | None = None,
    enabled: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    destination = Path(mcp_path)
    document: dict[str, Any] = {}
    if destination.exists():
        content = destination.read_text(encoding="utf-8").strip()
        if content:
            try:
                document = json.loads(content)
            except json.JSONDecodeError:
                document = {}

    servers = document.setdefault("servers", {})
    if not enabled:
        if "olinkb" in servers:
            del servers["olinkb"]
            return document, "removed"
        return (document, "unchanged") if destination.exists() else (None, "skipped")

    olinkb_document = json.loads(
        render_mcp_template(
            storage_backend=storage_backend,
            pg_url=pg_url,
            sqlite_path=str(Path(sqlite_path).expanduser()) if sqlite_path is not None else None,
            team=team,
            user_env=user_env,
            project=project,
        )
    )
    servers["olinkb"] = olinkb_document["servers"]["olinkb"]
    return document, "updated" if destination.exists() else "created"


def remove_olinkb_mcp_server(mcp_path: str | Path) -> str:
    destination = Path(mcp_path)
    if not destination.exists():
        return "missing"

    content = destination.read_text(encoding="utf-8").strip()
    if not content:
        destination.unlink()
        return "deleted"

    try:
        document = json.loads(content)
    except json.JSONDecodeError:
        return "unchanged"

    servers = document.get("servers")
    if not isinstance(servers, dict) or "olinkb" not in servers:
        return "unchanged"

    del servers["olinkb"]
    if servers:
        destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return "updated"

    remaining_keys = {key: value for key, value in document.items() if key != "servers"}
    if remaining_keys:
        document["servers"] = {}
        destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return "updated"

    destination.unlink()
    return "deleted"

def merge_instructions_document(instructions_path: str | Path, *, mode: str = "mcp") -> tuple[str, str]:
    destination = Path(instructions_path)
    protocol_block = render_instructions_template(mode=mode).strip()
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


def merge_prompt_document(prompt_path: str | Path) -> tuple[str, str]:
    destination = Path(prompt_path)
    prompt_text = render_cli_mandatory_prompt_template().rstrip() + "\n"
    if not destination.exists():
        return prompt_text, "created"
    existing = destination.read_text(encoding="utf-8")
    if existing == prompt_text:
        return prompt_text, "unchanged"
    return prompt_text, "updated"


def remove_protocol_block(instructions_path: str | Path) -> str:
    destination = Path(instructions_path)
    if not destination.exists():
        return "missing"

    existing = destination.read_text(encoding="utf-8")
    if PROTOCOL_HEADER not in existing:
        return "unchanged"

    updated = PROTOCOL_BLOCK_PATTERN.sub("", existing, count=1)
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    if updated:
        destination.write_text(updated + "\n", encoding="utf-8")
        return "updated"

    destination.unlink()
    return "deleted"


def remove_skill_document(skill_path: str | Path) -> str:
    return delete_file_if_exists(skill_path, prune_parent=True)


def remove_prompt_document(prompt_path: str | Path) -> str:
    return delete_file_if_exists(prompt_path)


def _default_viewer_readme() -> str:
    return (
        "# OlinKB Viewer\n\n"
        "Static read-only snapshot artifact for OlinKB.\n\n"
        "For large-scale exploration, use the live viewer:\n\n"
        "```bash\n"
        "olinkb viewer\n"
        "```\n\n"
        "Generate a fresh snapshot only when you need a portable point-in-time export:\n\n"
        "```bash\n"
        "olinkb viewer build\n"
        "```\n"
    )


def cleanup_viewer_scaffold(workspace_root: Path) -> str:
    viewer_dir = workspace_root / "olinkb-viewer"
    if not viewer_dir.exists():
        return "missing"

    allowed_entries = {"index.html", "README.md"}
    entries = list(viewer_dir.iterdir())
    if any(entry.name not in allowed_entries for entry in entries):
        return "preserved"

    for filename in allowed_entries:
        file_path = viewer_dir / filename
        if file_path.exists():
            file_path.unlink()

    viewer_dir.rmdir()
    return "deleted"


def cleanup_repository_bootstrap(workspace_root: Path) -> dict[str, str]:
    return {
        "mcp_status": remove_olinkb_mcp_server(workspace_root / ".vscode" / "mcp.json"),
        "instructions_status": remove_protocol_block(workspace_root / ".github" / "copilot-instructions.md"),
        "skill_status": remove_skill_document(
            workspace_root / ".copilot" / "skills" / MEMORY_RELEVANCE_SKILL_NAME / "SKILL.md"
        ),
        "viewer_status": cleanup_viewer_scaffold(workspace_root),
    }


def cleanup_global_bootstrap() -> dict[str, Any]:
    shell_profiles = get_shell_profile_paths()
    return {
        "mcp_status": remove_olinkb_mcp_server(get_global_mcp_config_path()),
        "instructions_status": remove_protocol_block(get_global_instructions_path()),
        "prompt_status": remove_prompt_document(get_global_cli_mandatory_prompt_path()),
        "legacy_instructions_status": cleanup_legacy_global_instructions(get_legacy_global_instructions_path()),
        "skill_status": remove_skill_document(get_global_skill_path()),
        "settings_status": delete_file_if_exists(get_global_settings_path()),
        "shell_env_status": delete_file_if_exists(get_global_shell_env_path()),
        "command_wrapper_status": delete_file_if_exists(get_global_command_wrapper_path()),
        "windows_user_path_status": remove_windows_user_path(get_global_command_wrapper_path().parent),
        "shell_profile_paths": [str(path) for path in shell_profiles],
        "shell_profile_statuses": remove_shell_profile_hooks(shell_profiles),
    }


def cleanup_legacy_global_instructions(instructions_path: str | Path) -> str:
    return remove_protocol_block(instructions_path)