# Knowledge Base: AI Memory Systems

> Synthesis of 20 analyzed repositories — April 2026
> Objective: Ground the design of a shared memory system for development teams using GitHub Copilot

---

## 1. Taxonomy of Analyzed Systems

### 1.1 Orchestration Frameworks (RAG/Agents)

| Repo | Stars | License | Primary Role |
|------|-------|----------|--------------|
| **LangChain** | 133k | MIT | Agent orchestration, standard interface for models/embeddings/vector stores |
| **LlamaIndex** | 48.5k | MIT | Document-centered framework for indexing and retrieval |
| **Haystack** | 24.8k | Apache-2.0 | Search + RAG pipelines for enterprise production |
| **Quivr** | 39.1k | Apache-2.0 | "Second Brain" — opinionated RAG, `Brain.from_files()` in 5 lines |
| **AnythingLLM** | 58.1k | MIT | All-in-one workspace, privacy-first, self-hosted |
| **Open WebUI** | 131k | Custom | Extensible AI platform with local RAG and enterprise auth |

**Key lesson**: These frameworks are too heavy for team memory. They are useful as references for retrieval patterns, but they are not the right foundation for a lightweight shared-memory system.

### 1.2 Persistent Memory Systems for Agents (CORE)

| Repo | Stars | License | Main Innovation |
|------|-------|----------|-----------------|
| **nocturne_memory** | 939 | MIT | URI Graph Routing, sovereign first-person memory, glossary auto-linking |
| **LycheeMem** | 218 | Apache-2.0 | 3 memory stores (working/semantic/procedural), 4-module pipeline, academically rigorous |
| **mcp-mem0** | 670 | MIT | Minimal MCP template on top of Mem0, 3 tools |
| **DeerFlow** | 60.5k | MIT | Long-term memory with deduplication, sub-agents with isolated context |
| **PraisonAI** | 6.9k | MIT | `memory=True` flag, persistence to 20+ DBs, memory CLI |

**Key lesson**: nocturne_memory is the most directly relevant one (URI philosophy, memory sovereignty). LycheeMem contributes the most sophisticated academic retrieval approach.

### 1.3 Performance and Cache Systems

| Repo | Stars | License | Role |
|------|-------|----------|------|
| **TeleMem** | 456 | Apache-2.0 | Drop-in replacement for Mem0, 86.33% accuracy, semantic clustering with an LLM |
| **GPTCache** | 8k | MIT | Semantic cache for LLM queries, reduces cost by 10x and latency by 100x |
| **Pathway** | 63.5k | BSL 1.1 | Real-time ETL, keeps RAG indexes synchronized |

**Key lesson**: TeleMem shows that LLM-based semantic deduplication outperforms simple vector similarity. GPTCache contributes the concept of semantic caching.

### 1.4 Specialized Systems

| Repo | Stars | License | Role |
|------|-------|----------|------|
| **everything-claude-code** | 151k | MIT | Session persistence hooks, 47 agents, strategic compaction |
| **Aetherius** | 313 | Custom | Human-memory simulacra (implicit/explicit/episodic/flashbulb) |
| **KAG** | 8.7k | Apache-2.0 | Knowledge Augmented Generation with knowledge graphs |
| **OpenClaw-DeepReeder** | 222 | MIT | Web content ingestion gateway -> Markdown -> memory |

### 1.5 Meta-Resources

| Repo | Stars | License | Role |
|------|-------|----------|------|
| **Awesome-AI-Memory** | 710 | Apache-2.0 | Complete academic taxonomy, 30+ listed systems, benchmarks |

---

## 2. Key Architectural Patterns

### 2.1 MCP Protocol (Model Context Protocol)

**Adopted by**: nocturne_memory, LycheeMem, mcp-mem0, KAG, DeerFlow, PraisonAI, AnythingLLM

MCP is the de facto emerging standard for agent-to-memory communication. It enables:
- A universal interface independent of the LLM model ("One Soul, Any Engine")
- Standardized tools that any harness can invoke
- Transport through stdio or SSE (Server-Sent Events)

**Typical MCP tools** (7 in nocturne_memory):
```
read_memory, create_memory, update_memory, delete_memory,
add_alias, manage_triggers, search_memory
```

**Implication for us**: MCP is the right protocol. GitHub Copilot supports MCP tools.

### 2.2 Storage: SQLite as the Base

**Used by**: nocturne_memory, LycheeMem, everything-claude-code, GPTCache, PraisonAI

Why SQLite dominates:
- Zero-config, single file, no server required
- FTS5 for native full-text search
- WAL mode for concurrent reads
- Can be replicated/backed up as a file
- Sufficient for teams of up to about 50 developers

**LycheeMem** combines SQLite FTS5 + LanceDB vector index — the best combination discovered.

**GPTCache** supports 12+ storage backends (SQLite, PostgreSQL, MySQL, Redis, MongoDB, DynamoDB, etc.) but SQLite is the default.

### 2.3 Memory Organization: Hierarchical URI

**Originated in**: nocturne_memory

```
core://agent/identity          -> Agent identity
project://architecture         -> Architectural decisions
system://boot                  -> Automatic startup load
system://index                 -> System index
user://preferences/rzjulio     -> User preferences
team://conventions/naming      -> Team conventions
```

**Why it works**: The path IS semantics — you do not need vector search to navigate the structure because the URI already indicates the context.

### 2.4 Retrieval: Hybrid with Graceful Degradation

**Best implementation**: LycheeMem (4-module pipeline)

**General hybrid retrieval pattern**:
- Keyword search (FTS5)
- Semantic search (embeddings)
- Hybrid search (both + reranking)
- If embeddings fail -> degrade to keyword with reported `degrade_reasons`

**LycheeMem** (more sophisticated):
1. Compact Semantic Encoding -> typed extraction -> decontextualization
2. Record Fusion + Conflict Update + Hierarchical Consolidation
3. Action-Aware Hierarchical Retrieval -> composite-level relevance -> tree expansion
4. Candidate Aggregation + Context Enrichment

**Intent-Aware Search** (LycheeMem):
- 4 categories: factual, exploratory, temporal, causal
- Each intent -> a different retrieval strategy

### 2.5 Write Safety: Write Guard Pattern

**Pattern proposed by**: nocturne_memory, refined as a general concept

Auditable write pipeline:
```
Request -> Write Guard (pre-check) -> Write Lane (serialized) -> SQLite -> Snapshot
```

- Write Guard: validates before writing
- Write Lane: serializes writes to avoid race conditions
- Snapshots: allow full rollback
- SQLite lock retry: handles transient locks

### 2.6 Session Lifecycle

**Consolidated pattern** (everything-claude-code + nocturne_memory):

```
1. Boot     -> system://boot loads core memories (identity, context)
2. Recall   -> Search relevant memories for the current task
3. Work     -> The agent works with enriched context
4. Write    -> Save discoveries, decisions, fixed bugs
5. Compact  -> Consolidate context before closing
6. Recover  -> In case of compaction or crash, recover from snapshots
```

### 2.7 Memory Types (Consolidated Taxonomy)

From Awesome-AI-Memory + Aetherius + LycheeMem:

| Type | Description | Persistence | Example |
|------|-------------|-------------|---------|
| **Working Memory** | Active session context | Session | "I am refactoring the auth module" |
| **Semantic Memory** | Facts, preferences, procedures | Permanent | "The project uses TypeScript strict mode" |
| **Episodic Memory** | Specific timestamped events | Permanent | "On 04/15 we migrated from Redux to Zustand" |
| **Procedural Memory** | Reusable how-to knowledge | Permanent | "To deploy: `npm run build && vercel`" |
| **Flashbulb Memory** | Significant/emotional events | Permanent | "We discovered a memory leak causing OOM in prod" |

**LycheeMem** defines 7 MemoryRecord types: `fact, preference, event, constraint, procedure, failure_pattern, tool_affordance`

### 2.8 Deduplication and Conflicts

| Repo | Strategy |
|------|----------|
| **TeleMem** | Semantic clustering with an LLM — merge similar memories through an LLM call |
| **LycheeMem** | SHA256 hash for exact dedup + CompositeRecord hierarchy |
| **DeerFlow** | Deduplication of facts in long-term memory |
| **nocturne_memory** | Glossary auto-hyperlinking with Aho-Corasick (the memory network auto-weaves) |

### 2.9 Observability and Auditability

**TeleMem**:
- FAISS + JSON dual-write -> fast retrieval + human-readable auditability
- Metadata with timestamp, round_index, character

### 2.10 Content Ingestion

**OpenClaw-DeepReeder** contributes this pattern:
- URL -> Router (Twitter/Reddit/YouTube/Generic) -> Parser -> Clean Markdown -> Memory
- YAML frontmatter with `content_hash: sha256:...` for deduplication
- Zero API keys for primary sources

---

## 3. Proposed Reference Architecture

Synthesis of the best patterns from nocturne_memory (FastAPI + SQLite), LycheeMem (retrieval pipeline), and everything-claude-code (session hooks):

```
┌─────────────────────────────────────────────────┐
│                 MCP Clients                      │
│  (Copilot, Claude Code, Cursor, Codex, etc.)    │
└──────────────────────┬──────────────────────────┘
                       │ MCP Protocol (stdio/SSE)
                       ▼
┌─────────────────────────────────────────────────┐
│            FastAPI / MCP Backend                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │Write Guard│→ │Write Lane │→ │  SQLite DB   │ │
│  └──────────┘  │(serialized)│  │  + FTS5      │ │
│                └───────────┘  └──────────────┘ │
│                                     │           │
│                          ┌──────────▼─────────┐ │
│                          │ Async Index Worker  │ │
│                          │ (embeddings, opt.)  │ │
│                          └────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Based on**: nocturne_memory (FastAPI + SQLite + URI routing) + LycheeMem (retrieval pipeline) + everything-claude-code (session hooks)

**4 Deployment Profiles**:
- **A**: Pure local (SQLite only, no embeddings)
- **B**: Local + embeddings (SQLite + local model)
- **C**: Local + cloud embeddings (SQLite + OpenAI)
- **D**: Cloud-connected (PostgreSQL + cloud embeddings)

---

## 4. Relevant Academic Concepts (from Awesome-AI-Memory)

### 4.1 Four Layers of the Memory System
1. **Storage Layer**: Vector DBs, graph DBs, hybrid storage
2. **Processing Layer**: Embedding models, summarization, segmenters
3. **Retrieval Layer**: Multi-stage retrievers, reranking, context injectors
4. **Control Layer**: Prioritization, forgetting controllers, consistency coordinators

### 4.2 Atomic Memory Operations
- **Writing**: Convert content into vectors + store it
- **Retrieval**: Generate a query -> obtain Top-K relevant memories
- **Updating**: Find similar memories -> replace or enrich
- **Deletion**: Remove by instruction or policy (privacy/expiration)
- **Compression**: Merge related memories into summaries

### 4.3 Classification by Sharing Scope
- **Personal Memory**: Single user
- **Team Memory**: Collaborative spaces
- **Public Memory**: Shared knowledge bases

### 4.4 Forgetting Mechanisms
- **Selective Forgetting**: Machine unlearning of specific information
- **Privacy-Driven**: Automatic removal of PII
- **Memory Decay**: Priority reduction due to inactivity (configurable, e.g. 30-day half-life)
- **Conflict-Driven**: Update/discard memories contradicted by new evidence

### 4.5 Evaluation Benchmarks
- **LOCOMO, LONGMEMEVAL**: Long-term memory evaluation
- **MemBench, Minerva**: Memory mechanism evaluation
- **MemoryAgentBench**: Comprehensive agent-memory evaluation
- **HaluMem**: Memory hallucination detection

---

## 5. Critical Design Decisions

### 5.1 Vector RAG or Memory System?

nocturne_memory expressed it best: "NOT another RAG system"

**Problems with pure Vector RAG**:
- Semantic shredding: loses context when chunking documents
- Read-only: does not allow the agent to write/update its own memory
- Trigger blindness: does not know WHEN a memory is relevant
- Memory islands: isolated memories with no connections between them
- No identity: it does not maintain a persistent "self"

**Solution**: A sovereign memory system where the agent decides what to remember.

### 5.2 Where to Store for a Team?

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| SQLite local per developer | Fast, zero-config | Not shared | ✅ For personal memory |
| SQLite + sync (Git/S3) | Shareable, auditable | Merge conflicts | ⚠️ Viable with write serialization |
| PostgreSQL central | Native multi-user | Requires a server | ✅ For shared team memory |
| SQLite + Litestream | Continuous replication, zero-config | Only 1 writer | ⚠️ Enough for small teams |

**Recommendation**: Two-level architecture:
1. Local SQLite for the developer's personal memory (fast, offline)
2. Shared PostgreSQL for team memory (conventions, decisions, patterns)

### 5.3 Which Embeddings to Use?

| Option | Latency | Cost | Quality |
|--------|---------|------|---------|
| text-embedding-3-small (OpenAI) | ~50ms | $0.02/1M tokens | Good |
| nomic-embed-text (local) | ~10ms | Free | Good |
| No embeddings (FTS5 only) | ~1ms | Free | Enough for keyword search |

**Recommendation**: Start with FTS5 only (Profile A — local only), then add embeddings as an incremental improvement.

---

## 6. Existing Systems Rejected for Our Use Case

| System | Reason for Rejection |
|--------|----------------------|
| LangChain/LlamaIndex/Haystack | Too heavy; a complete framework is unnecessary |
| Quivr | Inactive (about 10 months without commits) |
| Open WebUI | Focused on chat UI, not agent memory |
| Pathway | BSL 1.1 (commercial restrictions), oriented to streaming ETL |
| KAG | Focused on knowledge graphs for QA, not agent memory |
| Aetherius | Stale (2 years without commits), monolithic, requires Qdrant |
| Memory-Palace | Project with little real traction (266 stars), ambitious docs but no verifiable production evidence |
| GPTCache | Cache, not memory — useful concept, different problem |
| OpenClaw-DeepReeder | Ingestion, not memory — could be integrated as a data source |

---

## 7. Relevance Ranking for Our Objective

1. **nocturne_memory** ⭐⭐⭐⭐⭐ — Correct philosophy (URI graph, memory sovereignty), FastAPI + SQLite architecture directly applicable
2. **LycheeMem** ⭐⭐⭐⭐⭐ — Most sophisticated retrieval, action-aware memory types, academically rigorous pipeline
3. **everything-claude-code** ⭐⭐⭐⭐ — Hook patterns for session lifecycle
4. **TeleMem** ⭐⭐⭐⭐ — LLM-based semantic deduplication, solid benchmarks
5. **DeerFlow** ⭐⭐⭐ — Long-term memory with dedup, sub-agent patterns
6. **PraisonAI** ⭐⭐⭐ — Minimal API (`memory=True`), good persistence
7. **mcp-mem0** ⭐⭐⭐ — Minimal MCP template, a good starting point
8. **Awesome-AI-Memory** ⭐⭐⭐ — Academic taxonomy to support decisions
9. **GPTCache** ⭐⭐ — Semantic-cache concept applicable as an optimization
