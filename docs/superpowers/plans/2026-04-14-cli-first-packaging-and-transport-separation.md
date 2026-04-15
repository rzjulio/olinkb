# CLI-First Packaging And Transport Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split OlinKB into a CLI-first base install plus an optional MCP transport while preserving the current behavior through a direct CLI tool transport.

**Architecture:** Keep `OlinKBApp` and storage as the shared core, add a transport-neutral tool handler layer, move MCP-specific code behind a dedicated transport module, and add a JSON-based CLI transport reachable through `olinkb tool ...`. Packaging changes make `mcp` optional for the base wheel and introduce a separate addon package for MCP installs.

**Tech Stack:** Python 3.11+, setuptools, argparse, PostgreSQL via asyncpg, MCP Python SDK, pytest.

---

### Task 1: Lock the transport split in tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_templates.py`
- Create: `tests/test_tool_cli.py`

- [ ] Add parser and bootstrap tests that define `cli` mode, `olinkb tool ...`, and CLI-mode init behavior.
- [ ] Add template tests that define the CLI instructions contract separately from MCP instructions.
- [ ] Add focused CLI transport tests for JSON input/output and dispatch wiring.

### Task 2: Extract transport-neutral tool handlers

**Files:**
- Create: `src/olinkb/tool_handlers.py`
- Modify: `src/olinkb/server.py`

- [ ] Move the app singleton and tool-level async handlers out of the current MCP module into a shared handler module.
- [ ] Keep the existing `olinkb.server` import surface working as a thin compatibility shim.

### Task 3: Add direct CLI transport

**Files:**
- Create: `src/olinkb/tool_cli.py`
- Modify: `src/olinkb/cli.py`

- [ ] Add `olinkb tool <tool-name> --json '{...}'` with stable JSON stdout.
- [ ] Route the CLI transport through the same tool handlers used by MCP.
- [ ] Keep runtime imports lazy so lightweight commands stay fast.

### Task 4: Isolate MCP as an optional transport

**Files:**
- Create: `src/olinkb/mcp_transport.py`
- Modify: `src/olinkb/server.py`
- Modify: `src/olinkb/cli.py`

- [ ] Move MCP-only schema and stdio server code into a dedicated module.
- [ ] Make `olinkb mcp` fail with a clear install hint when the optional MCP dependency is missing.
- [ ] Keep the rest of the base CLI usable without the MCP package installed.

### Task 5: Teach bootstrap and templates about install mode

**Files:**
- Modify: `src/olinkb/bootstrap.py`
- Modify: `src/olinkb/templates.py`
- Modify: `src/olinkb/cli.py`

- [ ] Add `mcp|cli` mode selection to `olinkb --init`.
- [ ] Write MCP config only for MCP mode, and remove any existing `olinkb` MCP registration when switching to CLI mode.
- [ ] Generate distinct instructions so agents know whether to use MCP tools or `olinkb tool ...` commands.

### Task 6: Split packaging and release artifacts

**Files:**
- Modify: `pyproject.toml`
- Create: `packages/olinkb-mcp/pyproject.toml`
- Create: `packages/olinkb-mcp/README.md`
- Create: `packages/olinkb-mcp/src/olinkb_mcp/__init__.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

- [ ] Remove `mcp` from the base runtime dependencies and keep it only in development tooling or the addon package.
- [ ] Add a separate `olinkb-mcp` distributable that depends on the base package plus `mcp`.
- [ ] Build and publish both artifacts in the release workflow.

### Task 7: Update operator docs

**Files:**
- Modify: `README.md`
- Modify: `docs/DEVELOPER-GUIDE.md`
- Modify: `docs/releases/RELEASING.md`

- [ ] Document base CLI install, optional MCP install, and the new `olinkb tool ...` transport.
- [ ] Explain mode selection in `olinkb --init` and the cleanup/switching behavior.
- [ ] Update release guidance so maintainers know to ship both artifacts.