# OlinKB Developer Guide

This document contains the operational setup and day-to-day developer information that previously lived in the main README.

## Current status

This repository now contains the first implementation slice for the current PostgreSQL-based architecture:

- Python package scaffold
- PostgreSQL migration runner
- Local working-memory session manager
- In-memory read cache with TTL and prefix invalidation
- Official MCP Python SDK server with the core tools
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
- extensions pre-enabled: `uuid-ossp`, `pg_trgm`

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

For the main MCP/server runtime, `OLINKB_TEAM` and `OLINKB_USER` still define the default identity context. The live viewer is looser: `olinkb viewer` only needs `OLINKB_PG_URL` to start browsing data, and it no longer requires `OLINKB_USER` or `OLINKB_TEAM` at startup.

## Commands

```bash
olinkb migrate
olinkb add-member --username rzjulio --role lead
olinkb --init
olinkb mcp
olinkb viewer
olinkb viewer build
olinkb template mcp --pg-url postgresql://olinkb:olinkb@localhost:5433/olinkb --team example-team
olinkb template instructions
olinkb serve
```

`olinkb mcp` is an alias for the stdio MCP server entrypoint.

`olinkb viewer` starts the live HTTP viewer backed by PostgreSQL. Startup only requires `OLINKB_PG_URL`; `OLINKB_USER` and `OLINKB_TEAM` are no longer required just to boot the viewer.

`olinkb viewer build` exports a static snapshot to `olinkb-viewer/index.html`.

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

On Windows, use the same command from PowerShell, Command Prompt, or Windows Terminal.

After installation, the developer only needs the external PostgreSQL connection string and team name:

```bash
olinkb --init
```

The interactive initializer asks for:

- installation scope: `1 repository` or `2 global`
- PostgreSQL URL
- team name

For `repository`, the project name is detected automatically from the current directory name and written into the generated MCP configuration.

For `global`, OlinKB writes the MCP server into the user's VS Code `mcp.json` and writes a reusable base instructions file into the user's `.copilot` directory.

In both scopes, OlinKB also installs the `memory-relevance-triage` skill so agents have a reusable decision aid for whether a result deserves durable memory.

Global MCP registration paths:

- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Linux: `~/.config/Code/User/mcp.json`
- Windows: `%APPDATA%\Code\User\mcp.json`
- Windows fallback if `APPDATA` is missing or blank: `%USERPROFILE%\AppData\Roaming\Code\User\mcp.json`

Instruction file behavior:

- repository scope writes or updates `.github/copilot-instructions.md`
- global scope writes or updates `~/.copilot/instructions.md`
- repository scope writes or updates `.copilot/skills/memory-relevance-triage/SKILL.md`
- global scope writes or updates `~/.copilot/skills/memory-relevance-triage/SKILL.md`
- OlinKB does not create or manage repository-local `.copilot/` directories during global setup, so existing repo-local instruction layouts there remain untouched
- if `.github/copilot-instructions.md` already has other repository guidance, only the generated `## OlinKB Memory Protocol` block is replaced on rerun
- if `~/.copilot/instructions.md` already has other user guidance, only the generated `## OlinKB Memory Protocol` block is replaced on rerun
- precedence between repository instructions and any separate user/global Copilot instructions is outside OlinKB; the bootstrap only guarantees additive coexistence and non-destructive file updates
- global setup therefore does not conflict with repo-local instructions; it adds a user-level MCP registration plus a reusable cross-repository memory protocol

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
olinkb template mcp --pg-url postgresql://olinkb:olinkb@localhost:5433/olinkb --team example-team
olinkb template instructions
```

The first command prints a ready-to-paste `mcp.json` server block using `olinkb mcp`. The second prints the recommended instruction block so the agent knows when to call `boot_session`, `remember`, `save_memory`, and `end_session`.

`olinkb template instructions` only renders content to stdout. The actual bootstrap paths are `.github/copilot-instructions.md` for repository installs and `~/.copilot/instructions.md` for global installs. The memory triage skill is bootstrapped into `.copilot/skills/memory-relevance-triage/SKILL.md` for repository installs and `~/.copilot/skills/memory-relevance-triage/SKILL.md` for global installs.

If you want the end-user flow to be a single step, use:

```bash
olinkb --init
```

That command asks for the install scope, PostgreSQL URL, and team.

When the user chooses `repository`, OlinKB detects the project from the current workspace folder and writes `.vscode/mcp.json` and `.github/copilot-instructions.md` in the current workspace, preserving other MCP servers already registered and avoiding duplicate OlinkB protocol blocks when rerun.

It also writes `.copilot/skills/memory-relevance-triage/SKILL.md` in the current workspace.

When the user chooses `global`, OlinKB writes the server into the VS Code user-level `mcp.json` and writes the memory protocol into `~/.copilot/instructions.md`.

It also writes the triage skill into `~/.copilot/skills/memory-relevance-triage/SKILL.md`.

On Windows, the global file is `%APPDATA%\Code\User\mcp.json`, with `%USERPROFILE%\AppData\Roaming\Code\User\mcp.json` as the fallback when `APPDATA` is unavailable.

On Windows, the global instructions file is `%USERPROFILE%\.copilot\instructions.md`.

On Windows, the global skill file is `%USERPROFILE%\.copilot\skills\memory-relevance-triage\SKILL.md`.

Exact Windows examples:

```powershell
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init --scope global
```

```bat
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init --scope global
```

For uninstall on Windows, remove the `olinkb` entry from that file, or delete the file only if it contains no other MCP servers:

```powershell
Remove-Item "$env:APPDATA\Code\User\mcp.json"
```

```bat
del "%APPDATA%\Code\User\mcp.json"
```

If you no longer want the global instructions, remove the generated `## OlinKB Memory Protocol` block from `%USERPROFILE%\.copilot\instructions.md`, or delete that file only if it contains no other user guidance.

If you no longer want the global triage skill, remove `%USERPROFILE%\.copilot\skills\memory-relevance-triage\SKILL.md` or the containing `memory-relevance-triage` directory.

## Tools exposed by the server

- `boot_session`
- `remember`
- `save_memory`
- `create_managed_memory`
- `update_managed_memory`
- `list_managed_memories`
- `archive_managed_memory`
- `propose_memory_promotion`
- `list_pending_approvals`
- `review_memory_proposal`
- `end_session`
- `forget`

## Managed memory flow

Managed memories are curated Markdown records that share the same canonical `memories` table as standard OlinKB entries, plus explicit applicability targets in `managed_memory_targets`.

The three managed types are:

- `documentation`: engineering documentation that remains searchable through the viewer and `remember`
- `business_documentation`: business-facing documentation, searchable but restricted to admins for management operations
- `development_standard`: approved engineering standards that are searchable and also eligible for boot loading

The live viewer is the primary authoring surface:

1. Run `olinkb viewer`.
2. Upload or edit a Markdown document through the managed-memory flow.
3. Select a managed type.
4. Assign applicability targets as `global` or one or more explicit `project` values.
5. Save or archive the managed record.

Role rules are enforced below the UI layer:

- admins and leads can create, edit, list, and archive managed engineering content
- only admins can manage `business_documentation`

If no default team is configured in the environment, the authenticated viewer flows use an internal fallback team (`viewer`) for member provisioning. That fallback is only for the viewer surface; the main MCP runtime still expects explicit identity defaults.
- project-targeted operations require active membership and lead/admin authority in every targeted project

## Boot and retrieval behavior

Managed memories affect retrieval in two distinct ways.

`boot_session` remains intentionally narrow. It only auto-loads approved `development_standard` memories whose applicability matches the active project. `documentation` and `business_documentation` never enter the boot payload.

`remember` stays query-driven. It can return applicable managed memories together with regular memories when PostgreSQL ranking finds them relevant. At a high level, this means technical documentation and approved standards can show up during recall without bloating startup context.

For managed-memory administration, use the dedicated surfaces instead of overloading `remember`:

- MCP tools: `create_managed_memory`, `update_managed_memory`, `list_managed_memories`, `archive_managed_memory`
- live viewer HTTP routes: `GET/POST/PUT/DELETE /api/managed-memories`
- proposal workflow: `propose_memory_promotion` and `review_memory_proposal` now normalize approved project proposals into `development_standard`

When documenting or reviewing boot behavior, keep the rule explicit: approved, applicable `development_standard` memories are the only managed entries eligible for automatic startup loading.

## Notes

This is the foundation slice, not the full platform. It intentionally omits RLS policies, semantic retrieval, LISTEN/NOTIFY invalidation, and the forgetting engine until later phases.

Semantic search remains a future enhancement. When OlinKB reaches that phase, PostgreSQL can be extended with `pgvector` and the `vector` extension to support semantic retrieval and similarity search.