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
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory` with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`.
- Do not wait until `end_session` to persist important discoveries, decisions, procedures, or bugfixes. `end_session` is a closure summary, not the primary durable memory channel.
- Do not save a one-line summary if future work would still require re-reading code or reconstructing the situation from scratch.
- Prefer richer context blocks with real operational depth so retrieved memories stay reusable weeks later.
- Effective memory format:
    What: [2-3 sentences with the concrete action, behavior change, or discovery, including specific examples when useful]
    Why: [root cause, motivation, impact, and why simpler or naive approaches were not enough]
    Where: [relevant file paths, modules, commands, surfaces, or boundaries where the change lives]
    Learned: [non-obvious pattern, gotcha, or rule that should transfer to similar future work]
- Add these when they help turn the note into a reusable artifact instead of a summary:
    Context: [surrounding constraints, prior failed attempts, deadlines, environment details, or product pressure]
    Decision: [what was chosen over which alternatives, and why]
    Evidence: [error messages, observed symptoms, example inputs/outputs, reproduced commands, or data points]
    Next Steps: [unfinished work, verification still needed, rollout notes, or adjacent follow-up]
- Aim to save enough detail that a later agent can continue the work without reopening every touched file first.

### Before Ending
- Call `end_session` with a brief summary of what was accomplished.
"""