# OlinKB — MCP Operation in VS Code

## Purpose
This document describes how OlinKB should work inside VS Code so it behaves like Engram: installed locally, registered as an MCP server over `stdio`, and invoked automatically by the agent when the prompt genuinely requires memory.

The core idea is not that OlinKB should be "polling" or running as a permanent daemon, but that it should always be available and that the MCP client should invoke it on demand whenever the conversation needs context, memory retrieval, or persistence of findings.

## Desired Operating Model
OlinKB should operate in three layers:

1. **Availability**
  OlinKB exists as an installable local command, for example `olinkb`.

2. **MCP integration**
   VS Code registers it as an MCP `stdio` server in `mcp.json`.

3. **Automatic use guided by instructions**
   The agent decides to use its tools when the prompt calls for it, following an explicit repository protocol.

## What "Behaving Like Engram" Means
Behaving like Engram means this:

- OlinKB is installed as a local binary or CLI.
- VS Code knows how to start it as an MCP server.
- The client starts it on demand.
- The model invokes its tools when it needs memory.
- The user does not have to type manual commands to use it.

It does not necessarily mean that OlinKB has to live as an always-running background process.

## Registration in VS Code
The expected integration is through an MCP registration similar to this:

```json
{
  "servers": {
    "olinkb": {
      "command": "olinkb",
      "args": ["serve"],
      "type": "stdio",
      "env": {
        "OLINKB_PG_URL": "postgresql://user:password@host:5432/olinkb",
        "OLINKB_TEAM": "my-team",
        "OLINKB_USER": "${env:USER}"
      }
    }
  }
}
```

It could also use a more direct entrypoint:

```json
{
  "servers": {
    "olinkb": {
      "command": "olinkb",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

The final decision between `serve` and `mcp` depends on the CLI design, but the expected behavior is the same: VS Code starts the process and communicates with it over `stdin/stdout`.

## How VS Code Would Invoke It
When the user sends a prompt, the expected flow is this:

```mermaid
sequenceDiagram
    participant User as User
    participant IDE as VS Code + Copilot
    participant MCP as Local OlinKB MCP
    participant PG as PostgreSQL

    User->>IDE: Sends prompt
    IDE->>IDE: The agent evaluates whether it needs memory
    alt memory required
        IDE->>MCP: Calls MCP tool
        MCP->>PG: Reads or writes shared memory
        PG-->>MCP: Result
        MCP-->>IDE: Tool response
    else memory not required
        IDE->>IDE: Responds without using OlinKB
    end
    IDE-->>User: Final response
```

## What "Automatic" Means
In this design, "automatic" means that the agent invokes OlinKB without the user explicitly asking for it whenever the prompt appears to require team memory.

It does not mean:

- running it on every keystroke,
- executing all tools on every prompt,
- intercepting every message with a mandatory external proxy.

It does mean:

- `boot_session` at the beginning of the session,
- `remember` when the prompt needs prior context,
- `save_memory` when something important is discovered,
- `end_session` at the end.

## Recommended Invocation Policy

### 1. Session start
On the first relevant interaction of the session, the agent should call:

```text
boot_session(author, team, project)
```

This is used to:

- validate identity,
- load `team://conventions/*`,
- load relevant `project://*`,
- load useful personal memory,
- warm the read cache.

### 2. Automatic retrieval
When the prompt asks about context, prior decisions, conventions, known bugs, or procedures, the agent should call:

```text
remember(query)
```

Examples where it should trigger:

- "how do we handle auth here?"
- "remind me how we do refresh tokens"
- "why do we use Result instead of exceptions?"
- "had we already solved this bug?"

Examples where it is probably unnecessary:

- "hello"
- "change this color"
- "what time is it"
- trivial questions that only require immediate local context

### 3. Automatic persistence
When a decision, convention, discovery, or bugfix happens during the conversation, the agent should call:

```text
save_memory(...)
```

Using a compatible `memory_type`, for example `decision`, `convention`, `discovery`, `bugfix`, or `procedure`.

Examples:

- the root cause of a bug is discovered,
- a new convention is agreed on,
- an architectural constraint is decided,
- a reusable procedure is documented.

### 4. Closeout
When the session ends or a relevant block of work is completed, the agent should call:

```text
end_session(summary)
```

## Expected MCP Flow by Tool

### `boot_session`
```mermaid
sequenceDiagram
    participant IDE as MCP Client
    participant MCP as OlinKB
    participant PG as PostgreSQL
    participant Cache as Read Cache

    IDE->>MCP: boot_session(author, team, project)
    MCP->>PG: validate identity and load context
    PG-->>MCP: relevant memories
    MCP->>Cache: preload entries
    MCP-->>IDE: session ready
```

### `remember`
```mermaid
sequenceDiagram
    participant IDE as MCP Client
    participant MCP as OlinKB
    participant Cache as Read Cache
    participant PG as PostgreSQL

    IDE->>MCP: remember(query)
    MCP->>Cache: search cache
    alt cache hit
        Cache-->>MCP: results
    else cache miss
        MCP->>PG: search relevant memory
        PG-->>MCP: results
    end
    MCP-->>IDE: retrieved context
```

### `save_memory`
```mermaid
sequenceDiagram
    participant IDE as MCP Client
    participant MCP as OlinKB
    participant Guard as Write Guard
    participant PG as PostgreSQL
    participant Notify as LISTEN/NOTIFY

    IDE->>MCP: save_memory(...)
    MCP->>Guard: validate write
    Guard-->>MCP: allowed or proposed
    MCP->>PG: persist memory
    PG-->>Notify: emit change
    MCP-->>IDE: save successful
```

## What Must Exist for This to Work

### 1. Installable CLI
There must be something executable like:

```bash
olinkb serve
```

or

```bash
olinkb mcp
```

### 2. MCP server over `stdio`
OlinKB must speak MCP over `stdin/stdout`, just like Engram.

### 3. Minimum tools
For the experience to be useful and automatic, OlinKB needs at least:

- `boot_session`
- `remember`
- `save_memory`
- `end_session`

### 4. Repository instructions
The agent needs explicit rules to know when to use OlinKB. Without that, the server may be registered but the model could use it inconsistently.

## Recommended Instruction Block
This is the type of instruction that should live in the repository to enforce the desired behavior:

```md
## OlinKB Memory Protocol

You have access to OlinKB via MCP tools.

### On Session Start
- On the first relevant interaction of a session, call `boot_session`.

### During Work
- Before answering questions about project context, team conventions, past decisions, known bugs, or procedures, call `remember`.
- When you make or discover an important decision, pattern, bugfix, or procedure, call `save_memory` with a compatible `memory_type` such as `decision`, `discovery`, `bugfix`, or `procedure`.
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
```

## What MCP Does Not Solve by Itself
It is important to make clear that MCP does not guarantee hard interception of every prompt. The client exposes tools, and the agent decides whether to call them.

That implies:

- MCP does allow OlinKB to be always available.
- MCP does allow the agent to invoke it automatically.
- MCP alone does not force every prompt to pass through OlinKB.

If absolute guarantees such as "prefetch before every prompt" were ever required, that would be another layer entirely: a proxy, middleware, or an external orchestrator. For the current architecture, the correct recommendation is not to go there initially.

## Final Recommendation
The correct model for OlinKB is this:

1. Install OlinKB as a local CLI.
2. Register it in VS Code as an MCP `stdio` server.
3. Expose a minimal set of well-designed tools.
4. Guide its use with repository instructions.
5. Connect those tools to PostgreSQL as the team's shared memory.

With that, OlinKB behaves exactly like Engram from the user's point of view: it is always available, VS Code calls it when needed, and memory appears integrated into the agent's normal workflow instead of feeling like a separate tool.
