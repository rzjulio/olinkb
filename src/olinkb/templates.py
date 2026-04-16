from __future__ import annotations

import json


def render_mcp_template(
    *,
    team: str,
    storage_backend: str = "postgres",
    pg_url: str | None = None,
    sqlite_path: str | None = None,
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> str:
    env = {
        "OLINKB_STORAGE_BACKEND": storage_backend,
        "OLINKB_TEAM": team,
        "OLINKB_USER": user_env,
    }
    if storage_backend == "postgres":
        if not pg_url:
            raise ValueError("PostgreSQL MCP template requires pg_url")
        env["OLINKB_PG_URL"] = pg_url
    elif storage_backend == "sqlite":
        if not sqlite_path:
            raise ValueError("SQLite MCP template requires sqlite_path")
        env["OLINKB_SQLITE_PATH"] = sqlite_path
    else:
        raise ValueError(f"Unsupported storage backend: {storage_backend}")
    if project:
        env["OLINKB_PROJECT"] = project

    document = {
        "servers": {
            "olinkb": {
                "command": "olinkb",
                "args": ["mcp"],
                "type": "stdio",
                "env": env,
            }
        }
    }
    return json.dumps(document, indent=2)


def render_instructions_template(*, mode: str = "mcp") -> str:
    if mode not in {"mcp", "cli"}:
        raise ValueError(f"Unsupported instructions mode: {mode}")

    memory_type_guide = """### Memory Type Selection
- `decision` — a choice was made between alternatives with reasoning
- `discovery` — a non-obvious finding, behavior, or insight was uncovered
- `bugfix` — a bug was diagnosed and fixed, including root cause and evidence
- `procedure` — a reusable step-by-step workflow or command sequence was verified
- `convention` — a team-agreed standard or rule (requires lead/admin, or use `propose_memory_promotion`)
- `constraint` — a hard boundary, limitation, or invariant that must be respected
- `failure_pattern` — a recurring failure mode with its symptoms and workaround
- `tool_affordance` — a tool capability, shortcut, or integration pattern worth remembering
- `fact` — a verified factual statement about the codebase, environment, or domain
- `event` — a notable occurrence such as a deployment, outage, or milestone
- `preference` — a personal or team stylistic preference
- `documentation` — technical documentation for the project or team
- `business_documentation` — business-level documentation (admin only)
- `development_standard` — engineering standards and practices"""

    scope_guide = """### Scope Selection
- `personal` — private to the author (personal notes, preferences, scratch findings)
- `project` — shared within a specific project (most common for decisions, bugs, procedures)
- `team` — shared across the team regardless of project (conventions, standards)
- `org` — organization-wide (requires lead/admin)
- `system` — global system-level (requires lead/admin)
When in doubt, use `project`. OlinKB can infer scope from the URI or project context when omitted."""

    doc_approval_guide = """### Documentation Approval Workflow
All `documentation`, `business_documentation`, and `development_standard` memories are created with status **[PENDIENTE DE APROBACIÓN]** regardless of the author's role.
- Developers: you can create and edit documentation freely, but it will remain pending until a lead/admin reviews and approves it via `review_memory_proposal`.
- Leads/admins: your documentation is also saved as pending. The response will include `awaiting_approval: true` and an `approval_hint`. **You MUST ask the user if they want to approve the documentation now.** If they confirm, call `review_memory_proposal` with the returned `uri` and `action='approve'`.
- When searching with `remember`, each result includes an `approval_label` field: `[APROBADA]`, `[PENDIENTE DE APROBACIÓN]`, or `[RECHAZADA]`. Always communicate this status to the user.
- Pending documentation does NOT appear in `boot_session` preloaded memories. Only approved documentation is loaded at boot.
- If a pending documentation is edited, the approval resets — a lead/admin must re-approve the updated version.
- Non-documentation types (`decision`, `bugfix`, `procedure`, etc.) are NOT subject to approval and are saved as approved immediately."""

    effective_format = """- Effective memory format:
    What: [2-3 sentences with the concrete action, behavior change, or discovery, including specific examples when useful]
    Why: [root cause, motivation, impact, and why simpler or naive approaches were not enough]
    Where: [relevant file paths, modules, commands, surfaces, or boundaries where the change lives]
    Learned: [non-obvious pattern, gotcha, or rule that should transfer to similar future work]
- Add these when they help turn the note into a reusable artifact instead of a summary:
    Context: [surrounding constraints, prior failed attempts, deadlines, environment details, or product pressure]
    Decision: [what was chosen over which alternatives, and why]
    Evidence: [error messages, observed symptoms, example inputs/outputs, reproduced commands, or data points]
    Next Steps: [unfinished work, verification still needed, rollout notes, or adjacent follow-up]
- Aim to save enough detail that a later agent can continue the work without reopening every touched file first."""

    if mode == "cli":
        return f"""## OlinKB Memory Protocol

You have access to OlinKB via the local OlinKB CLI transport.

Use this as the default memory workflow across repositories unless the active repository provides more specific memory instructions.

### Mandatory CLI Gate
- OlinKB CLI usage is required for project memory workflows. Do not treat it as optional guidance.
- Do not use internal chat memory, `/memories/`, or session summaries as a substitute for OlinKB when this protocol applies.
- Do not answer project-memory questions from guesswork when `olinkb tool remember --json ...` should be used first.
- Do not claim a memory was persisted unless the corresponding `olinkb tool ...` command completed successfully.
- On Windows PowerShell, do not use bash-style escaping like `\\"...\\"` inside `--json` payloads. Prefer `$payload = @{{...}} | ConvertTo-Json -Compress; olinkb tool ... --json $payload` or `--input-file` for multiline/long payloads.
- If a required OlinKB CLI command fails, stop the normal workflow, state that persistence or recall is blocked, and ask the user whether to continue without OlinKB for that step.
- If a durable discovery, decision, bugfix, or procedure is identified, persist it immediately with `olinkb tool capture_memory --json ...` or `olinkb tool save_memory --json ...`; do not defer persistence until the end of the session.
- Failure policy:
    1. If `boot_session` fails, do not start project analysis, planning, or implementation until the user explicitly approves continuing without OlinKB.
    2. If `remember` fails for a question that depends on prior project context, do not answer from assumed memory; ask whether to continue with a best-effort answer.
    3. If `capture_memory` or `save_memory` fails for a durable result, stop and tell the user that the result is not yet persisted.
    4. If `end_session` fails, report that session closure was not recorded.

### Available Tools
All tools are invoked as `olinkb tool <tool_name> --json '{{...}}'`. The 10 available tools are:
- `boot_session` — start a session and preload relevant memories
- `analyze_memory` — dry-run analysis of content for memory classification
- `capture_memory` — analyze and auto-save high-confidence results
- `remember` — search stored memories by query
- `save_memory` — create or update a memory entry
- `propose_memory_promotion` — propose a project memory for convention review
- `list_pending_approvals` — list pending convention proposals (lead/admin)
- `review_memory_proposal` — approve or reject a proposal (lead/admin)
- `end_session` — close session with summary
- `forget` — soft-delete a memory with audit trail

### On Session Start
- On the first relevant interaction of a session, run the corresponding `olinkb tool ...` command, for example `olinkb tool boot_session --json '{{"project":"example"}}'`.
- Treat the first project-related request in a session as relevant even if the user did not explicitly ask about memory.
- If `boot_session` returns a non-empty `review_queue`, project leads and admins should review those proposals during the session instead of polling manually.
- Do not begin project analysis, planning, or implementation before running `boot_session` for the active project; if it cannot be run successfully, ask the user whether to proceed without OlinKB.

### During Work
- Before deciding whether something should become memory, run `olinkb tool analyze_memory --json ...` for a dry run or `olinkb tool capture_memory --json ...` to let OlinKB auto-save high-confidence results.
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, run `olinkb tool remember --json '{{"query":"..."}}'` and inspect the JSON result.
- If the user asks about a project, feature, workflow, prior decision, or "what did we do before", run `olinkb tool remember --json ...` before relying on guesswork.
- Prefer `olinkb tool remember --json '{{"query":"...","include_content":false}}'` for lean recall; request full `content` only when the body is actually needed.
- When you make or discover an important decision, pattern, bugfix, or procedure, run the matching `olinkb tool save_memory --json ...` command with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`.
- Treat these as mandatory checkpoints, not best-effort suggestions:
    1. `olinkb tool remember --json ...` before answering project-history or convention questions.
    2. `olinkb tool analyze_memory --json ...` or `olinkb tool capture_memory --json ...` before deciding not to persist a potentially durable result.
    3. `olinkb tool save_memory --json ...` immediately when a durable result is clear and auto-capture is insufficient or skipped.
- A memory only enters convention review when the developer explicitly runs `olinkb tool propose_memory_promotion --json ...`. Saving a normal project memory never queues it automatically.
- Do not save `convention` directly unless you are acting as a project lead or admin. Contributors should save the underlying project memory first and then use `olinkb tool propose_memory_promotion --json ...` when they believe it should become a standard or convention.
- Project leads and admins should run `olinkb tool list_pending_approvals --json ...` and `olinkb tool review_memory_proposal --json ...` to process proposals.
- To soft-delete a memory that is outdated, wrong, or superseded, run `olinkb tool forget --json '{{"uri":"...","reason":"..."}}'`.
- Save important discoveries as soon as you make them; do not defer them until after unrelated edits, tests, or long explanations.
- Do not wait until `end_session` to persist important discoveries, decisions, procedures, or bugfixes. `end_session` is a closure summary, not the primary durable memory channel.
- Do not save a one-line summary if future work would still require re-reading code or reconstructing the situation from scratch.
- Prefer richer context blocks with real operational depth so retrieved memories stay reusable weeks later.
- If a specialized repository skill exists for planning, brainstorming, or verification, use it in addition to this protocol rather than replacing the memory workflow.
{effective_format}

{memory_type_guide}

{scope_guide}

{doc_approval_guide}

### Before Ending
- Close the session with `olinkb tool end_session --json ...` and capture a brief summary of what was accomplished.
- `end_session` is mandatory session closure, but it never replaces earlier `capture_memory` or `save_memory` calls.

### PowerShell Notes
- Prefer one-line payload variables built with `ConvertTo-Json -Compress` when using `--json` in PowerShell.
- Prefer `--input-file` for multiline payloads, rich Markdown, or long `content` blocks.
- `save_memory` can infer `project`, `scope`, `title`, and canonical memory `uri` when you omit them.
- `end_session` can resolve `session_id` automatically when exactly one matching open session exists for the current author/project context.
"""

    return f"""## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

Use this as the default memory workflow across repositories unless the active repository provides more specific memory instructions.

### Mandatory Gate
- OlinKB tool usage is required for project memory workflows. Do not treat it as optional guidance.
- Do not use internal chat memory, `/memories/`, or session summaries as a substitute for OlinKB when this protocol applies.
- Do not answer project-memory questions from guesswork when `remember(...)` should be called first.
- Do not claim a memory was persisted unless the corresponding tool call completed successfully.
- Failure policy:
    1. If `boot_session` fails, do not start project analysis, planning, or implementation until the user explicitly approves continuing without OlinKB.
    2. If `remember` fails for a question that depends on prior project context, do not answer from assumed memory; ask whether to continue with a best-effort answer.
    3. If `capture_memory` or `save_memory` fails for a durable result, stop and tell the user that the result is not yet persisted.
    4. If `end_session` fails, report that session closure was not recorded.

### On Session Start
- On the first relevant interaction of a session, call `boot_session`.
- Treat the first project-related request in a session as relevant even if the user did not explicitly ask about memory.
- If `boot_session` returns a non-empty `review_queue`, project leads and admins should review those proposals during the session instead of polling manually.
- Do not begin project analysis, planning, or implementation before calling `boot_session`; if it fails, ask the user whether to proceed without OlinKB.

### During Work
- Before deciding whether something should become memory, call `analyze_memory(...)` for a dry run or `capture_memory(...)` to let OlinKB auto-save high-confidence results.
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`.
- If the user asks about a project, feature, workflow, prior decision, or "what did we do before", call `remember` before relying on guesswork.
- Prefer `remember(..., include_content=false)` for lean recall; request full `content` only when the body is actually needed.
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory` with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`.
- Treat these as mandatory checkpoints, not best-effort suggestions:
    1. `remember(...)` before answering project-history or convention questions.
    2. `analyze_memory(...)` or `capture_memory(...)` before deciding not to persist a potentially durable result.
    3. `save_memory(...)` immediately when a durable result is clear and auto-capture is insufficient or skipped.
- A memory only enters convention review when the developer explicitly calls `propose_memory_promotion(...)`. Saving a normal project memory never queues it automatically.
- Do not save `convention` directly unless you are acting as a project lead or admin. Contributors should save the underlying project memory first and then use `propose_memory_promotion(...)` when they believe it should become a standard or convention.
- Project leads and admins should use `list_pending_approvals(...)` or the `review_queue` returned by `boot_session` to batch-review proposed conventions, then call `review_memory_proposal(...)` to approve or reject them.
- To soft-delete a memory that is outdated, wrong, or superseded, call `forget(uri=..., reason=...)`.
- Save important discoveries as soon as you make them; do not defer them until after unrelated edits, tests, or long explanations.
- Do not wait until `end_session` to persist important discoveries, decisions, procedures, or bugfixes. `end_session` is a closure summary, not the primary durable memory channel.
- Do not save a one-line summary if future work would still require re-reading code or reconstructing the situation from scratch.
- Prefer richer context blocks with real operational depth so retrieved memories stay reusable weeks later.
- If a specialized repository skill exists for planning, brainstorming, or verification, use it in addition to this protocol rather than replacing the memory workflow.
{effective_format}

{memory_type_guide}

{scope_guide}

{doc_approval_guide}

### Before Ending
- Call `end_session` with a brief summary of what was accomplished.
- `end_session` is mandatory session closure, but it never replaces earlier `capture_memory` or `save_memory` calls.
"""


def render_cli_mandatory_prompt_template() -> str:
    return """---
mode: agent
description: Start a session with mandatory OlinKB CLI memory workflow.
---

Use OlinKB CLI as a mandatory workflow, not optional guidance.

These are blocking checkpoints. Use the exact `olinkb tool ...` workflow instead of relying on internal chat memory, `/memories/`, or assumptions.

Before any project analysis, planning, implementation, or project-context answer:
1. Run `olinkb tool boot_session --json ...`

Before answering anything about prior work, conventions, decisions, bugs, procedures, or project history:
2. Run `olinkb tool remember --json ...`

When a durable decision, discovery, bugfix, or procedure appears:
3. Run `olinkb tool analyze_memory --json ...` or `olinkb tool capture_memory --json ...`
4. If the result is clearly durable and was not persisted automatically, run `olinkb tool save_memory --json ...`

To promote a project memory to a team convention:
5. Run `olinkb tool propose_memory_promotion --json ...`

To soft-delete an outdated or wrong memory:
6. Run `olinkb tool forget --json '{"uri":"...","reason":"..."}'`

Before ending the session:
7. Run `olinkb tool end_session --json ...`

Rules:
- Do not substitute internal chat memory, `/memories/`, or a session summary for OlinKB.
- Do not claim anything was remembered or saved unless the CLI command succeeded.
- On Windows PowerShell, do not emit bash-style escaped JSON like `'{\"query\":\"x\"}'`. Prefer `$payload = @{ ... } | ConvertTo-Json -Compress` or `--input-file`.
- If any required OlinKB command fails, stop that workflow step, explain the failure, and ask whether to continue without OlinKB.
- If `boot_session` fails, do not start project analysis, planning, or implementation unless the user explicitly approves continuing without OlinKB.
- If `remember` fails for a question that depends on prior project context, do not answer from assumed memory; ask whether to continue with a best-effort answer.
- If `capture_memory` or `save_memory` fails for a durable result, tell the user the result is not yet persisted.
- If `end_session` fails, report that the session closure was not recorded.
- Do not defer durable memory saves until the end of the session.

Quick reference for `memory_type`: decision, discovery, bugfix, procedure, convention, constraint, failure_pattern, tool_affordance, fact, event, preference, documentation, business_documentation, development_standard.
Quick reference for `scope`: personal, project (default), team.
Note: documentation, business_documentation, and development_standard are ALWAYS saved as pending. Leads/admins will receive an `awaiting_approval` flag — ask them to confirm before calling `review_memory_proposal` to approve. Search results include `approval_label` to indicate status.
"""


def render_memory_relevance_skill_template() -> str:
    return """---
name: memory-relevance-triage
description: Use when deciding whether a result, finding, fix, review outcome, or brainstorming conclusion is important enough to persist as an OlinKB memory, especially after another skill or workflow produced structured output.
---

# Memory Relevance Triage

## Overview

Use this skill to decide whether something deserves durable memory or should remain session-local.

The standard is simple: save only information that will change future behavior or would be expensive to rediscover.

## When to Use

- After another skill returns findings, options, or a recommendation
- After debugging, code review, verification, install/setup work, or design exploration
- When you are unsure whether to call `save_memory`

Do not use this for routine progress updates, obvious facts visible in the current diff, or speculative ideas that were never chosen.

## Decision Rule

Save the result only if both conditions are true:

1. Durability: a future agent or teammate would likely need this later without re-reading the same files, rerunning the same commands, or reconstructing the same reasoning.
2. Signal: at least one of these is true:
   - a non-obvious root cause was found
   - a decision was made between alternatives
   - a reusable procedure or verified command flow was established
   - a constraint, gotcha, or boundary was discovered
   - a convention or precedence rule was clarified
   - an accepted review finding changed implementation, docs, or operating guidance

If either condition fails, do not save it.

## Result-Aware Triage

- Brainstorming: save the chosen direction, rejected options with reasons, or constraints that shape future work. Do not save raw idea lists.
- Reviews: save implemented findings or durable residual risks. Do not save unaccepted comments.
- Debugging: save root cause, evidence, and fix. Do not save the symptom alone.
- Verification: save only when it changes confidence, rollout steps, or known limitations.
- Setup and install work: save verified paths, precedence rules, environment gotchas, or uninstall procedures.

If another skill already produced a result, triage that result directly instead of re-summarizing the whole conversation.

## How to Persist

Use the OlinKB tools available in your current transport (MCP tools or CLI):
- MCP: call `save_memory(memory_type=..., title=..., content=..., scope=..., ...)` or `capture_memory(...)` for auto-classification.
- CLI: run `olinkb tool save_memory --json '{"memory_type":"...","title":"...","content":"..."}'` or use `capture_memory`.
- To delete outdated or wrong memories, use `forget(uri=..., reason=...)`.
- Follow the OlinKB Memory Protocol instructions for the full workflow including `boot_session` and `end_session`.

## Memory Type Selection

Pick the most specific type that fits:
- `decision` — a choice between alternatives with reasoning
- `discovery` — a non-obvious finding or insight
- `bugfix` — root cause, evidence, and fix for a bug
- `procedure` — a verified step-by-step workflow
- `convention` — a team standard (requires lead/admin or `propose_memory_promotion`)
- `constraint` — a hard limitation or invariant
- `failure_pattern` — a recurring failure with symptoms and workaround
- `tool_affordance` — a tool capability or integration pattern
- `fact` — a verified factual statement
- `event` — a notable occurrence (deployment, outage, milestone)
- `preference` — a personal or team stylistic preference
- `documentation` — technical documentation (pending approval if created by developer)
- `business_documentation` — business-level documentation (pending approval if created by developer)
- `development_standard` — engineering standards (pending approval if created by developer)

## Scope Selection

- `personal` — private to the author
- `project` — shared within a project (default; most common)
- `team` — shared across projects within the team

## Output Contract

Return one of these:

- `SAVE` — include suggested `memory_type`, `scope`, a short title, and a `What / Why / Where / Learned` skeleton.
- `SKIP` — explain in one sentence why the information is session-local, obvious, or not yet durable.

## Common Mistakes

- Saving every completed task
- Saving plans that were never adopted
- Saving diffs without the reason they mattered
- Saving speculative brainstorming as if it were a decision
- Saving tool output when the durable part is the conclusion, not the raw log
"""