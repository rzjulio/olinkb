## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

### On Session Start
- On the first relevant interaction of a session, call `boot_session`.

### During Work
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`.
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory`.

### Before Ending
- Call `end_session` with a brief summary of what was accomplished.
