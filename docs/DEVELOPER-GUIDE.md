# OlinKB Developer Guide

This document contains the operational setup and day-to-day developer information that previously lived in the main README.

## Current status

This repository now contains the first implementation slice for the current PostgreSQL-based architecture:

- Python package scaffold
- PostgreSQL migration runner
- Local working-memory session manager
- In-memory read cache with TTL and prefix invalidation
- FastMCP server with the core tools
- CLI commands to migrate the database, add members, and run the server
- Docker Compose for local PostgreSQL using the official PostgreSQL image

## Quick start with Docker

```bash
cd docker
docker compose up -d
```

If port `5432` is already in use on your machine, start it on another host port:

```bash
cd docker
OLINKB_PG_PORT=5433 docker compose up -d
```

This starts PostgreSQL on `localhost:5432` with:

- database: `olinkb`
- user: `olinkb`
- password: `olinkb`
- extensions pre-enabled: `uuid-ossp`, `pgcrypto`, `pg_trgm`

Connection string:

```bash
postgresql://olinkb:olinkb@localhost:5432/olinkb
```

If you started the container on another host port, update the connection string accordingly, for example:

```bash
postgresql://olinkb:olinkb@localhost:5433/olinkb
```

The matching environment example is available in `.env.example`.

## Environment variables

- `OLINKB_PG_URL`: PostgreSQL connection string
- `OLINKB_TEAM`: default team name
- `OLINKB_USER`: username used by the local MCP process
- `OLINKB_PROJECT`: optional default project name
- `OLINKB_CACHE_TTL_SECONDS`: optional cache TTL, defaults to `300`
- `OLINKB_CACHE_MAX_ENTRIES`: optional cache size, defaults to `256`

## Commands

```bash
olinkb migrate
olinkb add-member --username rzjulio --role lead
olinkb --init
olinkb mcp
olinkb template mcp --pg-url postgresql://olinkb:olinkb@localhost:5433/olinkb --team mi-equipo
olinkb template instructions
olinkb serve
```

`olinkb mcp` is an alias for the stdio MCP server entrypoint.

## Install for developers

The recommended developer installation target is a wheel published in GitHub Releases.

Once a release exists, the developer can install OlinKB with `pipx` directly from the downloaded wheel:

```bash
pipx install ./olinkb-0.1.0-py3-none-any.whl
olinkb --help
```

If you prefer to keep everything remote, you can also install from the release asset URL:

```bash
pipx install https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
```

After installation, the developer only needs the external PostgreSQL connection string and team name:

```bash
olinkb --init
```

The interactive initializer asks for:

- installation scope: `1 repository` or `2 global`
- PostgreSQL URL
- team name

For `repository`, the project name is detected automatically from the current directory name and written into the generated MCP configuration.

For `global`, OlinKB writes the MCP server into the user's VS Code `mcp.json` and skips repository instructions because they are repository-specific.

## GitHub release flow

This repository includes [release automation](releases/RELEASING.md) and a workflow that builds a wheel and source distribution and attaches both files to a GitHub Release whenever you push a tag like `v0.1.0`.

The repository also includes CI, which runs the test suite on pushes and pull requests. The release workflow runs its own test job first and only publishes assets if those tests pass.

Typical maintainer flow:

```bash
git add .
git commit -m "Prepare v0.1.0 release"
git push origin main
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions will then:

- run the test suite
- build `dist/*.whl`
- build `dist/*.tar.gz`
- create or update the GitHub Release for that tag
- upload both artifacts as downloadable assets

The prepared release notes for the initial version live in [releases/v0.1.0.md](releases/v0.1.0.md), future releases can start from [releases/TEMPLATE.md](releases/TEMPLATE.md), and the maintainer checklist lives in [releases/RELEASING.md](releases/RELEASING.md). The version history is tracked in [CHANGELOG.md](CHANGELOG.md).

## VS Code integration helpers

Use the built-in template commands to wire OlinKB into VS Code and your repository instructions:

```bash
olinkb template mcp --pg-url postgresql://olinkb:olinkb@localhost:5433/olinkb --team mi-equipo
olinkb template instructions
```

The first command prints a ready-to-paste `mcp.json` server block using `olinkb mcp`. The second prints the recommended repository instruction block so the agent knows when to call `boot_session`, `remember`, `save_memory`, and `end_session`.

If you want the end-user flow to be a single step, use:

```bash
olinkb --init
```

That command asks for the install scope, PostgreSQL URL, and team.

When the user chooses `repository`, OlinKB detects the project from the current workspace folder and writes `.vscode/mcp.json` and `.github/copilot-instructions.md` in the current workspace, preserving other MCP servers already registered and avoiding duplicate OlinkB protocol blocks when rerun.

When the user chooses `global`, OlinKB writes the server into the VS Code user-level `mcp.json` and skips repository instructions.

## Tools exposed by the server

- `boot_session`
- `remember`
- `save_memory`
- `end_session`
- `forget`

## Notes

This is the foundation slice, not the full platform. It intentionally omits RLS policies, semantic retrieval, LISTEN/NOTIFY invalidation, and the forgetting engine until later phases.

Semantic search remains a future enhancement. When OlinKB reaches that phase, PostgreSQL can be extended with `pgvector` and the `vector` extension to support semantic retrieval and similarity search.