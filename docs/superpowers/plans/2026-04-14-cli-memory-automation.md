# CLI Memory Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CLI-first automatic memory triage and capture so OlinKB can decide when content should be saved and when it looks like documentation or another durable memory type.

**Architecture:** Introduce a deterministic automation module for scoring and classification, expose it through shared tool handlers, and surface it primarily through `olinkb tool analyze_memory` and `olinkb tool capture_memory`. Reuse the existing `save_memory` pipeline for durable persistence so the new feature inherits current permissions, metadata enrichment, and audit logging.

**Tech Stack:** Python 3.11+, argparse, async app/service layer, PostgreSQL-backed storage, pytest.

---

### Task 1: Lock the CLI automation contract in tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_tool_cli.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_templates.py`
- Modify: `tests/test_app.py`

- [ ] Add parser and tool-transport tests that define `analyze_memory` and `capture_memory` as valid CLI-first tools.
- [ ] Add app tests that define `capture_memory` behavior for high-confidence auto-save and permission-aware suggestion fallback.
- [ ] Add server and template tests that keep MCP compatible while shifting operator guidance toward CLI automation.

### Task 2: Build deterministic analysis module

**Files:**
- Create: `src/olinkb/automation.py`
- Test: `tests/test_app.py`

- [ ] Implement reusable input normalization, scoring, title inference, memory-type inference, URI generation, and documentation detection in a transport-neutral module.
- [ ] Keep the module storage-free and fully explainable through returned signals and reasons.

### Task 3: Integrate analysis into the app layer

**Files:**
- Modify: `src/olinkb/app.py`
- Modify: `src/olinkb/tool_handlers.py`
- Modify: `src/olinkb/server.py`
- Test: `tests/test_app.py`
- Test: `tests/test_server.py`

- [ ] Add `analyze_memory(...)` and `capture_memory(...)` to `OlinKBApp`.
- [ ] Make `capture_memory(...)` auto-save only when the analyzer returns `save`, and degrade permission issues to `suggest`.
- [ ] Expose both methods through the shared tool surface.

### Task 4: Publish the new tools through CLI and MCP transports

**Files:**
- Modify: `src/olinkb/mcp_transport.py`
- Modify: `src/olinkb/tool_cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_tool_cli.py`
- Test: `tests/test_server.py`

- [ ] Add schemas for `analyze_memory` and `capture_memory`.
- [ ] Ensure JSON input/output stays stable in the direct CLI transport.
- [ ] Keep existing tool behavior untouched.

### Task 5: Update docs and CLI guidance

**Files:**
- Modify: `src/olinkb/templates.py`
- Modify: `README.md`
- Test: `tests/test_templates.py`

- [ ] Update CLI-mode instructions so users and agents prefer automation tools before manual `save_memory`.
- [ ] Add examples to the README for dry-run analysis and automatic capture.

### Task 6: Verify the feature end-to-end at test level

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_tool_cli.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_app.py`

- [ ] Run focused pytest targets for CLI, app, templates, and server coverage.
- [ ] Fix any regressions introduced by the new tool surface.