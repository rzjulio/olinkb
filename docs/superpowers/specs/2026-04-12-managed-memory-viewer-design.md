# Managed Memory Viewer Design

**Date:** 2026-04-12  
**Status:** Proposed and validated with user  
**Scope:** Viewer-managed Markdown memories, scoped recall, and boot-session curation

## Goal

Allow admins and leads to upload and manage Markdown-based knowledge through the viewer, store that content as first-class memories in OlinKB, support `global` and multi-project applicability, and keep `boot_session` lean by loading only project-relevant `development_standard` memories.

## Summary

OlinKB will treat uploaded Markdown files as managed memories instead of introducing a separate documentation subsystem. The viewer will support three managed memory types:

- `documentation`
- `business_documentation`
- `development_standard`

All three types are indexed in the main memory store and are searchable through normal retrieval. Only `development_standard` is eligible for automatic inclusion in `boot_session`, and only when it applies to the active context.

The existing MCP proposal flow for conventions will be normalized into `development_standard` so that standards proposed through MCP and standards uploaded through the viewer end up in the same data model, the same Markdown-oriented formatting, and the same retrieval behavior.

## Product Rules

### Managed Memory Types

Use these exact internal values:

- `documentation`: technical development documentation, searchable, not boot-loaded
- `business_documentation`: business or functional documentation, searchable, not boot-loaded
- `development_standard`: conventions, standards, and working rules, searchable and boot-loadable

Viewer labels should remain human-readable:

- `Documentation`
- `Business Documentation`
- `Development Standard`

### Permissions

- `admin` and `lead` can create, edit, replace, and archive `documentation`
- `admin` and `lead` can create, edit, replace, and archive `development_standard`
- only `admin` can create, edit, replace, and archive `business_documentation`

### Applicability

Every managed memory can target either:

- `global`
- one or more projects

The viewer must make applicability obvious in listings, especially for memories attached to multiple projects.

### Boot Session Policy

`boot_session` must stay intentionally small.

It may auto-load only managed memories of type `development_standard` that apply to the active context.

It must not auto-load:

- `documentation`
- `business_documentation`

### Retrieval Policy

`remember` should search across normal memories and managed memories together.

It must support both behaviors:

- managed memories can appear in normal results when highly relevant
- callers can explicitly filter by memory type when they want focused retrieval

## Architectural Decision

Managed Markdown uploads will reuse the existing `memories` table as the canonical content store.

OlinKB will not create a separate documentation subsystem in v1.

Instead:

- the Markdown body is stored as memory content
- the managed status and origin are stored as structured metadata
- applicability is stored in an auxiliary targets table
- viewer and MCP proposal flows both produce the same final memory representation

This keeps search, audit, cache invalidation, and viewer payload generation aligned with the existing architecture.

## Data Model

### Base Memory Record

Managed memories remain rows in `memories`.

Relevant fields already used or required:

- `uri`
- `title`
- `content`
- `memory_type`
- `scope`
- `namespace`
- `author_id`
- `author_username`
- `metadata`
- `approval_status`
- `proposed_memory_type`
- `proposed_by`
- `proposed_at`
- `reviewed_by`
- `reviewed_at`
- `review_note`

### Managed Targets Table

Add a new table to express applicability without duplicating content.

Suggested shape:

```sql
CREATE TABLE managed_memory_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('global', 'project')),
    target_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (memory_id, target_type, target_value)
);
```

Semantics:

- `global` uses `target_value='*'`
- `project` uses `target_value='<project-name>'`

### Metadata Contract

Managed memories should persist consistent metadata in `metadata`.

Required keys:

- `managed: true`
- `source_format: markdown`
- `origin_channel: viewer_upload | mcp_proposal`
- `audience: engineering | business`

Recommended keys:

- `source_filename`
- `summary`
- `version_label`
- `applies_to`
- `final_memory_type`

### Traceability Requirements

Every managed memory must clearly preserve:

- who created or proposed it
- who approved it, when approval exists
- where it originated
- what final type was stored

For direct viewer uploads:

- `author_id` and `author_username` identify the uploader
- `origin_channel='viewer_upload'`
- `approval_status='approved'`
- `reviewed_by` and `reviewed_at` should be set to the same authorized actor who published the memory so the approver identity is explicit even without a separate proposal stage

For MCP proposals that become standards:

- the proposer must remain visible through `proposed_by` and related usernames
- the approver must remain visible through `reviewed_by`, `reviewed_at`, and usernames
- the final stored type must be `development_standard`
- `origin_channel='mcp_proposal'`

The UI must expose these two identities separately:

- `Proposed by`
- `Approved by`

For direct viewer uploads without a prior proposal, `Proposed by` and `Approved by` may resolve to the same authorized user.

## Scope Semantics

Managed memories do not need personal scope in this feature.

For this feature, the meaningful applicability is:

- global
- project-based

Implementation may continue to store a canonical `scope` and `namespace` on the base memory row, but applicability for viewer-managed knowledge must be resolved through `managed_memory_targets` instead of relying on a single namespace string.

## Viewer Experience

### New Managed Memory Area

The viewer should add a dedicated management area separate from the graph-centric memory browsing.

This area should support:

- listing managed memories
- filtering by type
- filtering by target project
- filtering by applicability mode (`global` or `project`)
- upload from `.md`
- replace content
- edit metadata and targets
- archive/delete

### Upload Flow

The upload form must require:

- `.md` file input
- title
- managed memory type
- applicability selection

Rules:

- `lead` must not see business-documentation creation options
- `admin` can select any of the three managed types
- project applicability must support selecting multiple projects

### Listing Requirements

Each managed memory card or row should show:

- title
- type label
- applicability badges
- created by
- approved by
- updated timestamp
- short summary or preview

The applicability display is important enough that it should not be hidden behind a details panel.

## MCP and Application Behavior

### Viewer Upload Path

The system should add application and transport methods to create managed memories from uploaded Markdown.

Required behavior:

- validate role
- validate `.md` content
- create or update managed memory content
- write target rows
- invalidate affected caches
- emit audit trail

### Proposal Normalization Path

The existing proposal flow for conventions should be normalized so that approved proposals land as `development_standard` records in the same managed-memory format.

That means:

- a developer proposal should target `development_standard`
- on approval, the final row should use `memory_type='development_standard'`
- stored content should follow the same Markdown-oriented structure used for viewer-created standards

This avoids a split between legacy convention records and viewer-created standards.

### Boot Session Loading

`boot_session` should load managed memories only when all of the following are true:

- `memory_type='development_standard'`
- the memory is approved
- the memory targets `global` or the active project
- the memory is not deleted or archived

`boot_session` should continue to avoid loading bulky technical or business documentation.

### Remember Search

`remember` should include managed memories in its search space.

It should also accept an optional memory-type filter so callers can ask for only:

- `documentation`
- `business_documentation`
- `development_standard`

Search results should make managed-memory provenance explicit in the payload.

Suggested fields:

- `memory_type`
- `origin_channel`
- `managed`
- `applies_to`

## Content Format

Managed memories should store Markdown content in a normalized, readable template.

For `development_standard`, the preferred structure is:

```md
# <Title>

## Purpose
<Why this standard exists>

## Rule
<What must be followed>

## Applies To
- Global or project list

## Notes
<Optional examples or clarifications>
```

For `documentation` and `business_documentation`, the system may allow more flexible Markdown, but should still preserve a summary and source metadata.

For approved MCP proposals, the content should be normalized into the standard template before being persisted as `development_standard`.

## Non-Goals

This change does not require:

- backward compatibility for existing throwaway data
- a separate document versioning subsystem
- loading technical or business docs into `boot_session`
- personal-scoped managed documents
- a new persistence backend

## Risks and Mitigations

### Risk: Boot-session inflation

Mitigation:

- only load `development_standard`
- require applicability filtering before load

### Risk: Viewer and MCP standards diverge in format

Mitigation:

- normalize approved proposals into the same Markdown structure as viewer-created standards

### Risk: Permission leakage for business content

Mitigation:

- enforce role checks in app/storage layer, not just in viewer UI

### Risk: Applicability becomes opaque when many projects are selected

Mitigation:

- expose project targets directly in listings and result payloads

## Implementation Boundaries

Expected code areas:

- storage migration for managed targets and type expansion
- app methods for create/update/delete managed memories
- viewer server endpoints for upload and managed-memory listings
- viewer UI for managed-memory administration
- search and boot-session updates to respect managed types and targets
- tests covering permissions, applicability, boot loading, retrieval, and approval traceability

## Acceptance Criteria

1. `admin` and `lead` can upload Markdown files as `documentation` or `development_standard` from the viewer.
2. Only `admin` can upload or administer `business_documentation`.
3. Managed memories can target `global` or multiple projects.
4. Viewer listings clearly show the projects where a managed memory applies.
5. `boot_session` includes only approved `development_standard` memories relevant to the active context.
6. `documentation` and `business_documentation` remain searchable through `remember` but are excluded from `boot_session`.
7. Developer proposals approved through MCP are persisted as `development_standard` using the same normalized Markdown-style format as viewer-created standards.
8. Every managed memory exposes who proposed it or created it and who approved it when approval was involved.
9. Search results can include managed memories by relevance and can also be filtered explicitly by managed type.
