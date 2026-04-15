# CLI Memory Automation Design

**Date:** 2026-04-14  
**Status:** Approved for implementation in-session  
**Scope:** CLI-first automatic memory triage, classification, and capture with MCP compatibility

## Goal

Make OlinKB detect much better when work should become memory, when something looks like technical documentation, and when content is worth saving, while keeping the first implementation centered on the direct CLI transport.

## Summary

OlinKB will add a deterministic automation layer that sits above raw `save_memory`.

The new layer will expose two new tools through the shared tool surface:

- `analyze_memory`: dry-run triage and classification
- `capture_memory`: analyze the input and automatically persist it when confidence is high enough

Because the tool surface is shared, both `olinkb tool ...` and MCP can use the same feature, but all operator guidance and examples will prioritize the CLI transport.

## Product Rules

### Automation Outcomes

Each analysis must end in one of these outcomes:

- `skip`: not valuable enough to store
- `suggest`: valuable, but should not be auto-saved yet
- `save`: safe to auto-save immediately

### Balanced Automation Policy

This implementation uses the balanced mode as the default behavior:

- auto-save only when confidence is high
- suggest when confidence is medium or when the content looks important but risky
- skip when confidence is low

### Documentation Detection

The automation layer should detect at least these documentation-like cases:

- technical documentation
- business documentation
- development standards

Documentation should be inferred from signals such as architectural language, setup steps, API or contract wording, reusable explanations, markdown structure, and norm-setting phrases.

### Permission-Aware Behavior

If analysis suggests a memory type that the current actor cannot save directly, the system must degrade to `suggest` instead of raising a hard failure when using `capture_memory`.

Examples:

- `business_documentation` for a non-admin becomes `suggest`
- org/team/system scope writes without approver rights become `suggest`

### CLI-First Operator Experience

Repository instructions and docs should point users first to:

- `olinkb tool analyze_memory --json ...`
- `olinkb tool capture_memory --json ...`

Raw `save_memory` remains available for explicit/manual writes.

## Architecture

### New Automation Module

Add a new module responsible for deterministic analysis.

Responsibilities:

- normalize input
- extract structured hints from content
- score relevance
- infer the best memory type
- detect documentation candidates
- choose `skip` vs `suggest` vs `save`
- generate default title, tags, metadata, and URI hints

This module must stay independent from storage so it is easy to test.

### App Integration

`OlinKBApp` will expose two new methods:

- `analyze_memory(...)`
- `capture_memory(...)`

`capture_memory(...)` will reuse `analyze_memory(...)`, then call `save_memory(...)` only when the computed action is `save`.

### Shared Tool Surface

The new methods must be exposed through:

- `src/olinkb/tool_handlers.py`
- `src/olinkb/server.py`
- `src/olinkb/mcp_transport.py`

This preserves transport parity while keeping CLI as the documented primary interface.

## Analysis Contract

### Input Shape

The automation tools should accept:

- `content` (required)
- `title` (optional)
- `project` (optional)
- `scope_hint` (optional)
- `memory_type_hint` (optional)
- `tags` (optional)
- `metadata` (optional)
- `session_id` (optional)
- `author` (optional)
- `source_surface` (optional, defaults to `cli`)
- `files` (optional list)
- `commands` (optional list)
- `auto_save` (for `capture_memory`, defaults to true)

### Output Shape

Both tools should return structured analysis with at least:

- `action`
- `should_save`
- `relevance_score`
- `suggested_title`
- `suggested_memory_type`
- `suggested_scope`
- `suggested_uri`
- `suggested_tags`
- `reasons`
- `signals`
- `metadata`
- `documentation_candidate`

`capture_memory` should additionally return persisted memory details when a save actually happens.

## Heuristics

### Relevance Signals

The initial version should use deterministic, explainable heuristics.

Positive signals:

- structured headings like `What`, `Why`, `Where`, `Learned`, `Decision`, `Evidence`
- enough content length to be reusable later
- explicit bugfix or root-cause language
- decision or tradeoff language
- procedural/setup language
- architecture/documentation language
- attached file paths or commands

Negative signals:

- very short content
- no structure and no reusable signal
- purely conversational filler

### Type Inference Priority

When multiple types compete, prefer the most specific durable interpretation:

1. `business_documentation`
2. `development_standard`
3. `documentation`
4. `bugfix`
5. `procedure`
6. `decision`
7. `discovery`
8. fallback `fact`

### Documentation Scope Defaults

For CLI-first automation:

- project content defaults to `documentation_scope=repo`
- org/team/system content defaults to `documentation_scope=global`
- project documentation should set `applicable_projects=[project]` when a project is available

## URI Strategy

Auto-generated URIs should stay deterministic and readable.

Suggested buckets:

- `bugfix` -> `bugfixes`
- `decision` -> `decisions`
- `procedure` -> `procedures`
- `discovery` -> `discoveries`
- `documentation` -> `documentation`
- `business_documentation` -> `business-documentation`
- `development_standard` -> `development-standards`
- fallback -> `notes`

Example:

- `project://olinkb/documentation/cli-memory-automation`

## Error Handling

`analyze_memory` should never fail because the caller omitted optional inference fields.

`capture_memory` should return `suggest` rather than throw when:

- the inferred type requires stronger permissions
- the inferred scope cannot be written by the actor

Normal validation errors should still surface when the input itself is invalid.

## Testing Strategy

Add tests first for:

- CLI parser accepting the new tool names
- CLI transport returning dry-run analysis
- app-level `capture_memory` auto-saving high-confidence bugfix/procedure content
- app-level `capture_memory` suggesting documentation when permissions block auto-save
- server/MCP tool definitions including the new tools
- template instructions steering CLI users toward the new automation tools

## Non-Goals

This change does not introduce:

- machine-learning classification
- semantic deduplication
- persistent candidate queues
- viewer approval inbox for auto-capture suggestions
- automatic convention approval

Those can be added later once the deterministic CLI-first automation proves useful.