# Objective Audit of OlinKB

Date: April 12, 2026

## Executive Summary

Short and honest verdict:

- Is it helpful: yes, but today it helps as an operational foundation for shared memory in small teams, not as a mature system for curated context.
- Does it work as it should: partially. The CRUD core and MCP flow are coherent, but there are important gaps in scoping, security, verification, and operational integrity.
- Does it save tokens: yes, at the payload level. The savings exist and are implemented, but they are approximate, conditional, and do not automatically mean better context.
- Does it always deliver clean, curated context: no. It delivers lighter and more structured context, but it does not guarantee cleanliness, relevance, or project/team isolation.
- Would it serve 10 developers working in parallel: with caveats, and only after important adjustments, maybe. In the current state, there are real risks of context mixing and contention.
- Would it scale to hundreds of developers in an enterprise: no. It still lacks real multi-tenant isolation, authorization, distributed invalidation, observability, and a more sophisticated retrieval layer.

The most important conclusion is this: OlinKB is already a good technical base to evolve, but it is not yet a reliable curated shared-memory system for multi-project, multi-team, or large-enterprise use.

## Direct Answers to the Questions

### 1. Does it really help

Yes, in these scenarios:

- Small teams that want to remember decisions, bugs, procedures, and session closures inside the MCP flow.
- Repositories where there is already discipline around writing structured memories.
- Environments where shared PostgreSQL is already available and local installation cost is not a problem.

It helps less in these scenarios:

- When the team expects the tool to understand semantics, causal relationships, or query intent.
- When multiple projects and teams share the same database and strong isolation is required.
- When the team expects context to arrive curated automatically without disciplined capture.

### 2. Does it really work as it should

The objective answer is: not completely yet.

What is on solid footing:

- A simple and clear MCP server over `stdio`.
- PostgreSQL persistence.
- Saving with `audit_log`, `soft delete`, `content_hash`, and `metadata` JSONB.
- A `boot_session`, `remember`, `save_memory`, `end_session`, and `forget` flow that is well separated across app, storage, and server.
- Live viewer and snapshot viewer as useful inspection tools.

What prevents saying "it works as it should" without reservations:

- The suite is not fully green today: `pytest -q` returns `62 passed, 1 failed`.
- The README claims the current suite is passing, but that does not match the real state.
- `remember` filtering is not isolated by current project, team, or author; it only filters by `scope`.

### 3. Does it save tokens

Yes, but precisely:

- `remember(..., include_content=false)` omits the full body and returns metadata plus a preview.
- `boot_session` uses a hybrid mode with `BOOT_FULL_CONTENT_LIMIT = 5`.
- There is a `benchmark` command and a `benchmark_payloads()` path to measure bytes and approximate tokens.

What limits that claim:

- Token calculation is only an approximation of `chars / 4`, not a real tokenizer.
- The savings are payload savings, not evidence of net agent-token savings in real workflows.
- If the agent asks for `include_content=true`, the benefit drops quickly.
- Saving payload does not, by itself, solve context quality.

### 4. Does it always deliver clean and curated context

No.

It delivers cleaner context than raw memory, but not always clean and much less always curated.

Reasons:

- Search is trigram plus `ILIKE`; there is no semantic retrieval, clustering, intent detection, or enrichment.
- Deduplication is exact by SHA256; equivalent memories with different wording survive as conceptual duplicates.
- There is no automatic consolidation of related memories.
- The main search does not filter by real tenant boundaries; this can contaminate recall.

### 5. Would it serve a team of 10 developers in parallel

I would not rule it out, but I would not recommend it yet without prior changes.

The two most serious practical problems for that case are:

- A fixed `max_size=5` in the connection pool.
- `remember` and the viewer are not isolated by real project or team inside the query.

If the deployment were a single team, few projects, a controlled shared database, and those points were fixed, then yes, it could be useful for 10 people.

### 6. Would it scale to hundreds of developers in an enterprise

Not in the current state.

The chosen base, PostgreSQL, can scale. What does not scale yet is the architecture for isolation, security, cache coherence, and retrieval.

## Real Strengths of the Project

### 1. Reasonable and small technical base

The project is understandable. The separation between `app.py`, `server.py`, `storage/postgres.py`, `session.py`, `templates.py`, and `bootstrap.py` is pragmatic and maintainable.

That matters because improving a small, coherent system is much more viable than rescuing a disordered monolith.

### 2. PostgreSQL was the right decision

Switching from SQLite to PostgreSQL was the right decision for shared memory.

Current benefits:

- real concurrent reads and writes
- `pg_trgm` for useful basic search
- `JSONB` for structured metadata
- `audit_log` and standard extensions

### 3. The MCP surface is minimal and clear

The tools are few and understandable:

- `boot_session`
- `remember`
- `save_memory`
- `end_session`
- `forget`

That reduces cognitive complexity and makes adoption easier.

### 4. There is a serious attempt to save context

The project does not just say it saves tokens; there is concrete implementation:

- hybrid boot
- `include_content=false`
- `preview`
- benchmark CLI

That puts it above many memory systems that only promise savings without instrumentation.

### 5. There is traceability and structure

Using `audit_log`, `soft delete`, `metadata` JSONB, and `content_hash` provides a useful base for future governance.

### 6. The documentation is more honest than average

`README.md` already clarifies several things that do not exist yet: RLS, semantic retrieval, LISTEN/NOTIFY, and a forgetting engine. That is good. The problem is that some claims still do not match the real current state.

## Weaknesses and Serious Risks

### 1. Critical risk: `remember` is not isolated by project, team, or user

Evidence:

- `src/olinkb/app.py` computes `project_name` in `remember()`.
- But `src/olinkb/storage/postgres.py` in `search_memories()` does not receive or use `project`, `team`, or `author_username`.
- The query only filters with `scope = ANY(...)`.

Impact:

- `scope="project"` can return memories from any project stored in the same database.
- `scope="team"` can return memories from any team.
- `scope="personal"` can potentially expose personal memories from other users if they share the same database.
- `scope="all"`, which is the default, amplifies the problem.

Conclusion:

Today this is the main blocker to claiming that OlinKB delivers clean context or secure multi-tenant behavior.

### 2. Critical risk: there is no real authorization, only role data

Evidence:

- `team_members.role` exists in `001_init.sql`.
- `create_or_update_member()` stores `role`.
- There are no role checks before `save_memory`, `forget_memory`, `search_memories`, or `search_viewer_memories`.

Impact:

- The concept of role is currently decorative.
- There is no enforcement for sensitive namespaces such as team conventions.
- There is no permission isolation by namespace.

Conclusion:

It is not correct to market it as enterprise-ready while roles have no real effect.

### 3. Fixed and undersized connection pool

Evidence:

- `src/olinkb/storage/postgres.py` creates the pool with `min_size=1, max_size=5`.

Impact:

- For several concurrent agents, 5 connections is a low limit.
- In a team of 10 developers with overlapping operations, it can create avoidable contention and latency.

Conclusion:

It should be configurable by environment and measured under real load.

### 4. Active sessions live only in process memory

Evidence:

- `src/olinkb/session.py` uses an in-memory dictionary.
- `OlinKBApp` uses it for `memories_read` and `memories_written` during the session.

Impact:

- If the process dies, active session state is lost.
- There is no coordination between processes.
- It does not serve operational analytics or distributed observability.

Note:

The project has a partial recovery path when closing a session, but it does not solve multi-process coordination.

### 5. Local cache without distributed invalidation

Evidence:

- `src/olinkb/storage/cache.py` implements a local in-memory cache with TTL.
- `src/olinkb/config.py` defaults `OLINKB_CACHE_TTL_SECONDS=300`.
- There is no `LISTEN/NOTIFY` or cross-process invalidation.

Impact:

- One process can keep reading stale data for several minutes.
- In concurrent teams, freshness of context cannot be guaranteed.

Conclusion:

This does not invalidate the product for small teams, but it is insufficient for strong coordination across many agents.

### 6. Retrieval is still basic

Evidence:

- `search_memories()` uses `similarity(...)` and `ILIKE`.
- There are no embeddings, `pgvector`, query intent, semantic reranking, or relationship expansion.

Impact:

- The system remembers similar text, not necessarily relevant knowledge.
- There is no automatic curation of context.

Conclusion:

Today it is searchable memory, not intelligent memory.

### 7. Captured structure and extracted structure do not fully match

Evidence:

- `src/olinkb/templates.py` instructs agents to save blocks like `What`, `Why`, `Where`, `Learned`, `Context`, `Decision`, `Evidence`, and `Next Steps`.
- `src/olinkb/storage/postgres.py` extracts metadata with `STRUCTURED_METADATA_PATTERN`.
- That pattern does not include `Evidence`.

Impact:

- Part of the context recommended by the instructions is not stored as structured data.
- Previews and metadata do not represent everything that the protocol itself asks to save.

Additionally:

- Extraction depends on English headings.
- In bilingual or Spanish-speaking teams, the real structure can degrade.

### 8. Automated verification gives partial confidence, not strong confidence

Evidence:

- The current suite run locally returned `62 passed, 1 failed`.
- The failure is in `tests/test_viewer.py` and checks that the viewer HTML contains `All notes`, text that does not currently appear.
- Many storage and app tests use fakes and stubs (`FakeStorage`, `SavePool`, `QueryPool`, `BootQueryPool`, `BenchmarkQueryPool`, and so on).

Impact:

- There is good unit coverage of contracts.
- There is little evidence of real behavior against live PostgreSQL and full flows.

Conclusion:

The project is better tested than an improvised prototype, but not enough to support large-team robustness claims.

### 9. The README has an outdated claim

Evidence:

- `README.md` says: "The current test suite is passing".
- The real execution in this analysis does not match.

Impact:

- It reduces operational credibility.
- Even if it is a small detail, it is exactly the kind of detail that makes other claims harder to trust.

### 10. Boot is more curated than remember

Evidence:

- `load_boot_memories()` does limit by `system://`, `team://conventions/`, current project, and `personal://user/...`.
- `remember()` does not apply equivalent filtering to memories.

Impact:

- Startup is relatively prudent.
- Ad hoc recall is much riskier in terms of context cleanliness.

## What Can Be Improved Right Now

### High Priority

1. Fix `remember` scoping.

- Filter by current project for `project://...` memories.
- Filter by current team for `team://...` memories.
- Filter by current user for `personal://...` memories.
- Make `scope="all"` mean "all within my tenant/session context", not "all rows of that scope in the database".

2. Fix live viewer scoping.

- `search_viewer_memories()` should not expose a cross-cutting dataset by default if the database is shared across teams or projects.

3. Implement real authorization.

- First at the application level.
- Ideally afterward at the database level with RLS.

4. Make the PostgreSQL pool configurable.

- For example `OLINKB_PG_POOL_MIN_SIZE` and `OLINKB_PG_POOL_MAX_SIZE`.

5. Repair the suite state.

- Either fix the viewer test.
- Or fix the viewer HTML.
- But it should not remain red while the README says otherwise.

6. Add real integration tests.

- Live PostgreSQL brought up in CI.
- `boot -> remember -> save -> end -> forget` flows.
- Multi-tenant and multi-project cases.

### Medium Priority

1. Align instructions and metadata extraction.

- Add `Evidence` to extraction.
- Decide whether `Remaining`, `Risks`, or `Open Questions` should also be structured.
- Support Spanish headings if the product will be used in Spanish-speaking teams.

2. Improve token benchmark validity.

- Keep the current benchmark for simplicity.
- But clarify in CLI/docs that it is approximate.
- Add a future option with a real tokenizer from the main provider.

3. Distributed cache invalidation.

- `LISTEN/NOTIFY` is the natural next step.

4. Smarter retrieval.

- embeddings or `pgvector`
- semantic deduplication
- query intent
- reranking by memory type, recency, and authority

5. Persist more operational signals.

- metrics per query
- latencies
- cache hit ratio
- most accessed memories

### Low Priority

1. Improve viewer naming and claims.

- Separate the inspection viewer more clearly from the core product narrative.

2. Internationalize templates and interface.

3. Refine boot scoring with real data instead of only heuristics.

## What Should Be Removed or Softened

### 1. Remove the idea that roles already protect the system

Today roles exist in the data, not in enforcement.

### 2. Soften any claim of "curated context"

A more accurate description today would be:

- lighter context
- structured context when the memory is well written
- searchable shared memory

But not "always clean" or "curated".

### 3. Remove the README line claiming the suite is passing until that becomes true again

### 4. Remove the assumption that `scope` equals tenancy

`scope` only expresses category. It is not isolation.

## What Should Be Kept

- PostgreSQL as the main base.
- The small MCP API.
- `metadata` JSONB.
- `audit_log`.
- soft delete.
- benchmark CLI.
- hybrid boot with lean payload.
- VS Code bootstrap.

All of that makes sense and should not be thrown away.

## Evaluation by Scale

### 1 to 3 developers

Yes. It is a reasonable use today, especially if they work on one or a few projects and there is discipline around saving good memories.

### 4 to 10 developers

Possible, but I would not let it enter shared production in this state without first fixing:

- `remember` scoping
- configurable pool sizing
- integration tests
- cache invalidation, at least partially

### 10 to 50 developers

Not yet. That is where tenancy, permissions, observability, and context freshness issues become visible.

### 100+ developers

No. Too many structural pieces are still missing to say it is enterprise-ready.

## Final Judgment

OlinKB is not smoke and mirrors. It has real value and a useful technical base. It is not an empty product.

But it is also not correct to present it today as a mature curated shared-memory solution for large teams.

The best objective way to describe it would be this:

> OlinKB is a promising foundation for shared agent memory, with good technical direction and real payload improvements, but it still does not guarantee the isolation, semantic curation, or operational scalability needed for large teams or enterprise use.

## Practical Recommendation

If the goal is to improve the tool in the most effective order, I would do this:

1. Fix multi-tenant scoping in `remember` and the viewer.
2. Implement real authorization by namespace and role.
3. Repair the red suite and add integration with live PostgreSQL.
4. Make the pool configurable and measure load.
5. Add distributed cache invalidation.
6. Only then invest in semantic retrieval and intelligent deduplication.

Ese orden ataca primero verdad operativa, seguridad y limpieza de contexto. Luego viene la inteligencia extra.