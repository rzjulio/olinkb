# OlinKB Developer Guide

This guide keeps the operational details that are too long for the main README.

## Local development

Start PostgreSQL with Docker:

```bash
cd docker
docker compose up -d
```

If `5432` is busy:

```bash
cd docker
OLINKB_PG_PORT=5433 docker compose up -d
```

Default local connection string:

```bash
postgresql://olinkb:olinkb@localhost:5432/olinkb
```

## Runtime configuration

Main environment variables:

- `OLINKB_PG_URL`
- `OLINKB_TEAM`
- `OLINKB_USER`
- `OLINKB_PROJECT`
- `OLINKB_CACHE_TTL_SECONDS`
- `OLINKB_CACHE_MAX_ENTRIES`
- `OLINKB_PG_POOL_MAX_SIZE`

Configuration precedence is:

1. real environment variables
2. persisted settings written by `olinkb --init`

The live viewer is looser than the main runtime. `olinkb viewer` only needs `OLINKB_PG_URL` to start.

## Install modes for developers

Base package:

```bash
pipx install ./olinkb-0.1.0-py3-none-any.whl
```

Optional MCP addon:

```bash
pipx inject olinkb ./olinkb_mcp-0.1.0-py3-none-any.whl
```

If you do not want `pipx`, use `pip` inside a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install ./olinkb-0.1.0-py3-none-any.whl
```

Run bootstrap after install:

```bash
olinkb --init
```

## What bootstrap writes

Repository scope writes:

- `.github/copilot-instructions.md`
- `.copilot/skills/memory-relevance-triage/SKILL.md`
- `.vscode/mcp.json` only in MCP mode

Global scope writes:

- user-level Copilot instructions
- user-level memory triage skill
- user-level MCP registration only in MCP mode
- persisted OlinKB settings and wrapper bootstrap

Persisted runtime files:

- macOS/Linux:
  - `~/.config/olinkb/settings.json`
  - `~/.config/olinkb/env.sh`
  - `~/.local/bin/olinkb`
- Windows:
  - `%APPDATA%\olinkb\settings.json`
  - `%APPDATA%\olinkb\env.sh`
  - `%LOCALAPPDATA%\olinkb\bin\olinkb.cmd`

Platform behavior:

- macOS/Linux: `init` updates shell profiles so a new terminal picks up the wrapper and exported settings
- Windows: `init` updates the user `Path` so a new terminal can resolve `olinkb`

Mode inference:

- base package only: CLI mode
- base package plus addon: MCP mode

Override with `--mode cli` or `--mode mcp` if needed.

## Commands

```bash
olinkb --init
olinkb uninstall
olinkb migrate
olinkb add-member --username rzjulio --role lead
olinkb tool analyze_memory --json '{"content":"# CLI Memory Automation\n\nDecision: keep CLI-first capture as the default operator path"}'
olinkb tool capture_memory --json '{"content":"What: Fix invalid JSON handling\nWhy: CLI users need explicit parse errors\nWhere: src/olinkb/tool_cli.py"}'
olinkb tool remember --json '{"query":"bootstrap"}'
olinkb mcp
olinkb viewer
olinkb viewer build
olinkb template mcp --pg-url postgresql://olinkb:olinkb@localhost:5433/olinkb --team example-team
olinkb template instructions
olinkb template instructions --mode cli
```

Notes:

- `olinkb tool ...` is the direct JSON transport
- `olinkb tool analyze_memory ...` is the dry-run classifier for memory relevance and type inference
- `olinkb tool capture_memory ...` is the preferred CLI entry point for near-automatic capture
- `olinkb mcp` requires `olinkb-mcp`
- `olinkb viewer build` exports a static snapshot to `olinkb-viewer/index.html`

## Uninstall behavior

For a full cleanup, run:

```bash
olinkb uninstall
```

That command removes the same bootstrap side effects that `olinkb --init` creates:

- repository scope: `.vscode/mcp.json` OlinKB entry, OlinKB protocol block in `.github/copilot-instructions.md`, repository memory triage skill, and the default `olinkb-viewer/` scaffold
- global scope: user-level MCP registration, user-level OlinKB instruction block, legacy instruction block if present, memory triage skill, persisted settings, `env.sh`, wrapper command, and shell profile hooks
- Python environment: `pip uninstall -y olinkb olinkb-mcp` from the current interpreter

Useful variants:

- `olinkb uninstall --scope repository`
- `olinkb uninstall --scope global`
- `olinkb uninstall --skip-package-uninstall`

Plain `pip uninstall olinkb` is not enough for a full teardown because generated files like shell hooks, wrappers, and persisted settings live outside the package-managed site-packages tree.

## Managed memories

Managed memories are curated Markdown records stored in the same backend with explicit applicability targets.

Current managed types:

- `documentation`
- `business_documentation`
- `development_standard`

Operational rule that matters most:

- only approved, applicable `development_standard` memories are eligible for automatic boot loading
- other managed memories remain queryable through `remember` and the viewer

Use the live viewer as the primary authoring surface.

## Release flow

Release versioning is tag-driven.

When GitHub Actions receives a tag like `v0.1.3`, the release workflow syncs that version into:

- the base package metadata
- the MCP addon metadata
- the addon dependency pin on `olinkb==...`

Typical maintainer flow:

```bash
git add .
git commit -m "Prepare v0.1.3 release"
git push origin main
git tag v0.1.3
git push origin v0.1.3
```

Then GitHub Actions:

- runs tests
- builds the base package
- builds the MCP addon package
- creates or updates the GitHub Release

For the detailed checklist, see [docs/releases/RELEASING.md](docs/releases/RELEASING.md).

## Scope limits

This repo currently focuses on the operational base layer. It does not yet include:

- semantic retrieval
- RLS
- LISTEN/NOTIFY invalidation
- the forgetting engine
