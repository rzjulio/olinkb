# OlinKB

OlinKB is a local MCP server that gives development agents shared, queryable team memory backed by PostgreSQL.

It is designed to make team knowledge available inside the coding flow: the editor starts OlinKB as an MCP server, the agent calls memory tools when context is needed, and PostgreSQL acts as the shared source of truth.

## What the project does

OlinKB provides a small set of tools for team memory inside development agents:

- `boot_session`: starts a working session and loads relevant memory
- `remember`: searches prior team or project knowledge
- `save_memory`: persists decisions, discoveries, and useful procedures
- `end_session`: closes a working session with a summary
- `forget`: soft-deletes memory with audit traceability

The current implementation focuses on the operational foundation:

- FastMCP server over `stdio`
- PostgreSQL-backed storage
- local session state
- in-memory read cache
- CLI packaging and setup workflow
- GitHub Release packaging for installation

## How it works

The runtime model is intentionally simple:

1. A developer installs the `olinkb` CLI.
2. The user runs `olinkb --init` and chooses repository or global installation.
3. VS Code registers OlinKB as an MCP server using `stdio`.
4. The coding agent invokes OlinKB tools when it needs shared memory.
5. OlinKB reads and writes team memory in PostgreSQL.

That means OlinKB is not a desktop app and not a permanently running daemon. It is a local command-line tool that the editor starts on demand.

## Who this is for

- teams that want shared memory for coding agents
- repositories that need repeatable conventions and decision recall
- developers who want a one-command MCP setup against a shared PostgreSQL database

## Installation summary

For developers, the expected install path is a GitHub Release wheel plus a one-shot initialization command.

Typical usage:

```bash
pipx install https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init
```

`--init` asks only for the PostgreSQL URL and team, then detects the project name from the current workspace directory automatically.

It also lets the user choose between:

- `1 repository`: writes `.vscode/mcp.json` and `.github/copilot-instructions.md` in the current repository
- `2 global`: writes the VS Code user-level MCP configuration and skips repository instructions

The developer needs:

- Python 3.11+
- `pipx` or `pip`
- access to the external PostgreSQL connection string
- the team name
- optionally, the default project name

## Repository structure

- [src/olinkb](src/olinkb): package source code
- [tests](tests): test suite
- [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md): detailed setup and operational guide
- [docs/releases](docs/releases): release notes, templates, and maintainer release guide
- [docker](docker): local PostgreSQL helper setup for development
- [docs/CHANGELOG.md](docs/CHANGELOG.md): version history

## Main commands

- `olinkb mcp`
- `olinkb --init`
- `olinkb migrate`
- `olinkb add-member --username ...`
- `olinkb viewer`
- `olinkb viewer build`

## Viewer modes

Use the live viewer as the primary exploration path:

```bash
olinkb viewer
```

That starts the HTTP viewer backed directly by PostgreSQL, so search stays server-side through `/api/viewer`. This is the scalable path for large datasets.

This repository also includes a read-only viewer scaffold under `olinkb-viewer` for static exports.

Use it when you need a portable point-in-time snapshot of everything currently stored in PostgreSQL:

```bash
olinkb viewer build
```

That command writes `olinkb-viewer/index.html` with embedded data, so the file can be opened locally in a browser or hosted as a static page without any running backend. It is a snapshot/export path, not the primary path for massive datasets.

## Current scope

This repository implements the foundation slice, not the full long-term platform. It currently focuses on shared storage, MCP exposure, and operational setup. It does not yet include RLS, semantic retrieval, LISTEN/NOTIFY invalidation, or the forgetting engine.

## Documentation

- Detailed developer setup and commands: [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md)
- Release checklist: [docs/releases/RELEASING.md](docs/releases/RELEASING.md)
- Release template: [docs/releases/TEMPLATE.md](docs/releases/TEMPLATE.md)
- Initial release notes: [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md)
- Changelog: [docs/CHANGELOG.md](docs/CHANGELOG.md)

## Status

The current test suite is passing, and the repository is prepared for tagged GitHub Releases that publish installable wheel assets for developers.
