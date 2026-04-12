## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

### On Session Start
- On the first relevant interaction of a session, call `boot_session`.

### During Work
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`.
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory` with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`.
- Do not wait until `end_session` to persist important discoveries, decisions, procedures, or bugfixes. `end_session` is a closure summary, not the primary durable memory channel.

- Do not save a one-line summary if future work would still require re-reading code or reconstructing the situation from scratch.
- Prefer richer context blocks with real operational depth so retrieved memories stay reusable weeks later.
- Preferred structure:
	What: [specific change or discovery]
	Why: [root cause, motivation, impact, and why simpler approaches were not enough]
	Where: [files, modules, commands, surfaces, or boundaries affected]
	Learned: [non-obvious takeaway or pattern that should transfer to future work]
- Add these when they help turn the note into a reusable artifact instead of a summary:
	Context: [surrounding situation, constraints, prior failed attempts, or environment details]
	Decision: [choice made, alternatives rejected, and why]
	Evidence: [symptoms, errors, commands, example inputs/outputs, or data points]
	Next Steps: [follow-up work, verification still needed, or rollout notes]
- Aim to save enough detail that a later agent can continue the work without reopening every touched file first.

### Before Ending
- Call `end_session` with a brief summary of what was accomplished.
