from __future__ import annotations

import json


def render_mcp_template(
    *,
    pg_url: str,
    team: str,
    user_env: str = "${env:USER}",
    project: str | None = None,
) -> str:
    env = {
        "OLINKB_PG_URL": pg_url,
        "OLINKB_TEAM": team,
        "OLINKB_USER": user_env,
    }
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

    transport_intro = "You have access to OlinKB via MCP tools."
    session_start_line = "- On the first relevant interaction of a session, call `boot_session`."
    remember_line = "- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`."
    save_line = "- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory` with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`."
    approval_line = "- Project leads and admins should use `list_pending_approvals(...)` or the `review_queue` returned by `boot_session` to batch-review proposed conventions, then call `review_memory_proposal(...)` to approve or reject them."
    ending_line = "- Call `end_session` with a brief summary of what was accomplished."

    if mode == "cli":
        transport_intro = "You have access to OlinKB via the local OlinKB CLI transport."
        session_start_line = "- On the first relevant interaction of a session, run the corresponding `olinkb tool ...` command, for example `olinkb tool boot_session --json '{\"project\":\"example\"}'`."
        remember_line = "- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, run `olinkb tool remember --json '{\"query\":\"...\"}'` and inspect the JSON result."
        save_line = "- When you make or discover an important decision, pattern, bugfix, or procedure, run the matching `olinkb tool save_memory --json ...` command with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`."
        approval_line = "- Project leads and admins should run `olinkb tool list_pending_approvals --json ...` and `olinkb tool review_memory_proposal --json ...` to process proposals."
        ending_line = "- Close the session with `olinkb tool end_session --json ...` and capture a brief summary of what was accomplished."

    return f"""## OlinKB Memory Protocol

{transport_intro}

Use this as the default memory workflow across repositories unless the active repository provides more specific memory instructions.

### On Session Start
{session_start_line}
- Treat the first project-related request in a session as relevant even if the user did not explicitly ask about memory.
- If `boot_session` returns a non-empty `review_queue`, project leads and admins should review those proposals during the session instead of polling manually.

### During Work
{remember_line}
- If the user asks about a project, feature, workflow, prior decision, or "what did we do before", call `remember` before relying on guesswork.
- Prefer `remember(..., include_content=false)` for lean recall; request full `content` only when the body is actually needed.
{save_line}
- A memory only enters convention review when the developer explicitly calls `propose_memory_promotion(...)`. Saving a normal project memory never queues it automatically.
- Do not save `convention` directly unless you are acting as a project lead or admin. Contributors should save the underlying project memory first and then use `propose_memory_promotion(...)` when they believe it should become a standard or convention.
{approval_line}
- Save important discoveries as soon as you make them; do not defer them until after unrelated edits, tests, or long explanations.
- Do not wait until `end_session` to persist important discoveries, decisions, procedures, or bugfixes. `end_session` is a closure summary, not the primary durable memory channel.
- Do not save a one-line summary if future work would still require re-reading code or reconstructing the situation from scratch.
- Prefer richer context blocks with real operational depth so retrieved memories stay reusable weeks later.
- If a specialized repository skill exists for planning, brainstorming, or verification, use it in addition to this protocol rather than replacing the memory workflow.
- Effective memory format:
    What: [2-3 sentences with the concrete action, behavior change, or discovery, including specific examples when useful]
    Why: [root cause, motivation, impact, and why simpler or naive approaches were not enough]
    Where: [relevant file paths, modules, commands, surfaces, or boundaries where the change lives]
    Learned: [non-obvious pattern, gotcha, or rule that should transfer to similar future work]
- Add these when they help turn the note into a reusable artifact instead of a summary:
    Context: [surrounding constraints, prior failed attempts, deadlines, environment details, or product pressure]
    Decision: [what was chosen over which alternatives, and why]
    Evidence: [error messages, observed symptoms, example inputs/outputs, reproduced commands, or data points]
    Next Steps: [unfinished work, verification still needed, rollout notes, or adjacent follow-up]
- Aim to save enough detail that a later agent can continue the work without reopening every touched file first.

### Before Ending
{ending_line}
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

## Output Contract

Return one of these:

- `SAVE` — include suggested `memory_type`, a short title, and a `What / Why / Where / Learned` skeleton.
- `SKIP` — explain in one sentence why the information is session-local, obvious, or not yet durable.

## Common Mistakes

- Saving every completed task
- Saving plans that were never adopted
- Saving diffs without the reason they mattered
- Saving speculative brainstorming as if it were a decision
- Saving tool output when the durable part is the conclusion, not the raw log
"""