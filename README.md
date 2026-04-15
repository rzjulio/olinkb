# OlinKB

OlinKB is a shared memory runtime for development agents with SQLite or PostgreSQL storage.

The base package is CLI-first. MCP support is optional and shipped as a separate addon package.

## What it does

- stores team and project memory in PostgreSQL
- exposes the same memory operations through direct CLI calls or MCP
- bootstraps VS Code and Copilot integration with `olinkb --init`
- provides a live viewer for browsing stored data

Core tool surface:

- `boot_session`
- `analyze_memory`
- `capture_memory`
- `remember`
- `save_memory`
- `end_session`
- `forget`

Preferred CLI-first memory flow:

1. Use `analyze_memory` when you want a dry run.
2. Use `capture_memory` when you want OlinKB to auto-save high-confidence memories.
3. Use `save_memory` only when you already know the exact type, scope, and URI you want.

## Install

Recommended base install:

```bash
pipx install https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init
```

If you prefer `pip`, install into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init
```

Optional MCP addon:

```bash
pipx inject olinkb https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb_mcp-0.1.0-py3-none-any.whl
```

Or inside the same Python environment:

```bash
python -m pip install https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb_mcp-0.1.0-py3-none-any.whl
```

If you are reinstalling a wheel while keeping the same version number during manual verification, force the reinstall or start from a clean environment. Otherwise `pip` or an existing wrapper can keep resolving an older installed package:

```bash
python -m pip install --force-reinstall ./olinkb-0.1.0-py3-none-any.whl
```

Quick check for the active command:

```bash
command -v olinkb
python -m pip show olinkb
```

Windows note: if wheel installation looks idle for a while, use:

```bash
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
```

## What `--init` does

`olinkb --init` asks which storage backend to use, then persists the backend-specific configuration and team for future terminals.

Storage options:

- `SQLite`: local file-backed setup for single-user or lightweight workflows
- `PostgreSQL`: server-backed setup for shared multi-user workflows

Mode selection is inferred automatically:

- `olinkb` only: CLI mode
- `olinkb` + `olinkb-mcp`: MCP mode

You can override that with `--mode cli` or `--mode mcp`.

Scope selection:

- `repository`: writes workspace-local VS Code and Copilot files
- `global`: writes user-level VS Code and Copilot files

It also persists runtime configuration so the user does not have to keep re-entering storage settings and `OLINKB_TEAM`.

macOS/Linux files:

- `~/.config/olinkb/settings.json`
- `~/.config/olinkb/env.sh`
- `~/.local/bin/olinkb`

Windows files:

- `%APPDATA%\olinkb\settings.json`
- `%APPDATA%\olinkb\env.sh`
- `%LOCALAPPDATA%\olinkb\bin\olinkb.cmd`

Platform behavior after `init`:

- macOS/Linux: updates shell profiles so a new terminal picks up the wrapper and exported `OLINKB_*` values
- Windows: updates the user `Path` so a new terminal can resolve `olinkb`

If you installed OlinKB inside a virtual environment, the generated wrapper points at that environment's Python. That works as long as the environment stays on disk.

## Main commands

```bash
olinkb --init
olinkb uninstall
olinkb tool analyze_memory --json '{"content":"# CLI Memory Automation\n\nDecision: keep CLI-first capture as the default surface"}'
olinkb tool capture_memory --json '{"content":"What: Fix invalid JSON handling\nWhy: CLI users need clearer failures\nWhere: src/olinkb/tool_cli.py"}'
olinkb tool remember --json '{"query":"bootstrap"}'
olinkb mcp
olinkb viewer
olinkb viewer build
olinkb migrate
```

## Uninstall

Use the OlinKB command for a real teardown:

```bash
olinkb uninstall
```

That command removes the bootstrap artifacts created by `olinkb --init`, including MCP registration, Copilot instruction blocks, persisted settings, shell hooks, the global wrapper, and the default `olinkb-viewer` scaffold in the current workspace. It then runs `pip uninstall -y olinkb olinkb-mcp` from the active Python environment.

Useful variants:

- `olinkb uninstall --scope repository` removes only workspace-local artifacts
- `olinkb uninstall --scope global` removes only user-level artifacts
- `olinkb uninstall --skip-package-uninstall` keeps the Python packages installed and only cleans generated files

`pip uninstall olinkb` by itself cannot remove those generated files because Python package uninstall does not get a post-uninstall cleanup hook.

## Viewer and managed memories

CLI users can now pre-triage content before opening the viewer:

```bash
olinkb tool analyze_memory --json '{"content":"# Architecture Guide\n\nThis document explains the CLI-first memory workflow."}'
```

And they can let OlinKB capture high-confidence items automatically:

```bash
olinkb tool capture_memory --json '{"content":"What: Fix CLI payload validation\nWhy: Invalid JSON produced confusing errors\nWhere: src/olinkb/tool_cli.py"}'
```

Use the live viewer as the main browsing surface:

```bash
olinkb viewer
```

Use the static export only when you need a portable snapshot:

```bash
olinkb viewer build
```

The viewer also supports managed Markdown records for curated documentation and development standards.

## Current scope

OlinKB currently focuses on the foundation layer:

- SQLite and PostgreSQL storage
- session boot and retrieval
- CLI and optional MCP transport
- viewer and managed-memory flow
- release packaging

It does not yet include semantic retrieval, RLS, LISTEN/NOTIFY invalidation, or the forgetting engine.

## More docs

- [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md) — local development, commands, release flow
- [docs/releases/RELEASING.md](docs/releases/RELEASING.md) — release checklist
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — version history
- [docs/olinkb-funcionamiento-end-to-end.md](docs/olinkb-funcionamiento-end-to-end.md) — deeper runtime walkthrough
