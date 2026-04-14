---
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