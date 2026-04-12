from __future__ import annotations

import json


def render_mcp_template(
    *,
    pg_url: str,
    team: str,
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> str:
    env = {
        "OLINKB_PG_URL": pg_url,
        "OLINKB_TEAM": team,
        "OLINKB_USER": user_env,
    }
    if project:
        env["OLINKB_PROJECT"] = project

    document = {
        "servers": {
            "olinkb": {
                "command": "olinkb",
                "args": ["mcp"],
                "type": "stdio",
                "env": env,
            }
        }
    }
    return json.dumps(document, indent=2)


def render_instructions_template() -> str:
    return """## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

### On Session Start
- On the first relevant interaction of a session, call `boot_session`.

### During Work
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`.
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory`.

### Before Ending
- Call `end_session` with a brief summary of what was accomplished.
"""