from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REFERENCE_PATTERN = re.compile(r"\b[a-z]+://[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
NOTE_SECTION_PATTERN = re.compile(r"^\s*(what|why|where|learned)\s*:\s*(.*)$", re.IGNORECASE)
NOTE_SECTION_LABELS = {
  "what": "What",
  "why": "Why",
  "where": "Where",
  "learned": "Learned",
}


def _extract_namespace_component(namespace: str, scheme: str) -> str:
  if not namespace or not namespace.startswith(f"{scheme}://"):
    return ""
  return namespace.split("://", 1)[1].split("/", 1)[0]


def _stringify_note_section(value: Any) -> str:
  if value is None:
    return ""
  if isinstance(value, str):
    return value.strip()
  if isinstance(value, (list, tuple, set)):
    return "\n".join(str(item).strip() for item in value if str(item).strip()).strip()
  if isinstance(value, dict):
    return json.dumps(value, ensure_ascii=False, indent=2).strip()
  return str(value).strip()


def _extract_note_sections(content: str | None, metadata: dict[str, Any] | None) -> dict[str, str]:
  sections: dict[str, str] = {key: "" for key in NOTE_SECTION_LABELS}
  sections["remaining"] = ""

  normalized_metadata = {str(key).lower(): value for key, value in (metadata or {}).items()}
  for key in NOTE_SECTION_LABELS:
    sections[key] = _stringify_note_section(normalized_metadata.get(key))

  if not content:
    return sections

  remaining_lines: list[str] = []
  current_key: str | None = None
  buffer: list[str] = []

  def flush_current() -> None:
    nonlocal current_key, buffer
    if not current_key:
      buffer = []
      return
    parsed_value = "\n".join(line.rstrip() for line in buffer).strip()
    if parsed_value and not sections[current_key]:
      sections[current_key] = parsed_value
    current_key = None
    buffer = []

  for raw_line in content.splitlines():
    match = NOTE_SECTION_PATTERN.match(raw_line)
    if match:
      flush_current()
      current_key = match.group(1).lower()
      initial_value = match.group(2).strip()
      buffer = [initial_value] if initial_value else []
      continue

    if current_key:
      buffer.append(raw_line)
    else:
      remaining_lines.append(raw_line)

  flush_current()
  sections["remaining"] = "\n".join(line.rstrip() for line in remaining_lines).strip()
  return sections


def build_empty_viewer_payload() -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "memoryCount": 0,
            "activeMemoryCount": 0,
            "deletedMemoryCount": 0,
            "sessionCount": 0,
            "auditCount": 0,
            "authorCount": 0,
            "edgeCount": 0,
        },
        "filters": {
          "scopes": [],
          "authors": [],
          "tags": [],
          "memoryTypes": [],
          "teams": [],
          "projects": [],
          "established": ["active", "deleted"],
        },
        "memories": [],
        "sessions": [],
        "auditLog": [],
        "teamMembers": [],
        "graph": {"nodes": [], "edges": []},
        "highlights": [],
    }


def build_viewer_payload(
    *,
    memories: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    audit_log: list[dict[str, Any]],
    team_members: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    memories = [memory for memory in memories if memory.get("scope") != "personal"]
    normalized_team_members = [_normalize_team_member(member) for member in team_members]
    teams_by_username = {
      str(member.get("username")): str(member.get("team"))
      for member in normalized_team_members
      if member.get("username") and member.get("team")
    }
    normalized_memories = [_normalize_memory(memory, teams_by_username) for memory in memories]
    normalized_sessions = [_normalize_session(session) for session in sessions]
    normalized_audit_log = [_normalize_audit(entry) for entry in audit_log]

    scopes = sorted({memory["scope"] for memory in normalized_memories if memory.get("scope")})
    authors = sorted({memory["author_username"] for memory in normalized_memories if memory.get("author_username")})
    tags = sorted({tag for memory in normalized_memories for tag in memory.get("tags", [])})
    memory_types = sorted({memory["memory_type"] for memory in normalized_memories if memory.get("memory_type")})
    teams = sorted(
      {
        team
        for team in (
          _extract_namespace_component(memory.get("namespace", ""), "team")
          for memory in normalized_memories
        )
        if team
      }
      | {member.get("team") for member in normalized_team_members if member.get("team")}
    )
    projects = sorted(
      {
        project
        for project in (
          _extract_namespace_component(memory.get("namespace", ""), "project")
          for memory in normalized_memories
        )
        if project
      }
      | {session.get("project") for session in normalized_sessions if session.get("project")}
    )

    graph = _build_graph(normalized_memories)
    highlights = sorted(
        normalized_memories,
        key=lambda memory: (
            memory["isDeleted"],
            -(memory.get("retrieval_count") or 0),
            memory.get("updated_at") or "",
            memory.get("title") or "",
        ),
    )[:6]

    generated = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "generatedAt": generated,
        "stats": {
            "memoryCount": len(normalized_memories),
            "activeMemoryCount": sum(1 for memory in normalized_memories if not memory["isDeleted"]),
            "deletedMemoryCount": sum(1 for memory in normalized_memories if memory["isDeleted"]),
            "sessionCount": len(normalized_sessions),
            "auditCount": len(normalized_audit_log),
            "authorCount": len(authors),
            "edgeCount": len(graph["edges"]),
        },
        "filters": {
            "scopes": scopes,
            "authors": authors,
            "tags": tags,
            "memoryTypes": memory_types,
          "teams": teams,
          "projects": projects,
          "established": ["active", "deleted"],
        },
        "memories": normalized_memories,
        "sessions": normalized_sessions,
        "auditLog": normalized_audit_log,
        "teamMembers": normalized_team_members,
        "graph": graph,
        "highlights": highlights,
    }


def render_viewer_html(
    payload: dict[str, Any],
    title: str = "OlinKB Viewer",
    live_api_path: str | None = None,
) -> str:
    serialized_payload = "null" if live_api_path else json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    serialized_live_api_path = json.dumps(live_api_path)
    escaped_title = _escape_html(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
    <script>
      (() => {{
        try {{
          const storedTheme = window.localStorage.getItem("olinkb.viewer.theme");
          document.documentElement.dataset.theme = storedTheme === "light" ? "light" : "dark";
        }} catch (_error) {{
          document.documentElement.dataset.theme = "dark";
        }}
      }})();
    </script>
  <style>
    :root {{
        color-scheme: dark;
        --page-top: #0f1318;
        --page-bottom: #1a1e25;
        --bg: #1b1f26;
        --bg-elevated: #242a33;
        --sidebar: #14181d;
        --sidebar-2: #0f1317;
        --surface: #20252d;
        --surface-soft: rgba(255, 255, 255, 0.028);
        --field-bg: #10141a;
        --line: #323944;
        --line-soft: rgba(255, 255, 255, 0.08);
        --line-faint: rgba(255, 255, 255, 0.04);
        --text: #dde3ea;
        --text-strong: #f3f6fa;
        --text-soft: #d0d6df;
        --muted: #99a3b0;
        --accent: #8ba9ff;
        --accent-soft: rgba(139, 169, 255, 0.16);
        --accent-border: rgba(139, 169, 255, 0.28);
        --accent-strong: rgba(139, 169, 255, 0.45);
        --green: #7ec09b;
        --red: #d68579;
        --shadow: 0 24px 50px rgba(3, 6, 10, 0.32);
        --panel-tint: rgba(255, 255, 255, 0.02);
        --panel-overlay: rgba(255, 255, 255, 0.03);
        --panel-hover: rgba(255, 255, 255, 0.05);
        --panel-border: rgba(255, 255, 255, 0.06);
        --tree-line: rgba(255, 255, 255, 0.12);
        --hint-bg: #10141a;
        --chip-bg: rgba(255, 255, 255, 0.06);
        --chip-line: rgba(255, 255, 255, 0.08);
        --resizer-track: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.05));
        --resizer-handle: linear-gradient(180deg, rgba(139, 169, 255, 0.08), rgba(139, 169, 255, 0.5), rgba(139, 169, 255, 0.08));
        --canvas-glow: rgba(139, 169, 255, 0.14);
        --canvas-base: rgba(9, 12, 17, 0.96);
        --grid-line: rgba(255, 255, 255, 0.03);
        --guide-line: rgba(255, 255, 255, 0.06);
        --node-ring: rgba(255, 255, 255, 0.08);
        --selection-text: #edf1ff;
        --edge-namespace: rgba(139, 169, 255, 0.44);
        --edge-tag: rgba(196, 147, 86, 0.32);
        --edge-author: rgba(126, 192, 155, 0.35);
        --edge-reference: rgba(212, 170, 96, 0.46);
      --font-ui: "Avenir Next", "Segoe UI", sans-serif;
    }}
      :root[data-theme="light"] {{
        color-scheme: light;
        --page-top: #f6f3ec;
        --page-bottom: #ece7dc;
        --bg: #faf7f0;
        --bg-elevated: #f3eee4;
        --sidebar: #eee7db;
        --sidebar-2: #e4dccf;
        --surface: #fffdf8;
        --surface-soft: rgba(34, 42, 50, 0.025);
        --field-bg: #f7f2e9;
        --line: #d8cfbf;
        --line-soft: rgba(34, 42, 50, 0.11);
        --line-faint: rgba(34, 42, 50, 0.07);
        --text: #25313b;
        --text-strong: #16212b;
        --text-soft: #344450;
        --muted: #6f7984;
        --accent: #4464a5;
        --accent-soft: rgba(68, 100, 165, 0.12);
        --accent-border: rgba(68, 100, 165, 0.22);
        --accent-strong: rgba(68, 100, 165, 0.3);
        --green: #3f7d67;
        --red: #b76b5d;
        --shadow: 0 24px 50px rgba(89, 73, 43, 0.1);
        --panel-tint: rgba(34, 42, 50, 0.025);
        --panel-overlay: rgba(34, 42, 50, 0.03);
        --panel-hover: rgba(34, 42, 50, 0.055);
        --panel-border: rgba(34, 42, 50, 0.075);
        --tree-line: rgba(34, 42, 50, 0.14);
        --hint-bg: #f6f0e4;
        --chip-bg: rgba(34, 42, 50, 0.042);
        --chip-line: rgba(34, 42, 50, 0.075);
        --resizer-track: linear-gradient(180deg, rgba(34, 42, 50, 0.035), rgba(34, 42, 50, 0.07));
        --resizer-handle: linear-gradient(180deg, rgba(68, 100, 165, 0.08), rgba(68, 100, 165, 0.38), rgba(68, 100, 165, 0.08));
        --canvas-glow: rgba(68, 100, 165, 0.1);
        --canvas-base: rgba(234, 227, 214, 0.96);
        --grid-line: rgba(34, 42, 50, 0.03);
        --guide-line: rgba(34, 42, 50, 0.07);
        --node-ring: rgba(34, 42, 50, 0.1);
        --selection-text: #1a2640;
        --edge-namespace: rgba(68, 100, 165, 0.34);
        --edge-tag: rgba(162, 114, 60, 0.3);
        --edge-author: rgba(63, 125, 103, 0.25);
        --edge-reference: rgba(162, 114, 60, 0.39);
      }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      font-family: var(--font-ui);
      color: var(--text);
      background: linear-gradient(180deg, var(--page-top) 0%, var(--page-bottom) 100%);
      overflow: hidden;
    }}
    html, body, .sidebar-list, .note-scroll {{
      scrollbar-width: none;
      -ms-overflow-style: none;
    }}
    html::-webkit-scrollbar,
    body::-webkit-scrollbar,
    .sidebar-list::-webkit-scrollbar,
    .note-scroll::-webkit-scrollbar {{
      width: 0;
      height: 0;
      display: none;
    }}
    body.resizing {{ cursor: col-resize; user-select: none; }}
    .app-shell {{
      --sidebar-width: clamp(260px, 20vw, 420px);
      --graph-width: clamp(320px, 40vw, 960px);
      display: grid;
      grid-template-columns: var(--sidebar-width) minmax(0, 1fr) 12px minmax(320px, var(--graph-width));
      height: 100vh;
      width: 100vw;
      overflow: hidden;
    }}
    .sidebar-pane {{
      background: linear-gradient(180deg, var(--sidebar) 0%, var(--sidebar-2) 100%);
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      min-height: 0;
    }}
    .note-pane {{
      background: var(--bg);
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }}
    .graph-pane {{
      background: linear-gradient(180deg, var(--surface) 0%, var(--bg-elevated) 100%);
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow: hidden;
    }}
    .graph-resizer {{
      position: relative;
      background: var(--resizer-track);
      border-left: 1px solid var(--line-faint);
      border-right: 1px solid var(--line-faint);
      cursor: col-resize;
    }}
    .graph-resizer::before {{
      content: "";
      position: absolute;
      top: 50%;
      left: 50%;
      width: 4px;
      height: 84px;
      border-radius: 999px;
      transform: translate(-50%, -50%);
      background: var(--resizer-handle);
    }}
    .graph-resizer::after {{
      content: "Drag";
      position: absolute;
      top: 18px;
      left: 50%;
      transform: translateX(-50%);
      padding: 5px 8px;
      border-radius: 999px;
      background: var(--hint-bg);
      border: 1px solid var(--accent-border);
      color: var(--muted);
      font-size: 0.72rem;
      opacity: 0;
      transition: opacity 120ms ease;
      pointer-events: none;
      white-space: nowrap;
    }}
    .graph-resizer:hover::after {{ opacity: 1; }}
    .vault-header, .graph-header {{
      padding: 18px 18px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .vault-title {{
      font-size: 1rem;
      font-weight: 700;
      margin: 0 0 6px;
      color: var(--text-strong);
    }}
    .vault-header-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .vault-subtitle, .graph-subtitle, .note-subtitle {{
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.5;
      margin: 0;
    }}
    .section-action {{
      appearance: none;
      border: 0;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.01em;
      padding: 2px 0;
      border-radius: 6px;
      cursor: pointer;
      transition: color 120ms ease, opacity 120ms ease;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }}
    .section-action-icon {{
      content: "";
      width: 8px;
      height: 8px;
      border-right: 1.5px solid currentColor;
      border-bottom: 1.5px solid currentColor;
      opacity: 0.8;
      flex: none;
      transition: transform 120ms ease;
    }}
    .section-action[data-direction="down"] .section-action-icon {{ transform: rotate(45deg) translateY(-1px); }}
    .section-action[data-direction="up"] .section-action-icon {{ transform: rotate(-135deg) translate(-1px, -1px); }}
    .section-action:hover {{ color: var(--text); opacity: 1; }}
    .section-action:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .sidebar-tools {{
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 14px;
    }}
    .toolbar-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .toolbar-label {{ color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .theme-toggle {{
      appearance: none;
      border: 1px solid var(--accent-border);
      background: linear-gradient(180deg, var(--surface), var(--surface-soft));
      color: var(--text);
      font: inherit;
      border-radius: 999px;
      padding: 8px 12px;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
    }}
    .theme-toggle::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(180deg, #a3b7ff 0%, #586894 100%);
      box-shadow: 0 0 0 1px var(--accent-border);
      flex: none;
    }}
    .theme-toggle[data-theme="light"]::before {{
      background: linear-gradient(180deg, #fff6d8 0%, #c79347 100%);
    }}
    .theme-toggle:hover {{ transform: translateY(-1px); border-color: var(--accent); }}
    .theme-toggle:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .theme-toggle-value {{ color: var(--text-strong); font-size: 0.82rem; font-weight: 700; }}
    .search {{
      width: 100%;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--field-bg);
      color: var(--text);
      font: inherit;
      outline: none;
    }}
    .search:focus {{ border-color: var(--accent); }}
    .vault-stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .search-pagination {{
      display: grid;
      gap: 8px;
    }}
    .search-pagination:empty {{ display: none; }}
    .search-pagination-meta {{
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .search-pagination-actions {{
      display: flex;
      gap: 8px;
    }}
    .search-pagination-button {{
      appearance: none;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      font: inherit;
      border-radius: 8px;
      padding: 8px 10px;
      cursor: pointer;
      transition: border-color 120ms ease, transform 120ms ease;
    }}
    .search-pagination-button:hover:enabled {{ border-color: var(--accent); transform: translateY(-1px); }}
    .search-pagination-button:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .stat-card {{
      padding: 10px 10px 12px;
      border-radius: 10px;
      background: var(--surface);
      border: 1px solid var(--line);
    }}
    .stat-label {{ color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .stat-value {{ margin-top: 6px; font-size: 1.05rem; font-weight: 700; }}
    .search-highlight {{
        background: var(--accent-strong);
      color: var(--text-strong);
      border-radius: 4px;
      padding: 0 2px;
        border-bottom: 2px solid var(--accent);
        font-weight: 500;
    }}
    .sidebar-list {{
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 12px;
    }}
    .explorer-shell {{
      border-radius: 12px;
      background: var(--panel-tint);
      border: 1px solid var(--line);
      overflow: hidden;
    }}
    .explorer-toolbar {{
      display: flex;
      justify-content: flex-end;
      align-items: center;
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--line-faint);
      background: var(--panel-overlay);
    }}
    .explorer-tree {{
      display: grid;
      gap: 2px;
      padding: 8px 0;
    }}
    .explorer-folder {{ border-bottom: 1px solid var(--line-faint); }}
    .explorer-folder:last-child {{ border-bottom: none; }}
    .explorer-summary {{
      list-style: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      color: var(--text-soft);
      font-size: 0.9rem;
    }}
    .explorer-summary::-webkit-details-marker {{ display: none; }}
    .explorer-chevron {{
      width: 10px;
      color: var(--muted);
      transition: transform 120ms ease;
      transform: rotate(0deg);
      display: inline-block;
    }}
    .explorer-folder[open] > .explorer-summary .explorer-chevron {{ transform: rotate(90deg); }}
    .explorer-label {{ flex: 1; }}
    .explorer-count {{ color: var(--muted); font-size: 0.76rem; }}
    .explorer-children {{ display: grid; gap: 1px; padding: 0 0 8px; }}
    .explorer-folder .explorer-children {{ padding-left: 10px; }}
    .tree-note {{
      appearance: none;
      width: 100%;
      border: 0;
      background: transparent;
      color: var(--muted);
      text-align: left;
      font: inherit;
      cursor: pointer;
      padding: 4px 12px 4px 30px;
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      font-size: 0.84rem;
    }}
    .tree-note::before {{
      content: "";
      width: 10px;
      height: 1px;
      background: var(--tree-line);
      flex: none;
    }}
    .tree-note:hover {{ background: var(--panel-hover); color: var(--text); }}
    .tree-note.active {{
      background: var(--accent-soft);
      color: var(--selection-text);
      box-shadow: inset 2px 0 0 var(--accent);
    }}
    .tree-note-label {{
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .note-header {{
      padding: 22px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, var(--panel-tint), transparent);
    }}
    .note-breadcrumb {{ color: var(--muted); font-size: 0.8rem; margin-bottom: 8px; }}
    .note-title {{ margin: 0; font-size: 2rem; line-height: 1.05; color: var(--text-strong); }}
    .note-tags {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--chip-bg);
      border: 1px solid var(--chip-line);
      color: var(--muted);
      font-size: 0.75rem;
    }}
    .chip.accent {{ color: var(--accent); background: var(--accent-soft); border-color: var(--accent-border); }}
    .chip.green {{ color: var(--green); }}
    .chip.red {{ color: var(--red); }}
    .note-scroll {{
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 28px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 24px;
      align-items: start;
    }}
    .note-main {{ min-width: 0; display: grid; gap: 18px; }}
    .note-markdown {{
      padding: 24px 26px;
      border-radius: 16px;
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      white-space: pre-wrap;
      line-height: 1.75;
      color: var(--text);
      font-size: 0.98rem;
    }}
    .note-structured-content {{
      display: grid;
      gap: 16px;
    }}
    .note-subsection {{
      display: grid;
      gap: 8px;
    }}
    .note-subtitle {{
      margin: 0;
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: var(--text-strong);
    }}
    .note-subtitle.what {{ color: #9fb6ff; }}
    .note-subtitle.why {{ color: #f6c177; }}
    .note-subtitle.where {{ color: #8bd5ca; }}
    .note-subtitle.learned {{ color: #a6da95; }}
    .note-subcontent {{
      white-space: pre-wrap;
      line-height: 1.75;
      color: var(--text);
      font-size: 0.98rem;
    }}
    .note-section {{
      padding: 18px;
      border-radius: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
    }}
    .note-section h3 {{ margin: 0 0 12px; font-size: 0.98rem; }}
    .related-list, .history-list {{ display: grid; gap: 10px; }}
    .related-item, .history-item {{
      padding: 12px;
      border-radius: 10px;
      background: var(--panel-overlay);
      border: 1px solid var(--panel-border);
      cursor: pointer;
    }}
    .history-item {{ cursor: default; }}
    .related-item-title {{ font-size: 0.9rem; font-weight: 600; color: var(--text-strong); }}
    .related-item-meta, .history-time {{ margin-top: 6px; font-size: 0.78rem; color: var(--muted); }}
    .related-item-text, .history-text {{ margin-top: 8px; color: var(--muted); font-size: 0.84rem; line-height: 1.45; }}
    .note-side {{ display: grid; gap: 14px; position: sticky; top: 0; }}
    .side-card {{
      padding: 16px;
      border-radius: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
    }}
    .side-card h4 {{ margin: 0 0 10px; font-size: 0.86rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
    .side-list {{ display: grid; gap: 8px; color: var(--muted); font-size: 0.84rem; }}
    .graph-header {{ display: grid; gap: 10px; }}
    .graph-stage {{ flex: 1; min-height: 0; padding: 14px 16px 16px; overflow: hidden; }}
    .graph-stage canvas {{
      width: 100%;
      height: 100%;
      min-height: min(68vh, 760px);
      display: block;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: radial-gradient(circle at top, var(--canvas-glow), var(--canvas-base) 70%);
      cursor: grab;
    }}
    .graph-stage canvas.dragging {{ cursor: grabbing; }}
    .empty-state {{ color: var(--muted); font-size: 0.9rem; line-height: 1.6; }}
    @media (max-width: 1280px) {{
      .app-shell {{ grid-template-columns: 300px minmax(0, 1fr); }}
      .graph-resizer {{ display: none; }}
      .graph-pane {{ display: none; }}
      .note-scroll {{ grid-template-columns: 1fr; }}
      .note-side {{ position: static; }}
    }}
    @media (max-width: 880px) {{
      body {{ overflow: auto; }}
      .app-shell {{ grid-template-columns: 1fr; height: auto; min-height: 100vh; }}
      .sidebar-pane {{ border-right: none; border-bottom: 1px solid var(--line); }}
      .note-scroll {{ padding: 20px; }}
    }}
  </style>
</head>
<body>
  <div id="app-shell" class="app-shell">
    <aside class="sidebar-pane">
      <div class="vault-header">
        <div class="vault-title">OlinKB Vault</div>
        <p class="vault-subtitle">Universal knowledge base explorer. Every memory lives in a single path.</p>
      </div>
      <div class="sidebar-tools">
        <div class="toolbar-row">
          <span class="toolbar-label">Appearance</span>
          <button id="theme-toggle" class="theme-toggle" type="button" aria-live="polite">
            <span id="theme-toggle-value" class="theme-toggle-value">Dark mode</span>
          </button>
        </div>
        <input id="search" class="search" type="search" placeholder="Search notes...">
        <div class="vault-stats" id="vault-stats"></div>
        <div class="search-pagination" id="search-pagination"></div>
      </div>
      <div class="sidebar-list" id="memory-list"></div>
    </aside>

    <main class="note-pane">
      <div class="note-header" id="note-header"></div>
      <div class="note-scroll">
        <div class="note-main" id="note-main"></div>
        <div class="note-side" id="note-side"></div>
      </div>
    </main>

    <div id="graph-resizer" class="graph-resizer" role="separator" aria-orientation="vertical" aria-label="Resize graph panel"></div>

    <aside class="graph-pane">
      <div class="graph-header">
        <div>
          <div class="vault-title">Memory graph</div>
          <p class="graph-subtitle">Each point represents a note. Hover over the divider and drag to expand this section.</p>
        </div>
        <div class="note-subtitle" id="graph-summary"></div>
      </div>
      <div class="graph-stage">
        <canvas id="graph-canvas"></canvas>
      </div>
    </aside>
  </div>

  <script>
    window.__OLINKB_VIEWER_DATA__ = {serialized_payload};
  </script>
  <script>
    (() => {{
      const THEME_STORAGE_KEY = "olinkb.viewer.theme";
      let data = window.__OLINKB_VIEWER_DATA__ || {{ memories: [], sessions: [], auditLog: [], graph: {{ nodes: [], edges: [] }}, stats: {{}} }};
      const liveApiPath = {serialized_live_api_path};
      const state = {{
        theme: getStoredTheme(),
        search: "",
        graphWidth: Math.max(320, Math.round(window.innerWidth * 0.4)),
        selectedId: data.highlights?.[0]?.id || data.memories?.[0]?.id || null,
        expandedFolders: new Set(),
        explorerInitialized: false,
        live: {{
          limit: 50,
          cursor: null,
          cursorHistory: [],
          nextCursor: null,
          loading: false,
          requestToken: 0,
          searchTimer: null,
        }},
      }};

      const elements = {{
        search: document.getElementById("search"),
        vaultStats: document.getElementById("vault-stats"),
        searchPagination: document.getElementById("search-pagination"),
        memoryList: document.getElementById("memory-list"),
        noteHeader: document.getElementById("note-header"),
        noteMain: document.getElementById("note-main"),
        noteSide: document.getElementById("note-side"),
        graphSummary: document.getElementById("graph-summary"),
        graphResizer: document.getElementById("graph-resizer"),
        appShell: document.getElementById("app-shell"),
        themeToggle: document.getElementById("theme-toggle"),
        themeToggleValue: document.getElementById("theme-toggle-value"),
      }};

      const graphController = createGraphController(document.getElementById("graph-canvas"), (nodeId) => {{
        state.selectedId = nodeId;
        render();
      }});

      elements.search.addEventListener("input", (event) => {{
        const nextSearch = event.target.value.trim();
        state.selectedId = null;
        if (liveApiPath) {{
          state.search = nextSearch;
          resetLivePagination();
          queueLiveReload();
          return;
        }}
        state.search = nextSearch;
        render();
      }});
      applyTheme(state.theme);
      elements.themeToggle.addEventListener("click", () => {{
        applyTheme(state.theme === "light" ? "dark" : "light");
        graphController.resize();
      }});

      setupGraphResizer();
      if (liveApiPath) {{
        render();
        loadLiveData();
        window.setInterval(loadLiveData, 10000);
      }} else {{
        render();
      }}

      function resetLivePagination() {{
        state.live.cursor = null;
        state.live.cursorHistory = [];
        state.live.nextCursor = null;
      }}

      function queueLiveReload() {{
        if (!liveApiPath) return;
        if (state.live.searchTimer) window.clearTimeout(state.live.searchTimer);
        state.live.searchTimer = window.setTimeout(() => {{
          state.live.searchTimer = null;
          loadLiveData();
        }}, 180);
      }}

      async function loadLiveData() {{
        if (!liveApiPath) return;
        const requestToken = ++state.live.requestToken;
        const requestUrl = new URL(liveApiPath, window.location.origin);
        requestUrl.searchParams.set("limit", String(state.live.limit));
        if (state.search) requestUrl.searchParams.set("q", state.search);
        if (state.live.cursor) requestUrl.searchParams.set("cursor", state.live.cursor);
        state.live.loading = true;
        try {{
          const response = await fetch(requestUrl, {{ cache: "no-store" }});
          if (!response.ok) return;
          const nextData = await response.json();
          if (requestToken !== state.live.requestToken) return;
          data = nextData;
          state.live.nextCursor = data.pageInfo?.next_cursor || null;
          const stillExists = (data.memories || []).some((memory) => memory.id === state.selectedId);
          if (!stillExists) {{
            state.selectedId = data.highlights?.[0]?.id || data.memories?.[0]?.id || null;
          }}
          render();
        }} catch (_error) {{
        }} finally {{
          if (requestToken === state.live.requestToken) state.live.loading = false;
        }}
      }}

      function getStoredTheme() {{
        try {{
          const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
          if (storedTheme === "light" || storedTheme === "dark") return storedTheme;
        }} catch (_error) {{
        }}
        return document.documentElement.dataset.theme === "light" ? "light" : "dark";
      }}

      function applyTheme(theme) {{
        document.documentElement.dataset.theme = theme;
        state.theme = theme;
        elements.themeToggle.dataset.theme = theme;
        elements.themeToggle.setAttribute("aria-pressed", String(theme === "light"));
        elements.themeToggle.setAttribute("aria-label", theme === "light" ? "Switch to dark mode" : "Switch to light mode");
        elements.themeToggleValue.textContent = theme === "light" ? "Light mode" : "Dark mode";
        try {{
          window.localStorage.setItem(THEME_STORAGE_KEY, theme);
        }} catch (_error) {{
        }}
      }}

      function render() {{
        const memories = getFilteredMemories();
        ensureValidSelection(memories);
        const graph = getFilteredGraph(memories);
        elements.appShell.style.setProperty("--graph-width", `${{state.graphWidth}}px`);
        renderVaultStats(graph);
        renderSearchPagination(memories);
        renderExplorer(memories);
        renderNote(memories, graph);
        const memoryNodes = graph.nodes.filter((node) => node.kind === "memory");
        const projectCount = graph.nodes.filter((node) => node.kind === "project").length;
        const typeCount = graph.nodes.filter((node) => node.kind === "memory_type").length;
        const deletedCount = memoryNodes.filter((node) => node.stateKey === "deleted").length;
        elements.graphSummary.textContent = `${{formatNumber(memoryNodes.length)}} notes · ${{formatNumber(projectCount)}} projects · ${{formatNumber(typeCount)}} types · ${{formatNumber(deletedCount)}} forgotten`;
        graphController.resize();
        graphController.update(graph, state.selectedId);
      }}

      function renderVaultStats(graph) {{
        const memoryCount = liveApiPath
          ? (data.pageInfo?.returned_count ?? (data.memories || []).length)
          : (data.memories || []).length;
        const stats = [
          [liveApiPath ? "Visible" : "Notes", memoryCount],
          ["Authors", data.stats?.authorCount ?? 0],
          ["Links", graph.edges.length],
        ];
        elements.vaultStats.innerHTML = stats.map(([label, value]) => `
          <div class="stat-card">
            <div class="stat-label">${{label}}</div>
            <div class="stat-value">${{formatNumber(value)}}</div>
          </div>
        `).join("");
      }}

      function renderSearchPagination(memories) {{
        if (!liveApiPath) {{
          elements.searchPagination.innerHTML = "";
          return;
        }}

        const pageInfo = data.pageInfo || {{}};
        const summaryText = state.search
          ? `Searching title and content for “${{state.search}}”`
          : "Recent notes";
        const metaText = state.live.loading
          ? "Searching PostgreSQL..."
          : `${{summaryText}} · ${{formatNumber(pageInfo.returned_count ?? memories.length)}} notes on this page`;

        elements.searchPagination.innerHTML = `
          <div class="search-pagination-meta">${{escapeHtml(metaText)}}</div>
          <div class="search-pagination-actions">
            <button class="search-pagination-button" type="button" data-live-page="prev" ${{state.live.cursorHistory.length ? "" : "disabled"}}>Previous</button>
            <button class="search-pagination-button" type="button" data-live-page="next" ${{pageInfo?.has_next ? "" : "disabled"}}>Next</button>
          </div>
        `;

        elements.searchPagination.querySelector('[data-live-page="prev"]')?.addEventListener("click", () => {{
          if (!state.live.cursorHistory.length) return;
          state.live.cursor = state.live.cursorHistory.pop() ?? null;
          loadLiveData();
        }});
        elements.searchPagination.querySelector('[data-live-page="next"]')?.addEventListener("click", () => {{
          if (!data.pageInfo?.has_next || !state.live.nextCursor) return;
          state.live.cursorHistory.push(state.live.cursor);
          state.live.cursor = state.live.nextCursor;
          loadLiveData();
        }});
      }}

      function renderExplorer(memories) {{
        if (!memories.length) {{
          elements.memoryList.innerHTML = '<div class="empty-state">No notes match the current search.</div>';
          return;
        }}
        const searchActive = Boolean(getNormalizedSearchQuery());
        const tree = buildExplorerTree(memories);
        const folderKeys = collectExplorerFolderKeys(tree);
        const allExpanded = folderKeys.length > 0 && folderKeys.every((key) => state.expandedFolders.has(key));
        const actionLabel = allExpanded ? "Collapse" : "Expand";
        const actionDirection = allExpanded ? "up" : "down";
        elements.memoryList.innerHTML = `
          <div class="explorer-shell">
            ${{searchActive ? "" : `
              <div class="explorer-toolbar">
                <button id="collapse-explorer" class="section-action" type="button" data-direction="${{actionDirection}}" aria-label="${{actionLabel}} notes tree">
                  <span class="section-action-icon" aria-hidden="true"></span>
                  <span>${{actionLabel}}</span>
                </button>
              </div>
            `}}
            ${{renderExplorerNode(tree, true, 0)}}
          </div>
        `;
        elements.memoryList.querySelector("#collapse-explorer")?.addEventListener("click", () => {{
          if (allExpanded) {{
            state.expandedFolders.clear();
          }} else {{
            state.expandedFolders = new Set(folderKeys);
          }}
          state.explorerInitialized = true;
          render();
        }});
        elements.memoryList.querySelectorAll("[data-memory-id]").forEach((node) => {{
          node.addEventListener("click", () => {{
            state.selectedId = node.getAttribute("data-memory-id");
            render();
          }});
        }});
        elements.memoryList.querySelectorAll("details[data-folder-key]").forEach((node) => {{
          node.addEventListener("toggle", () => {{
            const folderKey = node.getAttribute("data-folder-key");
            if (!folderKey) return;
            if (node.open) state.expandedFolders.add(folderKey);
            else state.expandedFolders.delete(folderKey);
          }});
        }});
      }}

      function collectExplorerFolderKeys(node) {{
        if (!node || node.kind === "note") return [];
        const keys = [];
        (node.children || []).forEach((child) => {{
          if (child.kind !== "folder") return;
          keys.push(child.key, ...collectExplorerFolderKeys(child));
        }});
        return keys;
      }}

      function buildExplorerTree(memories) {{
        const root = {{ kind: "folder", key: "root", name: "root", count: memories.length, children: [], containsSelected: false }};
        const folderMap = new Map([["", root]]);

        memories.forEach((memory) => {{
          const path = getNoteFolderPath(memory);
          let key = "";
          let parent = root;
          path.forEach((segment) => {{
            key = `${{key}}/${{segment}}`;
            let folder = folderMap.get(key);
            if (!folder) {{
              folder = {{ kind: "folder", key, name: segment, count: 0, children: [], containsSelected: false }};
              folderMap.set(key, folder);
              parent.children.push(folder);
            }}
            folder.count += 1;
            parent = folder;
          }});
          parent.children.push({{
            kind: "note",
            id: memory.id,
            title: memory.title,
          }});
        }});

        sortExplorerTree(root);
        markSelectedPath(root);
        seedExplorerFolders(root);
        return root;
      }}

      function seedExplorerFolders(root) {{
        if (state.explorerInitialized || state.expandedFolders.size > 0) return;
        (root.children || []).forEach((child) => {{
          if (child.kind !== "folder") return;
          state.expandedFolders.add(child.key);
        }});
        state.explorerInitialized = true;
      }}

      function markSelectedPath(node) {{
        if (node.kind === "note") return node.id === state.selectedId;
        let containsSelected = false;
        (node.children || []).forEach((child) => {{
          if (markSelectedPath(child)) containsSelected = true;
        }});
        node.containsSelected = containsSelected;
        return containsSelected;
      }}

      function sortExplorerTree(node) {{
        if (!node.children) return;
        node.children.sort((left, right) => {{
          if (left.kind !== right.kind) return left.kind === "folder" ? -1 : 1;
          const leftValue = left.name || left.title || "";
          const rightValue = right.name || right.title || "";
          return leftValue.localeCompare(rightValue, "es");
        }});
        node.children.forEach((child) => sortExplorerTree(child));
      }}

      function renderExplorerNode(node, expanded, depth) {{
        if (node.kind === "note") {{
          return `
            <button class="tree-note ${{node.id === state.selectedId ? "active" : ""}}" type="button" data-memory-id="${{node.id}}">
              <span class="tree-note-label">${{highlightSearchText(node.title)}}</span>
            </button>
          `;
        }}

        const children = (node.children || []).map((child) => renderExplorerNode(child, depth < 2, depth + 1)).join("");
        if (node.name === "root") return `<div class="explorer-tree">${{children}}</div>`;
        const isOpen = getNormalizedSearchQuery() ? true : state.expandedFolders.has(node.key);
        return `
          <details class="explorer-folder" data-folder-key="${{escapeHtml(node.key)}}" ${{isOpen ? "open" : ""}}>
            <summary class="explorer-summary">
              <span class="explorer-chevron">›</span>
              <span class="explorer-label">${{escapeHtml(node.name)}}</span>
              <span class="explorer-count">${{formatNumber(node.count || 0)}}</span>
            </summary>
            <div class="explorer-children">${{children}}</div>
          </details>
        `;
      }}

      function getNoteFolderPath(memory) {{
        const scope = humanizeScope(memory.scope);
        const team = memory.team || extractNamespacePart(memory.namespace, "team");
        const project = memory.project || extractNamespacePart(memory.namespace, "project");
        const type = humanizeType(memory.memory_type);
        if (memory.scope === "project") {{
          if (team && project) return [team, project, type];
          if (team) return [team, type];
          if (project) return [project, type];
          return [type];
        }}
        if (team) return [scope, team, type];
        if (memory.scope === "personal" && memory.author_username) return [scope, memory.author_username, type];
        return [scope, type];
      }}

      function setupGraphResizer() {{
        if (!elements.graphResizer) return;
        let resizing = false;

        elements.graphResizer.addEventListener("pointerdown", (event) => {{
          if (window.innerWidth <= 1280) return;
          resizing = true;
          document.body.classList.add("resizing");
          elements.graphResizer.setPointerCapture?.(event.pointerId);
        }});

        window.addEventListener("pointermove", (event) => {{
          if (!resizing) return;
          const nextWidth = Math.max(320, Math.min(window.innerWidth - 460, window.innerWidth - event.clientX));
          state.graphWidth = nextWidth;
          elements.appShell.style.setProperty("--graph-width", `${{state.graphWidth}}px`);
        }});

        window.addEventListener("pointerup", () => {{
          if (!resizing) return;
          resizing = false;
          document.body.classList.remove("resizing");
          graphController.resize();
        }});
      }}

      function renderNote(memories, graph) {{
        const selected = memories.find((memory) => memory.id === state.selectedId) || memories[0];
        if (!selected) {{
          elements.noteHeader.innerHTML = '<div class="note-breadcrumb">Vault</div><h1 class="note-title">No selection</h1>';
          elements.noteMain.innerHTML = '<div class="empty-state">There is nothing to show yet.</div>';
          elements.noteSide.innerHTML = '';
          return;
        }}

        state.selectedId = selected.id;
        const related = graph.edges
          .filter((edge) => edge.type === "reference" && (edge.source === selected.id || edge.target === selected.id))
          .slice(0, 8)
          .map((edge) => {{
            const relatedId = edge.source === selected.id ? edge.target : edge.source;
            const relatedMemory = data.memories.find((memory) => memory.id === relatedId);
            return {{ edge, relatedMemory }};
          }})
          .filter((item) => item.relatedMemory);
        const authorSessions = (data.sessions || []).filter((session) => session.author_username === selected.author_username).slice(0, 4);

        elements.noteHeader.innerHTML = `
          <div class="note-breadcrumb">${{escapeHtml(selected.namespace || selected.scope || "Vault")}}</div>
          <h1 class="note-title">${{highlightSearchText(selected.title)}}</h1>
          <div class="note-tags">
            <span class="chip accent">${{escapeHtml(selected.memory_type)}}</span>
            <span class="chip">${{escapeHtml(selected.author_username)}}</span>
            <span class="chip">${{formatDate(selected.updated_at)}}</span>
            ${{selected.isDeleted ? '<span class="chip red">Forgotten</span>' : '<span class="chip green">Active</span>'}}
            ${{(selected.tags || []).slice(0, 4).map((tag) => `<span class="chip">#${{escapeHtml(tag)}}</span>`).join("")}}
          </div>
        `;

        const structuredSections = [
          {{ key: "what", label: "What" }},
          {{ key: "why", label: "Why" }},
          {{ key: "where", label: "Where" }},
          {{ key: "learned", label: "Learned" }},
        ];
        const noteSections = selected.sections || {{}};
        const sectionBlocks = structuredSections
          .map((section) => {{
            const value = (noteSections[section.key] || "").trim();
            if (!value) return "";
            return `
              <section class="note-subsection">
                <h4 class="note-subtitle ${{section.key}}">${{section.label}}</h4>
                <div class="note-subcontent">${{highlightSearchText(value)}}</div>
              </section>
            `;
          }})
          .join("");
        const remainingContent = (noteSections.remaining || "").trim();
        const noteBody = sectionBlocks || remainingContent
          ? `
            <div class="note-structured-content">
              ${{sectionBlocks}}
              ${{remainingContent ? `
                <section class="note-subsection">
                  <h4 class="note-subtitle">Additional content</h4>
                  <div class="note-subcontent">${{highlightSearchText(remainingContent)}}</div>
                </section>
              ` : ""}}
            </div>
          `
          : `<div class="note-markdown">${{highlightSearchText(selected.content || "No content available.")}}</div>`;

        elements.noteMain.innerHTML = `
          <section class="note-section">
            <h3>Note content</h3>
            ${{noteBody}}
          </section>
          <section class="note-section">
            <h3>Directly connected notes</h3>
            <div class="related-list">
              ${{related.length ? related.map((item) => `
                <article class="related-item" data-memory-id="${{item.relatedMemory.id}}">
                  <div class="related-item-title">${{escapeHtml(item.relatedMemory.title)}}</div>
                  <div class="related-item-meta">${{escapeHtml(item.edge.typeLabel || item.edge.type)}} · ${{escapeHtml(item.relatedMemory.author_username)}}</div>
                  <div class="related-item-text">${{escapeHtml(excerpt(item.relatedMemory.content, 120))}}</div>
                </article>
              `).join("") : '<div class="empty-state">No direct relationships are visible for this note.</div>'}}
            </div>
          </section>
        `;

        elements.noteMain.querySelectorAll("[data-memory-id]").forEach((node) => {{
          node.addEventListener("click", () => {{
            state.selectedId = node.getAttribute("data-memory-id");
            render();
          }});
        }});

        elements.noteSide.innerHTML = `
          <section class="side-card">
            <h4>Metadata</h4>
            <div class="side-list">
              <div><strong>URI:</strong> <span>${{escapeHtml(selected.uri)}}</span></div>
              <div><strong>Scope:</strong> <span>${{escapeHtml(selected.scope)}}</span></div>
              <div><strong>Team:</strong> <span>${{escapeHtml(selected.team || extractNamespacePart(selected.namespace, "team") || "-")}}</span></div>
              <div><strong>Project:</strong> <span>${{escapeHtml(selected.project || extractNamespacePart(selected.namespace, "project") || "-")}}</span></div>
              <div><strong>Namespace:</strong> <span>${{escapeHtml(selected.namespace || "no namespace")}}</span></div>
              <div><strong>Reads:</strong> <span>${{formatNumber(selected.retrieval_count || 0)}}</span></div>
            </div>
          </section>
          <section class="side-card">
            <h4>Author sessions</h4>
            <div class="side-list">
              ${{authorSessions.length ? authorSessions.map((session) => `<div>${{escapeHtml(session.project || "No project")}} · ${{formatDate(session.started_at)}}</div>`).join("") : '<div>No recent sessions.</div>'}}
            </div>
          </section>
        `;
      }}

      function getFilteredMemories() {{
        if (liveApiPath) return data.memories || [];
        const searchQuery = getNormalizedSearchQuery();
        return (data.memories || []).filter((memory) => {{
          const searchable = [memory.title, memory.uri, memory.content, ...(memory.tags || []), memory.author_username, memory.memory_type, memory.team, memory.project]
            .join(" ")
            .toLowerCase();
          return !searchQuery || searchable.includes(searchQuery);
        }});
      }}

      function getFilteredGraph(memories) {{
        const visibleMemoryIds = new Set(memories.map((memory) => memory.id));
        const nodeMap = new Map((data.graph?.nodes || []).map((node) => [node.id, node]));
        const visibleNodeIds = new Set(visibleMemoryIds);
        const visibleEdges = [];

        (data.graph?.edges || []).forEach((edge) => {{
          const sourceNode = nodeMap.get(edge.source);
          const targetNode = nodeMap.get(edge.target);
          const sourceVisibleMemory = visibleMemoryIds.has(edge.source);
          const targetVisibleMemory = visibleMemoryIds.has(edge.target);
          const sourceMeta = sourceNode && sourceNode.kind !== "memory";
          const targetMeta = targetNode && targetNode.kind !== "memory";

          if (sourceVisibleMemory && targetVisibleMemory) {{
            visibleEdges.push(edge);
            return;
          }}
          if (sourceVisibleMemory && targetMeta) {{
            visibleNodeIds.add(edge.target);
            visibleEdges.push(edge);
            return;
          }}
          if (targetVisibleMemory && sourceMeta) {{
            visibleNodeIds.add(edge.source);
            visibleEdges.push(edge);
          }}
        }});

        return {{
          nodes: (data.graph?.nodes || []).filter((node) => visibleNodeIds.has(node.id)),
          edges: visibleEdges,
        }};
      }}

      function ensureValidSelection(memories) {{
        if (!memories.length) {{
          state.selectedId = null;
          return;
        }}
        if (!memories.some((memory) => memory.id === state.selectedId)) {{
          state.selectedId = memories[0].id;
        }}
      }}

      function extractNamespacePart(namespace, scheme) {{
        if (!namespace || !namespace.startsWith(`${{scheme}}://`)) return "";
        return namespace.slice(scheme.length + 3).split("/")[0];
      }}

      function humanizeScope(scope) {{
        if (scope === "project") return "Project";
        if (scope === "team") return "Team";
        if (scope === "personal") return "Personal";
        if (scope === "org") return "Org";
        if (scope === "system") return "System";
        return scope || "Other";
      }}

      function humanizeType(type) {{
        if (!type) return "Notes";
        return type.split(/[_-]/g).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
      }}

      function excerpt(text, length) {{
        if (!text) return "";
        return text.length > length ? `${{text.slice(0, length).trim()}}…` : text;
      }}

      function formatDate(value) {{
        if (!value) return "no date";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return new Intl.DateTimeFormat("en", {{ dateStyle: "medium", timeStyle: "short" }}).format(date);
      }}

      function formatNumber(value) {{
        return new Intl.NumberFormat("en").format(Number(value || 0));
      }}

      function getNormalizedSearchQuery() {{
        return String(state.search || "").trim().toLowerCase();
      }}

      function highlightSearchText(value) {{
        const text = String(value ?? "");
        const searchQuery = getNormalizedSearchQuery();
        if (!searchQuery) return escapeHtml(text);

        const lowerText = text.toLowerCase();
        let cursor = 0;
        let matchIndex = lowerText.indexOf(searchQuery, cursor);
        if (matchIndex === -1) return escapeHtml(text);

        let output = "";
        while (matchIndex !== -1) {{
          output += escapeHtml(text.slice(cursor, matchIndex));
          output += `<mark class="search-highlight">${{escapeHtml(text.slice(matchIndex, matchIndex + searchQuery.length))}}</mark>`;
          cursor = matchIndex + searchQuery.length;
          matchIndex = lowerText.indexOf(searchQuery, cursor);
        }}
        output += escapeHtml(text.slice(cursor));
        return output;
      }}

      function escapeHtml(value) {{
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }}

      function createGraphController(canvas, onSelect) {{
        const context = canvas.getContext("2d");
        const resizeTarget = canvas.parentElement || canvas;
        const runtime = {{
          nodes: [],
          nodeMap: new Map(),
          edges: [],
          layout: null,
          selectedId: null,
          hoverId: null,
          draggedId: null,
          dragOffset: null,
          isPanning: false,
          panStart: null,
          lastPointer: null,
          offsetX: 0,
          offsetY: 0,
          scale: 1,
          suppressClick: false,
          resizeFrame: null,
          resizeObserver: null,
          pixelWidth: 0,
          pixelHeight: 0,
          dpr: 0,
          pointerDown: null,
          dragStarted: false,
        }};

        function cssVar(name, fallback) {{
          return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
        }}

        resize();
        scheduleResize();
        window.addEventListener("resize", scheduleResize);
        canvas.addEventListener("pointermove", onPointerMove);
        canvas.addEventListener("pointerdown", onPointerDown);
        window.addEventListener("pointerup", onPointerUp);
        canvas.addEventListener("click", onClick);
        canvas.addEventListener("wheel", onWheel, {{ passive: false }});
        if (typeof ResizeObserver !== "undefined") {{
          runtime.resizeObserver = new ResizeObserver(() => scheduleResize());
          runtime.resizeObserver.observe(resizeTarget);
        }}
        requestAnimationFrame(tick);

        return {{ update, resize: scheduleResize }};

        function scheduleResize() {{
          if (runtime.resizeFrame) cancelAnimationFrame(runtime.resizeFrame);
          runtime.resizeFrame = requestAnimationFrame(() => {{
            runtime.resizeFrame = null;
            resize();
          }});
        }}

        function resize() {{
          const dpr = window.devicePixelRatio || 1;
          const width = Math.max(canvas.clientWidth, 1);
          const height = Math.max(canvas.clientHeight, 1);
          const pixelWidth = Math.round(width * dpr);
          const pixelHeight = Math.round(height * dpr);
          runtime.layout = buildLayout(runtime.nodes, width, height);
          if (runtime.pixelWidth == pixelWidth && runtime.pixelHeight == pixelHeight && runtime.dpr == dpr) {{
            return;
          }}
          runtime.pixelWidth = pixelWidth;
          runtime.pixelHeight = pixelHeight;
          runtime.dpr = dpr;
          canvas.width = pixelWidth;
          canvas.height = pixelHeight;
          context.setTransform(dpr, 0, 0, dpr, 0, 0);
          if (!runtime.offsetX && !runtime.offsetY) {{
            runtime.offsetX = canvas.clientWidth * 0.06;
            runtime.offsetY = canvas.clientHeight * 0.08;
          }}
        }}

        function update(graph, selectedId) {{
          runtime.selectedId = selectedId;
          const nextMap = new Map();
          const existing = runtime.nodeMap;
          const width = Math.max(canvas.clientWidth, 1);
          const height = Math.max(canvas.clientHeight, 1);
          runtime.layout = buildLayout(graph.nodes, width, height);
          const targetSlots = buildNodeSlots(graph.nodes, runtime.layout, width, height);
          graph.nodes.forEach((node, index) => {{
            const previous = existing.get(node.id);
            const target = previous?.userPosition
              ? {{ x: previous.targetX ?? previous.x, y: previous.targetY ?? previous.y }}
              : (targetSlots.get(node.id) || {{ x: width / 2, y: height / 2 }});
            nextMap.set(node.id, previous || {{
              ...node,
              x: target.x + ((index % 3) - 1) * 10,
              y: target.y + ((index % 4) - 1.5) * 8,
              vx: 0,
              vy: 0,
              userPosition: false,
            }});
            Object.assign(nextMap.get(node.id), node, {{
              targetX: target.x,
              targetY: target.y,
              userPosition: previous?.userPosition || false,
            }});
          }});
          runtime.nodeMap = nextMap;
          runtime.nodes = [...nextMap.values()];
          runtime.edges = graph.edges;
        }}

        function buildLayout(nodes, width, height) {{
          const memoryNodes = (nodes || []).filter((node) => node.kind === "memory");
          const projects = [...new Set(memoryNodes.map((node) => node.projectLabel || "No project"))];
          const memoryTypes = [...new Set(memoryNodes.map((node) => node.typeLabel || node.type || "Notes"))];
          if (!projects.length) projects.push("No project");
          const spacing = projects.length === 1
            ? 0
            : Math.max(180, Math.min(320, Math.max(width - 180, 180) / (projects.length - 1)));
          const totalWidth = spacing * Math.max(projects.length - 1, 0);
          const startX = width / 2 - totalWidth / 2;
          const projectColumns = projects.map((label, index) => ({{ label, x: startX + index * spacing }}));
          const activeY = Math.max(130, height * 0.3);
          const deletedY = Math.max(activeY + 140, height * 0.7);
          const projectNodeY = Math.max(56, activeY - 120);
          const typeNodeY = deletedY + 126;
          const typeSpacing = memoryTypes.length === 1
            ? 0
            : Math.max(130, Math.min(220, Math.max(width - 160, 160) / (memoryTypes.length - 1)));
          const typeTotalWidth = typeSpacing * Math.max(memoryTypes.length - 1, 0);
          const typeStartX = width / 2 - typeTotalWidth / 2;
          const typeColumns = memoryTypes.map((label, index) => ({{ label, x: typeStartX + index * typeSpacing, y: typeNodeY }}));
          const stateRows = [
            {{ key: "active", label: "Active", y: activeY }},
            {{ key: "deleted", label: "Forgotten", y: deletedY }},
          ];
          return {{
            projectColumns,
            projectMap: new Map(projectColumns.map((column) => [column.label, column])),
            projectNodeY,
            typeColumns,
            typeMap: new Map(typeColumns.map((column) => [column.label, column])),
            stateRows,
            stateMap: new Map(stateRows.map((row) => [row.key, row])),
            bounds: {{
              left: startX - 96,
              right: startX + totalWidth + 96,
              top: projectNodeY - 42,
              bottom: typeNodeY + 68,
            }},
          }};
        }}

        function buildNodeSlots(nodes, layout, width, height) {{
          const groups = new Map();
          (nodes || []).forEach((node) => {{
            if (node.kind !== "memory") return;
            const groupKey = `${{node.projectLabel || "No project"}}::${{node.stateKey || "active"}}`;
            if (!groups.has(groupKey)) groups.set(groupKey, []);
            groups.get(groupKey).push(node);
          }});

          const slots = new Map();
          groups.forEach((group, groupKey) => {{
            const [projectLabel, stateKey] = groupKey.split("::");
            const project = layout.projectMap.get(projectLabel);
            const state = layout.stateMap.get(stateKey);
            const anchorX = project ? project.x : width / 2;
            const anchorY = state ? state.y : height / 2;
            const ordered = group.slice().sort((left, right) => {{
              if (left.prominent !== right.prominent) return left.prominent ? -1 : 1;
              if ((left.size || 0) !== (right.size || 0)) return (right.size || 0) - (left.size || 0);
              return (left.label || "").localeCompare(right.label || "", "es");
            }});
            const columns = Math.max(1, Math.ceil(Math.sqrt(ordered.length)));
            const rows = Math.max(1, Math.ceil(ordered.length / columns));
            ordered.forEach((node, index) => {{
              const column = index % columns;
              const row = Math.floor(index / columns);
              const offsetX = (column - (columns - 1) / 2) * 54;
              const offsetY = (row - (rows - 1) / 2) * 48;
              slots.set(node.id, {{ x: anchorX + offsetX, y: anchorY + offsetY }});
            }});
          }});

          (nodes || []).forEach((node) => {{
            if (node.kind === "project") {{
              const project = layout.projectMap.get(node.projectLabel || node.label);
              slots.set(node.id, {{ x: project ? project.x : width / 2, y: layout.projectNodeY }});
            }} else if (node.kind === "memory_type") {{
              const type = layout.typeMap.get(node.typeLabel || node.label);
              slots.set(node.id, {{ x: type ? type.x : width / 2, y: type ? type.y : height - 96 }});
            }}
          }});

          return slots;
        }}

        function tick() {{
          stepPhysics();
          draw();
          requestAnimationFrame(tick);
        }}

        function stepPhysics() {{
          const nodes = runtime.nodes;
          const edges = runtime.edges;
          const draggedId = runtime.draggedId;
          if (!nodes.length) return;

          for (let i = 0; i < nodes.length; i += 1) {{
            const nodeA = nodes[i];
            for (let j = i + 1; j < nodes.length; j += 1) {{
              const nodeB = nodes[j];
              if (nodeA.id === draggedId || nodeB.id === draggedId) continue;
              let dx = nodeB.x - nodeA.x;
              let dy = nodeB.y - nodeA.y;
              let distanceSq = dx * dx + dy * dy;
              if (!distanceSq) distanceSq = 0.01;
              const distance = Math.sqrt(distanceSq);
              const force = Math.min(2300 / distanceSq, 0.8);
              dx /= distance;
              dy /= distance;
              nodeA.vx -= dx * force;
              nodeA.vy -= dy * force;
              nodeB.vx += dx * force;
              nodeB.vy += dy * force;
            }}
          }}

          edges.forEach((edge) => {{
            const source = runtime.nodeMap.get(edge.source);
            const target = runtime.nodeMap.get(edge.target);
            if (!source || !target) return;
            if (source.id === draggedId || target.id === draggedId) return;
            const dx = target.x - source.x;
            const dy = target.y - source.y;
            const distance = Math.max(Math.hypot(dx, dy), 0.001);
            const desired = edge.type === "reference" ? 110 : 84;
            const spring = (distance - desired) * 0.004 * (edge.weight || 1);
            const nx = dx / distance;
            const ny = dy / distance;
            source.vx += nx * spring;
            source.vy += ny * spring;
            target.vx -= nx * spring;
            target.vy -= ny * spring;
          }});

          const centerX = canvas.clientWidth / 2;
          const centerY = canvas.clientHeight / 2;
          nodes.forEach((node) => {{
            if (draggedId === node.id) {{
              node.vx = 0;
              node.vy = 0;
              return;
            }}
            const targetX = node.targetX ?? centerX;
            const targetY = node.targetY ?? centerY;
            node.vx += (targetX - node.x) * 0.012;
            node.vy += (targetY - node.y) * 0.012;
            node.vx *= 0.88;
            node.vy *= 0.88;
            node.x += node.vx;
            node.y += node.vy;
          }});
        }}

        function draw() {{
          context.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
          context.save();
          context.translate(runtime.offsetX, runtime.offsetY);
          context.scale(runtime.scale, runtime.scale);
          context.strokeStyle = cssVar('--grid-line', 'rgba(255,255,255,0.03)');
          const topLeft = screenToWorld({{ x: 0, y: 0 }});
          const bottomRight = screenToWorld({{ x: canvas.clientWidth, y: canvas.clientHeight }});
          const startX = Math.floor(topLeft.x / 36) * 36;
          const endX = Math.ceil(bottomRight.x / 36) * 36;
          const startY = Math.floor(topLeft.y / 36) * 36;
          const endY = Math.ceil(bottomRight.y / 36) * 36;
          for (let x = startX; x <= endX; x += 36) {{
            context.beginPath();
            context.moveTo(x, startY);
            context.lineTo(x, endY);
            context.stroke();
          }}
          for (let y = startY; y <= endY; y += 36) {{
            context.beginPath();
            context.moveTo(startX, y);
            context.lineTo(endX, y);
            context.stroke();
          }}

          drawLayoutGuides();
          const edgeColors = {{
            same_namespace: cssVar('--edge-namespace', 'rgba(139, 169, 255, 0.44)'),
            shared_tag: cssVar('--edge-tag', 'rgba(196, 147, 86, 0.32)'),
            same_author: cssVar('--edge-author', 'rgba(126, 192, 155, 0.35)'),
            reference: cssVar('--edge-reference', 'rgba(212, 170, 96, 0.46)'),
          }};

          runtime.edges.forEach((edge) => {{
            const source = runtime.nodeMap.get(edge.source);
            const target = runtime.nodeMap.get(edge.target);
            if (!source || !target) return;
            context.beginPath();
            context.strokeStyle = edgeColors[edge.type] || cssVar('--line-soft', 'rgba(159, 164, 173, 0.22)');
            context.lineWidth = edge.type === 'reference' ? 1.8 : 1.1;
            context.moveTo(source.x, source.y);
            context.lineTo(target.x, target.y);
            context.stroke();
          }});

          runtime.nodes.forEach((node) => {{
            const selected = node.id === runtime.selectedId;
            const radius = Math.max(6, node.size || 10);
            context.beginPath();
            context.fillStyle = node.isDeleted ? 'rgba(242, 139, 130, 0.4)' : node.color;
            context.shadowColor = selected ? cssVar('--accent-strong', 'rgba(139, 169, 255, 0.45)') : 'transparent';
            context.shadowBlur = selected ? 18 : 0;
            context.arc(node.x, node.y, selected ? radius + 2 : radius, 0, Math.PI * 2);
            context.fill();
            context.shadowBlur = 0;
            context.lineWidth = selected ? 2.2 : 1;
            context.strokeStyle = selected ? cssVar('--text-strong', 'rgba(255,255,255,0.9)') : cssVar('--node-ring', 'rgba(255,255,255,0.08)');
            context.stroke();
            if (selected || node.prominent || node.kind !== "memory") {{
              context.fillStyle = cssVar('--text', 'rgba(220, 221, 222, 0.92)');
              context.font = `${{11 / runtime.scale}}px Avenir Next, sans-serif`;
              context.fillText(node.label, node.x + radius + 8, node.y + 4);
            }}
          }});
          context.restore();
        }}

        function drawLayoutGuides() {{
          if (!runtime.layout || !runtime.layout.projectColumns?.length) return;
          const {{ projectColumns, stateRows, bounds }} = runtime.layout;
          context.save();
          context.lineWidth = 1 / runtime.scale;
          context.strokeStyle = cssVar('--guide-line', 'rgba(255,255,255,0.06)');
          context.fillStyle = cssVar('--text-soft', 'rgba(220, 221, 222, 0.76)');
          context.font = `${{12 / runtime.scale}}px Avenir Next, sans-serif`;
          context.textAlign = 'center';
          context.textBaseline = 'bottom';
          projectColumns.forEach((project) => {{
            context.beginPath();
            context.moveTo(project.x, bounds.top);
            context.lineTo(project.x, bounds.bottom);
            context.stroke();
          }});

          context.textAlign = 'left';
          context.textBaseline = 'middle';
          stateRows.forEach((state) => {{
            context.beginPath();
            context.moveTo(bounds.left, state.y);
            context.lineTo(bounds.right, state.y);
            context.stroke();
            context.fillText(state.label, bounds.left + (12 / runtime.scale), state.y - (16 / runtime.scale));
          }});

          context.textAlign = 'center';
          context.textBaseline = 'top';
          (runtime.layout.typeColumns || []).forEach((type) => {{
            context.fillText(type.label, type.x, type.y + (18 / runtime.scale));
          }});
          context.restore();
        }}

        function findNode(pointer) {{
          const worldPointer = screenToWorld(pointer);
          let closest = null;
          runtime.nodes.forEach((node) => {{
            const dx = worldPointer.x - node.x;
            const dy = worldPointer.y - node.y;
            const radius = Math.max(10, node.size || 12);
            if (dx * dx + dy * dy <= radius * radius) closest = node;
          }});
          return closest;
        }}

        function screenToWorld(pointer) {{
          return {{
            x: (pointer.x - runtime.offsetX) / runtime.scale,
            y: (pointer.y - runtime.offsetY) / runtime.scale,
          }};
        }}

        function getPointer(event) {{
          const rect = canvas.getBoundingClientRect();
          return {{ x: event.clientX - rect.left, y: event.clientY - rect.top }};
        }}

        function onPointerMove(event) {{
          runtime.lastPointer = getPointer(event);
          if (runtime.pointerDown && !runtime.dragStarted) {{
            const moveX = runtime.lastPointer.x - runtime.pointerDown.x;
            const moveY = runtime.lastPointer.y - runtime.pointerDown.y;
            if (Math.hypot(moveX, moveY) < 6) return;
            runtime.dragStarted = true;
            runtime.suppressClick = true;
            canvas.classList.add('dragging');
          }}
          if (runtime.draggedId) {{
            if (!runtime.dragStarted) return;
            const node = runtime.nodeMap.get(runtime.draggedId);
            const worldPointer = screenToWorld(runtime.lastPointer);
            if (node && runtime.dragOffset) {{
              node.x = worldPointer.x - runtime.dragOffset.x;
              node.y = worldPointer.y - runtime.dragOffset.y;
              node.vx = 0;
              node.vy = 0;
            }}
            return;
          }}
          if (!runtime.isPanning || !runtime.panStart) return;
          if (!runtime.dragStarted) return;
          runtime.offsetX = runtime.panStart.offsetX + (runtime.lastPointer.x - runtime.panStart.x);
          runtime.offsetY = runtime.panStart.offsetY + (runtime.lastPointer.y - runtime.panStart.y);
        }}

        function onPointerDown(event) {{
          const pointer = getPointer(event);
          runtime.lastPointer = pointer;
          runtime.pointerDown = pointer;
          runtime.dragStarted = false;
          const node = findNode(pointer);
          runtime.suppressClick = false;
          if (node) {{
            const worldPointer = screenToWorld(pointer);
            runtime.draggedId = node.id;
            runtime.dragOffset = {{ x: worldPointer.x - node.x, y: worldPointer.y - node.y }};
            runtime.isPanning = false;
            runtime.panStart = null;
          }} else {{
            runtime.draggedId = null;
            runtime.dragOffset = null;
            runtime.isPanning = true;
            runtime.panStart = {{ x: pointer.x, y: pointer.y, offsetX: runtime.offsetX, offsetY: runtime.offsetY }};
          }}
        }}

        function onPointerUp() {{
          if (runtime.dragStarted && runtime.draggedId) {{
            const node = runtime.nodeMap.get(runtime.draggedId);
            if (node) {{
              node.targetX = node.x;
              node.targetY = node.y;
              node.userPosition = true;
            }}
          }}
          runtime.draggedId = null;
          runtime.dragOffset = null;
          runtime.isPanning = false;
          runtime.panStart = null;
          runtime.pointerDown = null;
          runtime.dragStarted = false;
          canvas.classList.remove('dragging');
        }}

        function onClick(event) {{
          if (runtime.suppressClick) {{
            runtime.suppressClick = false;
            return;
          }}
          const node = findNode(getPointer(event));
          if (node && node.kind === "memory") onSelect(node.id);
        }}

        function onWheel(event) {{
          event.preventDefault();
          const pointer = getPointer(event);
          const worldBefore = screenToWorld(pointer);
          const nextScale = Math.min(2.6, Math.max(0.45, runtime.scale * (event.deltaY < 0 ? 1.1 : 0.9)));
          runtime.scale = nextScale;
          runtime.offsetX = pointer.x - (worldBefore.x * runtime.scale);
          runtime.offsetY = pointer.y - (worldBefore.y * runtime.scale);
        }}
      }}
    }})();
  </script>
</body>
</html>
"""


def build_viewer_output(snapshot: dict[str, list[dict[str, Any]]], output_path: str | Path, title: str = "OlinKB Viewer") -> Path:
    payload = build_viewer_payload(
        memories=snapshot.get("memories", []),
        sessions=snapshot.get("sessions", []),
        audit_log=snapshot.get("audit_log", []),
        team_members=snapshot.get("team_members", []),
    )
    html = render_viewer_html(payload, title=title)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def _normalize_memory(memory: dict[str, Any], teams_by_username: dict[str, str] | None = None) -> dict[str, Any]:
    tags = [str(tag) for tag in memory.get("tags") or []]
    retrieval_count = int(memory.get("retrieval_count") or 0)
    normalized = dict(memory)
    namespace = str(normalized.get("namespace") or "")
    project = _extract_namespace_component(namespace, "project")
    team = _extract_namespace_component(namespace, "team")
    if not team and teams_by_username:
        author_username = normalized.get("author_username")
        if author_username:
            team = teams_by_username.get(str(author_username), "")
    normalized["tags"] = tags
    normalized["project"] = project or str(normalized.get("project") or "")
    normalized["team"] = team or str(normalized.get("team") or "")
    normalized["retrieval_count"] = retrieval_count
    normalized["size"] = 12 + min(16, math.sqrt(max(retrieval_count, 1)) * 3)
    normalized["isDeleted"] = bool(memory.get("deleted_at"))
    normalized["created_at"] = memory.get("created_at")
    normalized["updated_at"] = memory.get("updated_at")
    if normalized.get("metadata") is None:
        normalized["metadata"] = {}
    normalized["sections"] = _extract_note_sections(normalized.get("content"), normalized.get("metadata"))
    return normalized


def _normalize_session(session: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(session)
    normalized["memories_read"] = int(session.get("memories_read") or 0)
    normalized["memories_written"] = int(session.get("memories_written") or 0)
    return normalized


def _normalize_audit(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    metadata = normalized.get("metadata")
    if metadata is None:
        normalized["metadata"] = {}
    return normalized


def _normalize_team_member(member: dict[str, Any]) -> dict[str, Any]:
    return dict(member)


def _graph_project_label(memory: dict[str, Any]) -> str:
    namespace = memory.get("namespace", "")
    project = _extract_namespace_component(namespace, "project")
    if project:
        return project
    team = _extract_namespace_component(namespace, "team")
    if team:
        return f"team/{team}"
    scope = memory.get("scope") or "other"
    if scope == "personal" and memory.get("author_username"):
        return f"personal/{memory['author_username']}"
    return str(scope)


def _build_graph(memories: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
  nodes = []
  edges: list[dict[str, Any]] = []
  memory_by_uri = {memory["uri"]: memory for memory in memories if memory.get("uri")}
  edge_keys: set[tuple[Any, ...]] = set()
  project_nodes: dict[str, dict[str, Any]] = {}
  type_nodes: dict[str, dict[str, Any]] = {}

  color_map = {
    "personal": "rgba(97, 165, 209, 0.92)",
    "project": "rgba(102, 132, 214, 0.92)",
    "team": "rgba(90, 154, 144, 0.9)",
    "org": "rgba(194, 150, 82, 0.9)",
    "system": "rgba(117, 177, 120, 0.92)",
  }

  prominent_ids = {
    memory["id"]
    for memory in sorted(
      memories,
      key=lambda item: (item["isDeleted"], -(item["retrieval_count"] or 0), item.get("updated_at") or ""),
    )[:10]
  }

  for memory in memories:
    state_key = "deleted" if memory["isDeleted"] else "active"
    project_label = _graph_project_label(memory)
    type_label = memory.get("memory_type") or "note"
    type_display = " ".join(part.capitalize() for part in type_label.replace("-", "_").split("_")) or "Notas"

    nodes.append(
      {
        "id": memory["id"],
        "label": memory["title"],
        "kind": "memory",
        "uri": memory["uri"],
        "scope": memory["scope"],
        "author": memory["author_username"],
        "type": memory["memory_type"],
        "typeLabel": type_display,
        "tags": memory["tags"],
        "size": memory["size"],
        "color": color_map.get(memory["scope"], "rgba(148, 163, 184, 0.9)"),
        "prominent": memory["id"] in prominent_ids,
        "isDeleted": memory["isDeleted"],
        "projectLabel": project_label,
        "stateKey": state_key,
        "stateLabel": "Forgotten" if state_key == "deleted" else "Active",
      }
    )

    project_nodes.setdefault(
      project_label,
      {
        "id": f"project:{project_label}",
        "label": project_label,
        "kind": "project",
        "projectLabel": project_label,
        "stateKey": "meta",
        "typeLabel": "Proyecto",
        "size": 18,
        "color": "rgba(80, 157, 146, 0.9)",
        "prominent": True,
        "isDeleted": False,
      },
    )
    type_nodes.setdefault(
      type_label,
      {
        "id": f"type:{type_label}",
        "label": type_display,
        "kind": "memory_type",
        "projectLabel": project_label,
        "stateKey": "meta",
        "typeLabel": type_display,
        "size": 16,
        "color": "rgba(199, 150, 77, 0.92)",
        "prominent": True,
        "isDeleted": False,
      },
    )

    _add_edge(
      edges,
      edge_keys,
      memory["id"],
      f"project:{project_label}",
      edge_type="belongs_project",
      type_label="pertenece al proyecto",
      weight=2,
    )
    _add_edge(
      edges,
      edge_keys,
      memory["id"],
      f"type:{type_label}",
      edge_type="has_type",
      type_label="tipo de nota",
      weight=1,
    )

  nodes.extend(project_nodes.values())
  nodes.extend(type_nodes.values())

  author_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
  namespace_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
  tag_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

  for memory in memories:
    author_groups[memory["author_username"]].append(memory)
    namespace_groups[memory["namespace"]].append(memory)
    for tag in memory["tags"]:
      tag_groups[tag].append(memory)

    for uri in sorted(set(REFERENCE_PATTERN.findall(memory.get("content") or ""))):
      referenced = memory_by_uri.get(uri.rstrip(".,;:!?)]"))
      if referenced is None or referenced["id"] == memory["id"]:
        continue
      _add_edge(
        edges,
        edge_keys,
        memory["id"],
        referenced["id"],
        edge_type="reference",
        type_label="referencia",
        weight=2,
        directed=True,
      )

  for group in author_groups.values():
    _connect_chain(edges, edge_keys, group, edge_type="same_author", type_label="mismo autor")
  for group in namespace_groups.values():
    _connect_chain(edges, edge_keys, group, edge_type="same_namespace", type_label="mismo namespace")
  for group in tag_groups.values():
    _connect_chain(edges, edge_keys, group, edge_type="shared_tag", type_label="tag compartido")

  return {"nodes": nodes, "edges": edges}


def _connect_chain(
    edges: list[dict[str, Any]],
    edge_keys: set[tuple[Any, ...]],
    group: list[dict[str, Any]],
    *,
    edge_type: str,
    type_label: str,
) -> None:
    ordered = sorted(group, key=lambda item: item.get("updated_at") or "", reverse=True)
    for left, right in zip(ordered, ordered[1:]):
        _add_edge(
            edges,
            edge_keys,
            left["id"],
            right["id"],
            edge_type=edge_type,
            type_label=type_label,
            weight=1,
        )


def _add_edge(
    edges: list[dict[str, Any]],
    edge_keys: set[tuple[Any, ...]],
    source: str,
    target: str,
    *,
    edge_type: str,
    type_label: str,
    weight: int,
    directed: bool = False,
) -> None:
    if source == target:
        return
    if directed:
        key = (edge_type, source, target)
    else:
        left, right = sorted((source, target))
        key = (edge_type, left, right)
        source, target = left, right
    if key in edge_keys:
        return
    edge_keys.add(key)
    edges.append(
        {
            "id": f"{edge_type}:{source}:{target}",
            "source": source,
            "target": target,
            "type": edge_type,
            "typeLabel": type_label,
            "weight": weight,
        }
    )


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
