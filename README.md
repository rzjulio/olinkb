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

- Official MCP Python SDK server over `stdio`
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

On Windows, run the same commands from PowerShell, Command Prompt, or Windows Terminal.

On Windows, installation can look idle for a while because the wheel still needs to install runtime dependencies. If you want visible progress and the best chance of staying on binary wheels, use:

```bash
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
```

Explicit Windows examples:

```powershell
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init --scope global
```

```bat
pipx install --pip-args="-v --prefer-binary" https://github.com/rzjulio/olinkb/releases/download/v0.1.0/olinkb-0.1.0-py3-none-any.whl
olinkb --init --scope global
```

If `asyncpg` has no compatible wheel for that Python build, `pip` may compile it from source and that is usually the slowest step.

`--init` asks only for the PostgreSQL URL and team, then detects the project name from the current workspace directory automatically.

It also lets the user choose between:

- `1 repository`: writes `.vscode/mcp.json` and `.github/copilot-instructions.md` in the current repository
- `2 global`: writes the VS Code user-level MCP configuration and a user-level `.copilot/instructions.md`

Bootstrap also installs the `memory-relevance-triage` skill:

- repository scope: `.copilot/skills/memory-relevance-triage/SKILL.md`
- global scope: `~/.copilot/skills/memory-relevance-triage/SKILL.md`

Global MCP registration paths:

- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Linux: `~/.config/Code/User/mcp.json`
- Windows: `%APPDATA%\Code\User\mcp.json`
- Windows fallback if `APPDATA` is missing or blank: `%USERPROFILE%\AppData\Roaming\Code\User\mcp.json`

Instructions file behavior:

- repository scope merges the OlinKB protocol block into `.github/copilot-instructions.md`
- global scope writes a cross-repository instructions file at `~/.copilot/instructions.md`
- repository scope installs the memory triage skill into `.copilot/skills/memory-relevance-triage/SKILL.md`
- global scope installs the same skill into `~/.copilot/skills/memory-relevance-triage/SKILL.md`
- OlinKB does not modify repository-local `.copilot/` directories during global setup; existing repo-local instructions there stay untouched
- if `.github/copilot-instructions.md` already contains non-OlinKB sections, OlinKB replaces only its own `## OlinKB Memory Protocol` block and leaves the other repository guidance in place
- if `~/.copilot/instructions.md` already exists, OlinKB replaces only its own `## OlinKB Memory Protocol` block there and preserves the rest of the user's global guidance
- OlinKB does not decide precedence between repository instructions and any separate user/global instructions already loaded by VS Code or Copilot; its guarantee is coexistence at the file level, not editor-level merge priority
- global setup therefore does not overwrite repo-local instructions; it adds a reusable base protocol at the user level while repository instructions can still be more specific

The developer needs:

- Python 3.11+
- `pipx` or `pip`
- access to the external PostgreSQL connection string
- the team name
- optionally, the default project name

## Complete uninstall

OlinKB does not currently provide an `uninstall` command.

To remove it completely, clean up the CLI package, the VS Code MCP registration, any generated workspace files, and optionally the PostgreSQL data.

### 1. Remove the CLI package

If you installed OlinKB with `pipx`:

```bash
pipx uninstall olinkb
```

If you installed it with `pip` instead:

```bash
python -m pip uninstall olinkb
```

### 2. Remove the MCP registration from VS Code

If you used repository installation (`olinkb --init` and chose `repository`):

- remove the `olinkb` server entry from `.vscode/mcp.json`
- if `.vscode/mcp.json` only contains OlinKB, you can delete the file instead
- remove the generated OlinKB protocol block from `.github/copilot-instructions.md` if you no longer want repository-level agent instructions
- remove `.copilot/skills/memory-relevance-triage/SKILL.md` if you no longer want the repository-local memory triage skill

Example cleanup:

```bash
rm -f .vscode/mcp.json
```

Windows equivalents:

```powershell
Remove-Item .vscode\mcp.json
```

```bat
del .vscode\mcp.json
```

If you used global installation (`olinkb --init` and chose `global`), remove the `olinkb` entry from the VS Code user-level MCP file, or delete the file if OlinKB is the only configured server:

- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Linux: `~/.config/Code/User/mcp.json`
- Windows: `%APPDATA%\\Code\\User\\mcp.json`

Global instructions are also written to `~/.copilot/instructions.md` on macOS/Linux and `%USERPROFILE%\\.copilot\\instructions.md` on Windows.

The memory triage skill is also written to `~/.copilot/skills/memory-relevance-triage/SKILL.md` on macOS/Linux and `%USERPROFILE%\\.copilot\\skills\\memory-relevance-triage\\SKILL.md` on Windows.

If you no longer want the global OlinKB guidance, remove the generated `## OlinKB Memory Protocol` block from that global instructions file, or delete the file only if it contains no other user guidance you want to keep.

If you no longer want the global OlinKB memory triage skill, delete `~/.copilot/skills/memory-relevance-triage/SKILL.md` or the containing `memory-relevance-triage` directory.

If `APPDATA` is not available on Windows, OlinKB falls back to `%USERPROFILE%\\AppData\\Roaming\\Code\\User\\mcp.json`.

Windows delete commands, only if that file contains no other MCP servers you want to keep:

```powershell
Remove-Item "$env:APPDATA\Code\User\mcp.json"
```

```bat
del "%APPDATA%\Code\User\mcp.json"
```

If you initialized globally from PowerShell or Command Prompt, the interactive command is still the same:

```powershell
olinkb --init --scope global
```

```bat
olinkb --init --scope global
```

### 3. Remove generated workspace artifacts

If you created the viewer scaffold or a static viewer build, remove the generated directory:

```bash
rm -rf olinkb-viewer
```

### 4. Optionally remove PostgreSQL data

OlinKB stores memories, sessions, review state, and audit data in PostgreSQL.

That data is not removed automatically when you uninstall the CLI or delete the MCP configuration.

If you want a full local teardown, drop the OlinKB database objects manually. Only do this if the database is disposable or you have coordinated it with your team.

Example:

```sql
DROP TABLE IF EXISTS managed_memory_targets CASCADE;
DROP TABLE IF EXISTS project_members CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS memories CASCADE;
DROP TABLE IF EXISTS team_members CASCADE;
```

If you are using the local Docker Compose setup for development, you can also stop and remove that environment:

```bash
cd docker
docker compose down -v
```

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

For startup, the live viewer now only requires `OLINKB_PG_URL`. It no longer requires `OLINKB_USER` or `OLINKB_TEAM` just to boot the read-only browsing surface. If you later use authenticated viewer flows like login or managed-document authoring, OlinKB will provision a local viewer fallback team internally when no default team is configured.

This repository also includes a read-only viewer scaffold under `olinkb-viewer` for static exports.

Use it when you need a portable point-in-time snapshot of everything currently stored in PostgreSQL:

```bash
olinkb viewer build
```

That command writes `olinkb-viewer/index.html` with embedded data, so the file can be opened locally in a browser or hosted as a static page without any running backend. It is a snapshot/export path, not the primary path for massive datasets.

## Managed Memories

The live viewer now includes a managed-memory flow for curated Markdown knowledge.

Use it when an admin or lead needs to publish durable guidance that should stay searchable and reviewable across projects without creating ad hoc memory blobs.

Managed memories currently use three internal types:

- `documentation`: engineering reference material that stays searchable
- `business_documentation`: business-facing reference material, restricted to admins
- `development_standard`: approved engineering standards that stay searchable and can also influence startup context

The high-level viewer flow is:

1. Open `olinkb viewer`.
2. Create or update a managed Markdown document.
3. Choose the managed type and applicability targets (`global` or one or more `project` targets).
4. Save it as an approved managed memory.

Applicability matters at retrieval time:

- `boot_session` stays lean and only auto-loads approved `development_standard` memories that apply to the active project.
- `documentation` and `business_documentation` are excluded from boot loading.
- `remember` can still return applicable managed memories alongside regular memories when they are relevant to the query.

For curated administration flows, OlinKB exposes `create_managed_memory`, `update_managed_memory`, `list_managed_memories`, and `archive_managed_memory` through the MCP server, plus the matching live viewer HTTP endpoints.

## Current scope

This repository implements the foundation slice, not the full long-term platform. It currently focuses on shared storage, MCP exposure, and operational setup. It does not yet include RLS, semantic retrieval, LISTEN/NOTIFY invalidation, or the forgetting engine.

## Documentation

- Detailed developer setup and commands: [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md)
- End-to-end technical architecture and runtime guide: [docs/olinkb-funcionamiento-end-to-end.md](docs/olinkb-funcionamiento-end-to-end.md)
- Visual HTML companion for the end-to-end guide: [olinkb-viewer/olinkb-end-to-end-visual-companion.html](olinkb-viewer/olinkb-end-to-end-visual-companion.html)
- Release checklist: [docs/releases/RELEASING.md](docs/releases/RELEASING.md)
- Release template: [docs/releases/TEMPLATE.md](docs/releases/TEMPLATE.md)
- Initial release notes: [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md)
- Changelog: [docs/CHANGELOG.md](docs/CHANGELOG.md)

## Status

The current test suite is passing, and the repository is prepared for tagged GitHub Releases that publish installable wheel assets for developers.
