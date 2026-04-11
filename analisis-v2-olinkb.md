# OlinkB v2 — Re-Análisis, Brainstorming y Plan PostgreSQL

> Fecha: Abril 2026
> Contexto: Revisión profunda del plan v1 (SQLite) vs capacidades reales de los repos analizados.
> Objetivo: Un sistema que funcione verdaderamente para equipos de cualquier tamaño.

---

## Parte 1: Análisis de Brechas — ¿Qué propone v1 vs qué ya resuelven otros?

### 1.1 Lo que v1 propone correctamente

| Decisión v1 | Validada por | Estado |
|-------------|-------------|--------|
| MCP como protocolo | nocturne_memory, mcp-mem0, LycheeMem, DeerFlow | ✅ Correcto — estándar emergente de facto |
| URI namespaces (`team://`, `personal://`) | nocturne_memory | ✅ Correcto — path IS semantics |
| Write Guard + snapshots | nocturne_memory | ✅ Correcto — escritura auditable |
| Session lifecycle (boot→work→save→end) | everything-claude-code | ✅ Correcto — patrón probado |
| FTS5 para búsqueda keyword | nocturne_memory, LycheeMem | ✅ Correcto como base mínima |
| SHA256 dedup | TeleMem, OpenClaw-DeepReeder | ✅ Correcto para dedup exacto |
| Memory types (fact, preference, procedure...) | LycheeMem, Awesome-AI-Memory | ✅ Correcto — clasificación esencial |

### 1.2 Brechas CRÍTICAS de v1

#### Brecha 1: SQLite no escala para equipos reales

**Problema**: SQLite es single-writer. Con WAL mode soporta lecturas concurrentes, pero sólo 1 escritor simultáneo. Para un equipo de 5 devs con agentes guardando memorias concurrentemente, esto genera lock contention. Para 20+ devs, es inviable.

**Lo que v1 proponía**: "WAL mode + write serialization + fallback retry" — esto es un workaround, no una solución.

**Lo que los repos hacen**:
- **mcp-mem0**: Ya usa Supabase (PostgreSQL) para storage compartido
- **GPTCache**: Soporta PostgreSQL, MySQL, Redis como backends
- **nocturne_memory**: Solo SQLite — pero es diseñado para 1 agente personal, no equipos
- **Awesome-AI-Memory**: Documenta PostgreSQL + pgvector como arquitectura de producción

**Veredicto**: PostgreSQL no es una mejora futura — es un requisito para equipos.

#### Brecha 2: Sin retrieval intent-aware

**Problema**: v1 solo propone FTS5 (keyword) + embeddings opcionales. No distingue el _tipo_ de pregunta.

**Lo que LycheeMem ya implementa**:
- 4 categorías de intent: `factual`, `exploratory`, `temporal`, `causal`
- Cada intent → estrategia de retrieval diferente
- Action-Aware Hierarchical Retrieval → no solo busca, entiende qué acción necesita el agente
- Composite records con tree expansion para dar contexto completo

**Lo que v1 ignora**: LycheeMem tiene un pipeline de retrieval de 4 módulos:
1. Ingestion Module → typed extraction → decontextualization
2. Consolidation Module → fusion + conflict → hierarchical consolidation
3. Retrieval Module → intent-aware → tree expansion → context enrichment
4. Response Module → relevance filtering → formatted output

v1 solo tiene `remember(query)` → FTS5 → resultados. Es un grep glorificado.

#### Brecha 3: Sin dedup semántico

**Problema**: v1 usa SHA256 para dedup exacto. Pero dos memorias pueden decir esencialmente lo mismo con palabras diferentes.

**Lo que TeleMem ya resuelve**:
- Clustering semántico con LLM: agrupa memorias similares y las merge
- 86.33% accuracy en benchmarks de retrieval
- Reduce la base de memorias sin perder información

**Lo que nocturne_memory aporta que v1 no tiene**:
- Glossary auto-hyperlinking con Aho-Corasick: las memorias se auto-enlazan cuando mencionan conceptos ya guardados

v1 acumularía memorias redundantes sin mecanismo de consolidación inteligente.

#### Brecha 4: Sin identidad de equipo ni roles

**Problema**: v1 tiene `author` como string pero no hay concepto de roles, permisos, ni quién puede escribir en qué namespace.

**Lo que falta**:
- Un dev junior no debería poder sobreescribir `team://conventions/architecture`
- Las memorias de un dev no deberían ser visibles para todos sin control
- No hay audit trail de quién escribió qué y cuándo se cambió

**Lo que los repos no resuelven tampoco** (oportunidad):
- nocturne_memory: diseñado para 1 agente, no tiene roles
- mcp-mem0: user-scoped pero sin roles
- DeerFlow: sub-agent isolation pero sin permisos de equipo

**Esta es un área donde OlinkB puede innovar genuinamente.**

#### Brecha 5: Sin mecanismo de olvido inteligente

**Problema**: v1 tiene `vitality_score` con decay pero no implementa forgetting policies.

**Lo que Awesome-AI-Memory documenta**:
- Selective Forgetting: eliminar info específica (machine unlearning)
- Privacy-Driven: auto-eliminación de PII
- Memory Decay: half-life configurable por tipo
- Conflict-Driven: memoria nueva contradice antigua → resolver

**Lo que Aetherius modela (parcialmente útil)**:
- Flashbulb memories que persisten más (alta importancia emocional)
- Implicit vs explicit memory decay curves diferentes

v1 solo tiene "decay" como concepto abstracto sin implementación real.

#### Brecha 6: Sin working memory management

**Problema**: v1 no distingue entre contexto activo de sesión (working memory) y memoria Long-Term.

**Lo que LycheeMem implementa**:
- 3 stores separados: Working Memory, Semantic Memory, Procedural Memory
- Dual-threshold compression: cuando working memory excede thresholds, se comprime y migra a semantic
- El agente sabe qué está en su "cabeza" vs qué está archivado

v1 guarda todo como `memories` en la misma tabla sin distinción temporal/funcional.

---

### 1.3 Lo que NINGÚN repo resuelve (oportunidad real de OlinkB)

| Problema | Estado en los 20 repos | Oportunidad para OlinkB |
|----------|----------------------|------------------------|
| Memoria compartida multi-equipo real | Nadie lo resuelve bien | PostgreSQL + Row-Level Security + namespaces |
| RBAC (roles y permisos) en memoria | No existe | Roles por dev, permisos por namespace |
| Sincronización en tiempo real | No existe en MCP servers | PostgreSQL LISTEN/NOTIFY para invalidación de caché |
| Onboarding automático de nuevos devs | No existe | `boot_session` carga convenciones del equipo + historial relevante |
| Memoria entre proyectos de la misma org | No existe | `org://` namespace que trasciende proyectos |
| Auditoría de cambios con diff | Snapshots existen (nocturne) pero sin diff | PostgreSQL temporal tables o audit log |
| Analytics de uso de memoria | No existe | ¿Qué memorias son más consultadas? ¿Qué tipo se guarda más? |

---

## Parte 2: Brainstorming — Tres Enfoques Arquitectónicos

### Enfoque A: PostgreSQL-First Monolith

```
┌─────────────────────────────────────────────────────────────┐
│                   MCP Clients (cada dev)                     │
│  Copilot, Claude Code, Cursor, Codex CLI...                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ MCP Protocol (SSE over HTTP)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                OlinkB MCP Server (1 instancia)               │
│  ┌───────────┐  ┌───────────┐  ┌────────────┐              │
│  │Write Guard│→ │Permission │→ │Query Router │              │
│  │           │  │  Check    │  │(URI→schema) │              │
│  └───────────┘  └───────────┘  └──────┬─────┘              │
│                                       ▼                      │
│                         ┌─────────────────────┐              │
│                         │    PostgreSQL        │              │
│                         │  + pgvector          │              │
│                         │  + pg_trgm (FTS)     │              │
│                         │  + RLS policies      │              │
│                         └─────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

**Cómo funciona**:
- Una sola instancia del MCP server (puede ser un container) accesible por red
- Todos los devs apuntan al mismo server via SSE transport
- PostgreSQL maneja concurrencia nativamente (MVCC)
- Row-Level Security (RLS) enforces permisos a nivel de DB
- pgvector para búsqueda semántica nativa
- pg_trgm para búsqueda full-text

**Pros**:
- ✅ Simple: 1 server, 1 DB, 1 fuente de verdad
- ✅ Concurrencia nativa (MVCC) — sin lock contention
- ✅ RLS para permisos reales a nivel de base de datos
- ✅ pgvector integrado — búsqueda semántica sin servicios adicionales
- ✅ Backup/restore estándar (pg_dump, WAL archiving)
- ✅ Escala a cientos de devs sin cambios arquitectónicos
- ✅ LISTEN/NOTIFY para eventos en tiempo real

**Contras**:
- ❌ Requiere PostgreSQL corriendo (infra)
- ❌ Sin modo offline — requiere conectividad
- ❌ Latencia de red (~5-50ms) vs SQLite (<1ms)
- ❌ Single point of failure (mitígale con replicas)
- ❌ Setup más complejo que `pip install && go`

---

### Enfoque B: Hybrid (SQLite Local + PostgreSQL Central)

```
┌──────────────────────────────────────────────────────────────────┐
│                    Dev Machine (cada uno)                         │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │   OlinkB MCP Server (local, stdio)                        │   │
│  │   ┌────────────┐   ┌────────────┐   ┌─────────────────┐  │   │
│  │   │Working Mem  │   │Personal Mem│   │  Sync Engine    │  │   │
│  │   │(in-memory)  │   │(SQLite)    │   │  (←→ PG)       │  │   │
│  │   └────────────┘   └────────────┘   └───────┬─────────┘  │   │
│  └─────────────────────────────────────────────┼─────────────┘   │
└─────────────────────────────────────────────────┼────────────────┘
                                                  │ HTTPS
                                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   OlinkB Sync API                                │
│   ┌────────────────┐   ┌────────────────────────────────┐       │
│   │  Conflict Res  │   │        PostgreSQL               │       │
│   │  (LWW/CRDT)    │   │  team://, org://, shared mem    │       │
│   └────────────────┘   │  + pgvector + audit log         │       │
│                        └────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────┘
```

**Cómo funciona**:
- Cada dev tiene un MCP server local (stdio, rápido)
- Working memory vive en memoria del proceso
- Personal memory en SQLite local
- Team/org memory se sincroniza bidireccionalmente con PostgreSQL
- Un Sync API maneja conflictos (Last-Write-Wins o CRDTs)

**Pros**:
- ✅ Rapidísimo en local (<1ms para lecturas frecuentes)
- ✅ Funciona offline (personal + working memory)
- ✅ Team memory compartida via PostgreSQL
- ✅ Separación limpia de responsabilidades (local vs compartido)

**Contras**:
- ❌ Complejidad de sincronización (merge conflicts, eventual consistency)
- ❌ 2 motores de storage que mantener (SQLite + PostgreSQL)
- ❌ El sync puede perder datos si el dev no se sincroniza antes de cerrar
- ❌ Debugging más difícil (¿está en local o en central?)
- ❌ CRDTs o LWW agregan complejidad significativa
- ❌ Más código, más superficie de bugs

---

### Enfoque C: PostgreSQL Central + Read Cache Local

```
┌──────────────────────────────────────────────────────────────────┐
│                    Dev Machine (cada uno)                         │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │   OlinkB MCP Server (local, stdio)                        │   │
│  │   ┌────────────┐   ┌────────────────────────────────────┐ │   │
│  │   │Working Mem  │   │  Read Cache (SQLite/in-memory)     │ │   │
│  │   │(session)    │   │  TTL-based invalidation            │ │   │
│  │   └────────────┘   │  + PG LISTEN/NOTIFY refresh        │ │   │
│  │                    └───────────────┬────────────────────┘ │   │
│  └────────────────────────────────────┼──────────────────────┘   │
└───────────────────────────────────────┼──────────────────────────┘
                                        │ All writes + cache misses
                                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Central                            │
│   ┌────────────┐  ┌──────────┐  ┌────────┐  ┌───────────────┐  │
│   │  memories   │  │ pgvector │  │  RLS   │  │  audit_log    │  │
│   │  + FTS      │  │ index    │  │ policies│  │  (temporal)   │  │
│   └────────────┘  └──────────┘  └────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Cómo funciona**:
- PostgreSQL es la única fuente de verdad
- Todas las escrituras van directo a PostgreSQL
- Un read cache local (SQLite o in-memory) almacena memorias frecuentes
- LISTEN/NOTIFY de PostgreSQL invalida el caché cuando otro dev escribe
- Working memory (sesión activa) vive solo en memoria local

**Pros**:
- ✅ Una sola fuente de verdad — no hay conflictos de sync
- ✅ Lecturas rápidas en caché (<1ms para hits)
- ✅ Writes siempre consistentes (no eventual consistency)
- ✅ LISTEN/NOTIFY da near-real-time invalidation
- ✅ Más simple que hybrid (no hay 2-way sync ni CRDTs)
- ✅ Funciona parcialmente offline (cache de lectura + working memory)

**Contras**:
- ❌ Writes requieren conectividad (sin modo offline para escritura)
- ❌ Cache invalidation puede tener edge cases
- ❌ Primer boot requiere cargar caché desde PostgreSQL (cold start)
- ❌ Requiere PostgreSQL infra

---

### Matriz de Decisión

| Criterio | Peso | A: PG Monolith | B: Hybrid | C: PG + Cache |
|----------|------|:-:|:-:|:-:|
| Simplicidad de implementación | 25% | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| Rendimiento en lectura | 15% | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Consistencia de datos | 20% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Escalabilidad (equipos grandes) | 20% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Modo offline | 10% | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Mantenibilidad | 10% | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Score ponderado** | | **4.05** | **3.35** | **4.25** |

### 🏆 Recomendación: Enfoque C (PostgreSQL Central + Read Cache Local)

**Razón**: Combina la consistencia y escalabilidad de PostgreSQL con rendimiento local comparable a SQLite. Evita la complejidad del sync bidireccional del Enfoque B. El modo offline parcial (lecturas del cache + working memory) cubre el 90% de los casos reales — un desarrollador casi siempre tiene conectividad en el contexto de un equipo.

---

## Parte 3: Plan OlinkB v2 — PostgreSQL-First con Read Cache

### 3.1 Principios de Diseño (actualizados)

| Principio | Implementación |
|-----------|---------------|
| **PostgreSQL es la verdad** | Toda escritura va a PostgreSQL. No SQLite para datos compartidos |
| **MCP-native** | Protocolo estándar, compatible con Copilot/Claude/Cursor |
| **Cache, no sync** | Read cache local con invalidation — no replicación bidireccional |
| **Identity-first** | Cada dev tiene identidad, roles, y permisos verificables |
| **Intent-aware retrieval** | No solo keyword — entiende qué tipo de pregunta se está haciendo |
| **Smart dedup** | Clustering semántico para merge, no solo SHA256 |
| **Forgetting policies** | Memoria que decae, se consolida, y se limpia automáticamente |
| **Observable** | Cada operación genera audit trail queryable |

### 3.2 Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                  MCP Clients (N desarrolladores)                     │
│  Cada dev: Copilot / Claude Code / Cursor / Codex CLI               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ stdio (local server per dev)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            OlinkB MCP Server (proceso local por dev)                 │
│                                                                      │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Working Memory │  │  Read Cache  │  │   Retrieval Pipeline     │  │
│  │ (in-process)   │  │  (in-memory  │  │  ┌────────┐ ┌────────┐  │  │
│  │                │  │   LRU/TTL)   │  │  │Keyword │ │Semantic│  │  │
│  │ Session state, │  │              │  │  │(pg_trgm)│ │(pgvec) │  │  │
│  │ active context │  │ boot_session │  │  └───┬────┘ └───┬────┘  │  │
│  │                │  │ results,     │  │      └────┬─────┘       │  │
│  │                │  │ frequent     │  │   ┌───────▼──────┐      │  │
│  │                │  │ queries      │  │   │ Intent-Aware │      │  │
│  │                │  │              │  │   │ Reranker     │      │  │
│  └───────────────┘  └──────┬───────┘  │   └──────────────┘      │  │
│                            │          └──────────────────────────┘  │
│  ┌──────────────────┐      │                                        │
│  │ Write Guard      │      │                                        │
│  │ + Permission     │      │                                        │
│  │   Enforcer       │      │                                        │
│  └────────┬─────────┘      │                                        │
└───────────┼────────────────┼────────────────────────────────────────┘
            │ writes         │ cache miss / invalidation
            ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PostgreSQL (source of truth)                        │
│                                                                      │
│  ┌───────────┐  ┌──────────┐  ┌───────┐  ┌────────┐  ┌──────────┐ │
│  │ memories  │  │ pgvector │  │  RLS  │  │ audit  │  │ sessions │ │
│  │ + GIN idx │  │ (HNSW)   │  │ rules │  │ _log   │  │          │ │
│  └───────────┘  └──────────┘  └───────┘  └────────┘  └──────────┘ │
│                                                                      │
│  LISTEN/NOTIFY → cache invalidation a todos los MCP servers          │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 Schema PostgreSQL

```sql
-- Extensiones requeridas
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- trigram similarity

-- =============================================
-- TABLA: team_members (identidad)
-- =============================================
CREATE TABLE team_members (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    TEXT UNIQUE NOT NULL,       -- "rzjulio", "maria", etc.
    display_name TEXT,
    role        TEXT NOT NULL DEFAULT 'developer',  
                -- 'admin', 'lead', 'developer', 'viewer'
    team        TEXT NOT NULL,              -- "mi-equipo"
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    is_active   BOOLEAN DEFAULT true
);

-- =============================================
-- TABLA: memories (core)
-- =============================================
CREATE TABLE memories (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uri             TEXT NOT NULL UNIQUE,   -- "team://conventions/naming"
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    memory_type     TEXT NOT NULL CHECK (memory_type IN (
        'fact', 'preference', 'event', 'constraint',
        'procedure', 'failure_pattern', 'tool_affordance',
        'convention', 'decision', 'discovery'
    )),
    scope           TEXT NOT NULL CHECK (scope IN (
        'personal', 'project', 'team', 'org', 'system'
    )),
    namespace       TEXT NOT NULL,          -- extracted from URI prefix
    author_id       UUID NOT NULL REFERENCES team_members(id),
    tags            TEXT[] DEFAULT '{}',
    content_hash    TEXT NOT NULL,          -- SHA256 del content
    embedding       vector(1536),           -- pgvector, nullable hasta que se compute
    vitality_score  REAL DEFAULT 1.0,
    access_count    INTEGER DEFAULT 0,
    last_accessed   TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,            -- NULL = no expira
    superseded_by   UUID REFERENCES memories(id),  -- para memory evolution
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Índices de búsqueda
CREATE INDEX idx_memories_uri      ON memories USING btree (uri);
CREATE INDEX idx_memories_ns       ON memories USING btree (namespace);
CREATE INDEX idx_memories_author   ON memories USING btree (author_id);
CREATE INDEX idx_memories_type     ON memories USING btree (memory_type);
CREATE INDEX idx_memories_scope    ON memories USING btree (scope);
CREATE INDEX idx_memories_tags     ON memories USING gin (tags);
CREATE INDEX idx_memories_hash     ON memories USING btree (content_hash);
CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- Full-text search con trigrams para fuzzy matching
CREATE INDEX idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops);
CREATE INDEX idx_memories_title_trgm   ON memories USING gin (title gin_trgm_ops);

-- =============================================
-- TABLA: memory_links (grafo de relaciones)
-- =============================================
CREATE TABLE memory_links (
    source_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type   TEXT NOT NULL CHECK (link_type IN (
        'supersedes', 'related', 'contradicts', 'derived_from',
        'implements', 'blocks', 'references'
    )),
    created_by  UUID REFERENCES team_members(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_id, target_id, link_type)
);

-- =============================================
-- TABLA: sessions (lifecycle tracking)
-- =============================================
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    author_id   UUID NOT NULL REFERENCES team_members(id),
    project     TEXT,
    started_at  TIMESTAMPTZ DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT,
    memories_created  INTEGER DEFAULT 0,
    memories_accessed INTEGER DEFAULT 0
);

-- =============================================
-- TABLA: audit_log (inmutable)
-- =============================================
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    actor_id    UUID NOT NULL REFERENCES team_members(id),
    action      TEXT NOT NULL,  -- 'create', 'update', 'delete', 'access', 'merge'
    memory_id   UUID REFERENCES memories(id),
    uri         TEXT,
    old_content TEXT,           -- para updates/deletes
    new_content TEXT,           -- para creates/updates
    metadata    JSONB          -- contexto adicional
);

-- =============================================
-- TABLA: forgetting_policies
-- =============================================
CREATE TABLE forgetting_policies (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    scope       TEXT NOT NULL,             -- qué scope afecta
    memory_type TEXT,                       -- NULL = aplica a todos
    rule_type   TEXT NOT NULL CHECK (rule_type IN (
        'decay', 'ttl', 'access_threshold', 'consolidation'
    )),
    config      JSONB NOT NULL,            -- parámetros de la regla
    is_active   BOOLEAN DEFAULT true,
    created_by  UUID REFERENCES team_members(id)
);

-- Ejemplo de config para decay:
-- {"half_life_days": 30, "min_vitality": 0.1, "exempt_types": ["convention", "decision"]}

-- =============================================
-- ROW-LEVEL SECURITY (RLS)
-- =============================================
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Todos ven team, org, system, project
CREATE POLICY memories_read_shared ON memories
    FOR SELECT
    USING (scope IN ('team', 'org', 'system', 'project'));

-- Solo el autor ve sus personales
CREATE POLICY memories_read_personal ON memories
    FOR SELECT
    USING (
        scope = 'personal'
        AND author_id = current_setting('olinkb.current_user_id')::uuid
    );

-- Solo el autor escribe personales
CREATE POLICY memories_write_personal ON memories
    FOR INSERT
    WITH CHECK (
        scope = 'personal'
        AND author_id = current_setting('olinkb.current_user_id')::uuid
    );

-- Devs escriben project, leads/admins escriben team
CREATE POLICY memories_write_shared ON memories
    FOR INSERT
    WITH CHECK (
        CASE scope
            WHEN 'project' THEN true  -- cualquier dev del proyecto
            WHEN 'team' THEN EXISTS (
                SELECT 1 FROM team_members
                WHERE id = current_setting('olinkb.current_user_id')::uuid
                AND role IN ('admin', 'lead', 'developer')
            )
            WHEN 'org' THEN EXISTS (
                SELECT 1 FROM team_members
                WHERE id = current_setting('olinkb.current_user_id')::uuid
                AND role IN ('admin', 'lead')
            )
            WHEN 'system' THEN EXISTS (
                SELECT 1 FROM team_members
                WHERE id = current_setting('olinkb.current_user_id')::uuid
                AND role = 'admin'
            )
            ELSE false
        END
    );

-- Updates: solo autor (personal), leads/admins (team/org/system)
CREATE POLICY memories_update ON memories
    FOR UPDATE
    USING (
        (scope = 'personal' AND author_id = current_setting('olinkb.current_user_id')::uuid)
        OR (scope IN ('project', 'team') AND EXISTS (
            SELECT 1 FROM team_members
            WHERE id = current_setting('olinkb.current_user_id')::uuid
            AND role IN ('admin', 'lead', 'developer')
        ))
        OR (scope IN ('org', 'system') AND EXISTS (
            SELECT 1 FROM team_members
            WHERE id = current_setting('olinkb.current_user_id')::uuid
            AND role IN ('admin', 'lead')
        ))
    );

-- =============================================
-- FUNCIONES de notificación
-- =============================================
CREATE OR REPLACE FUNCTION notify_memory_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('memory_changes', json_build_object(
        'action', TG_OP,
        'memory_id', COALESCE(NEW.id, OLD.id)::text,
        'uri', COALESCE(NEW.uri, OLD.uri),
        'scope', COALESCE(NEW.scope, OLD.scope),
        'namespace', COALESCE(NEW.namespace, OLD.namespace),
        'author_id', COALESCE(NEW.author_id, OLD.author_id)::text
    )::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memory_change_trigger
    AFTER INSERT OR UPDATE OR DELETE ON memories
    FOR EACH ROW EXECUTE FUNCTION notify_memory_change();

-- =============================================
-- FUNCIONES de retrieval
-- =============================================

-- Búsqueda híbrida: keyword + semántica con reranking
CREATE OR REPLACE FUNCTION search_memories(
    query_text TEXT,
    query_embedding vector(1536) DEFAULT NULL,
    scope_filter TEXT[] DEFAULT NULL,
    type_filter TEXT[] DEFAULT NULL,
    limit_n INTEGER DEFAULT 10,
    keyword_weight REAL DEFAULT 0.4,
    semantic_weight REAL DEFAULT 0.6
)
RETURNS TABLE (
    id UUID,
    uri TEXT,
    title TEXT,
    content TEXT,
    memory_type TEXT,
    scope TEXT,
    score REAL,
    match_source TEXT  -- 'keyword', 'semantic', 'hybrid'
) AS $$
BEGIN
    RETURN QUERY
    WITH keyword_results AS (
        SELECT m.id, m.uri, m.title, m.content, m.memory_type, m.scope,
               similarity(m.content, query_text) AS sim_score,
               'keyword'::TEXT AS source
        FROM memories m
        WHERE (scope_filter IS NULL OR m.scope = ANY(scope_filter))
          AND (type_filter IS NULL OR m.memory_type = ANY(type_filter))
          AND m.superseded_by IS NULL
          AND (m.expires_at IS NULL OR m.expires_at > NOW())
          AND (m.content % query_text OR m.title % query_text)  -- trigram similarity
        ORDER BY sim_score DESC
        LIMIT limit_n * 2
    ),
    semantic_results AS (
        SELECT m.id, m.uri, m.title, m.content, m.memory_type, m.scope,
               1 - (m.embedding <=> query_embedding) AS sim_score,
               'semantic'::TEXT AS source
        FROM memories m
        WHERE query_embedding IS NOT NULL
          AND m.embedding IS NOT NULL
          AND (scope_filter IS NULL OR m.scope = ANY(scope_filter))
          AND (type_filter IS NULL OR m.memory_type = ANY(type_filter))
          AND m.superseded_by IS NULL
          AND (m.expires_at IS NULL OR m.expires_at > NOW())
        ORDER BY m.embedding <=> query_embedding
        LIMIT limit_n * 2
    ),
    combined AS (
        SELECT DISTINCT ON (r.id)
            r.id, r.uri, r.title, r.content, r.memory_type, r.scope,
            COALESCE(k.sim_score * keyword_weight, 0) +
            COALESCE(s.sim_score * semantic_weight, 0) AS final_score,
            CASE
                WHEN k.id IS NOT NULL AND s.id IS NOT NULL THEN 'hybrid'
                WHEN k.id IS NOT NULL THEN 'keyword'
                ELSE 'semantic'
            END AS match_source
        FROM (
            SELECT id, uri, title, content, memory_type, scope FROM keyword_results
            UNION
            SELECT id, uri, title, content, memory_type, scope FROM semantic_results
        ) r
        LEFT JOIN keyword_results k ON k.id = r.id
        LEFT JOIN semantic_results s ON s.id = r.id
    )
    SELECT c.id, c.uri, c.title, c.content, c.memory_type, c.scope,
           c.final_score, c.match_source
    FROM combined c
    ORDER BY c.final_score DESC
    LIMIT limit_n;
END;
$$ LANGUAGE plpgsql;

-- Vitality decay (ejecutar periódicamente via pg_cron o cron externo)
CREATE OR REPLACE FUNCTION apply_vitality_decay(
    half_life_days INTEGER DEFAULT 30
) RETURNS INTEGER AS $$
DECLARE
    affected INTEGER;
BEGIN
    UPDATE memories
    SET vitality_score = vitality_score * power(0.5, 
        EXTRACT(EPOCH FROM (NOW() - COALESCE(last_accessed, updated_at))) 
        / (half_life_days * 86400)
    ),
    updated_at = NOW()
    WHERE vitality_score > 0.05
      AND superseded_by IS NULL;
    
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;
```

### 3.4 MCP Tools (v2)

#### Tier 1: Core (MVP — 6 tools)

| Tool | Descripción | Cambio vs v1 |
|------|-------------|-------------|
| `boot_session` | Carga contexto del equipo + personal para la sesión | Ahora carga desde PostgreSQL + llena read cache |
| `remember` | Busca memorias relevantes (hybrid search) | Ahora con intent-aware retrieval + semantic search nativo (pgvector) |
| `save_memory` | Guarda una nueva memoria | Escribe a PostgreSQL + trigger NOTIFY → invalida caches de otros devs |
| `update_memory` | Actualiza memoria existente con audit trail | **NUEVO** — v1 no tenía update explícito |
| `end_session` | Cierra sesión con resumen | Ahora persiste summary en `sessions` table |
| `forget` | Marca memoria como obsoleta o la elimina | Ahora con `superseded_by` chain + audit log |

#### Tier 2: Equipo (6 tools)

| Tool | Descripción | Fuente |
|------|-------------|--------|
| `team_digest` | Resume actividad reciente del equipo | v1 (mantenido) |
| `link_memories` | Crea relación entre 2 memorias | **NUEVO** — grafo de relaciones |
| `consolidate` | Merge de N memorias similares en 1 via LLM | **NUEVO** — inspirado por TeleMem |
| `search_by_author` | Busca memorias de un dev específico | **NUEVO** — útil para handoffs |
| `list_conventions` | Lista todas las `team://conventions/*` | **NUEVO** — acceso rápido a normas del equipo |
| `propose_convention` | Propone nueva convención (requiere approval de lead) | **NUEVO** — workflow de governance |

#### Tier 3: Inteligencia (4 tools)

| Tool | Descripción | Fuente de inspiración |
|------|-------------|----------------------|
| `search_semantic` | Búsqueda pure semantic sin keyword | pgvector nativo |
| `find_contradictions` | Detecta memorias que se contradicen | Awesome-AI-Memory (conflict-driven forgetting) |
| `suggest_links` | Sugiere relaciones entre memorias via LLM | nocturne_memory (glossary auto-linking) |
| `memory_analytics` | Estadísticas de uso, tipos, autores, trends | **NUEVO** — observabilidad |

### 3.5 Retrieval Pipeline (Intent-Aware)

```
Query del agente
       │
       ▼
┌──────────────────────┐
│ 1. Intent Classifier │  ← Clasifica: factual / exploratory / temporal / causal
│    (heurístico/LLM)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│ 2. Query Expansion                                    │
│    factual    → búsqueda exacta, prioriza conventions │
│    exploratory → búsqueda broad, incluye related links│
│    temporal   → agrega filtro de fechas, ordena by time│
│    causal     → sigue cadenas superseded_by + links   │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│ 3. search_memories() (PostgreSQL function)            │
│    keyword (pg_trgm) + semantic (pgvector) + rerank   │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│ 4. Context Enrichment                                 │
│    Para cada resultado, cargar memory_links            │
│    Expandir con memorias relacionadas (1 hop)         │
│    Incluir metadata: author, created_at, access_count │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│ 5. Vitality + Freshness Boost                         │
│    Score final = retrieval_score * vitality_boost      │
│    Boost recency para temporal queries                 │
│    Boost access_count para frequently-used             │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
       Resultados al agente
```

**Inspirado por**: LycheeMem (4-module pipeline), nocturne_memory (URI routing), TeleMem (semantic clustering)

### 3.6 Read Cache Local

```python
class ReadCache:
    """In-memory LRU cache con TTL e invalidation via PG LISTEN/NOTIFY."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
    
    # boot_session precarga:
    #   - team://conventions/*
    #   - system://boot/*
    #   - personal://{author}/* (top 50 by vitality)
    #   - project://* del proyecto actual (top 50)
    
    # PG LISTEN/NOTIFY:
    #   - On 'memory_changes' → invalida entry por memory_id
    #   - Si namespace cambia → invalida todo el namespace
    
    # Cache miss → query PostgreSQL → populate cache → return
```

### 3.7 Forgetting Engine

```
┌─────────────────────────────────────────────────┐
│              Forgetting Engine                    │
│  (scheduled job: daily o configurable)           │
│                                                   │
│  1. Vitality Decay                               │
│     - apply_vitality_decay(half_life_days=30)    │
│     - Exempt: conventions, decisions (siempre 1.0)│
│                                                   │
│  2. TTL Enforcement                              │
│     - Expira memorias con expires_at < NOW()     │
│     - Auto-TTL para tipos efímeros (events: 90d) │
│                                                   │
│  3. Consolidation                                │
│     - Detecta clusters de memorias similares     │
│     - (embedding distance < threshold)           │
│     - Propone merge via LLM → crea consolidated  │
│     - Marca originales como superseded_by        │
│                                                   │
│  4. Contradiction Detection                      │
│     - Busca pares con link_type = 'contradicts'  │
│     - Prioriza la más reciente                   │
│     - Notifica al team lead si ambas son team://  │
│                                                   │
│  5. Dead Memory Cleanup                          │
│     - vitality < 0.05 + access_count = 0         │
│     - + last_accessed > 90 days ago              │
│     - → Archive (no delete) con audit log        │
└─────────────────────────────────────────────────┘
```

### 3.8 Identity & Permissions Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    Permission Matrix                             │
│                                                                  │
│  Namespace        │ viewer │ developer │  lead  │ admin          │
│  ─────────────────┼────────┼───────────┼────────┼───────         │
│  personal://me    │   -    │    RW     │   -    │   -            │
│  personal://other │   -    │    -      │   R    │   R            │
│  project://*      │   R    │    RW     │   RW   │  RW            │
│  team://*         │   R    │    R+P    │   RW   │  RW            │
│  org://*          │   R    │    R      │   R+P  │  RW            │
│  system://*       │   R    │    R      │   R    │  RW            │
│                                                                  │
│  R = Read, W = Write, P = Propose (requiere approval),          │
│  - = No access                                                   │
└─────────────────────────────────────────────────────────────────┘
```

Un developer puede **proponer** memorias `team://` que un lead aprueba:

```python
# Developer ejecuta:
save_memory(
    uri="team://conventions/error-handling",
    content="Use Result<T, E> pattern instead of try/catch",
    scope="team", 
    memory_type="convention"
)
# → Estado: 'proposed' (no visible como convention activa)
# → Lead recibe notificación
# → Lead llama: approve_memory(memory_id) → estado: 'active'
```

### 3.9 Onboarding de Nuevos Devs

Uno de los beneficios únicos de OlinkB v2: cuando un dev nuevo se une al equipo:

```
1. Admin ejecuta: olinkb add-member --username "nueva-dev" --role developer --team "mi-equipo"
2. Nueva dev configura su mcp.json (template provisto)
3. Primera sesión: boot_session carga:
   - Todas las team://conventions/* → "Así trabaja el equipo"
   - Top 20 team://decisions/* → "Historia de decisiones clave"
   - project://architecture/* del proyecto asignado → "Cómo funciona esto"
   - team://procedures/* → "Cómo hacer deploy, review, etc."
4. El agente del dev nuevo YA SABE las convenciones del equipo desde la primera sesión
```

Esto resuelve un problema real que ningún repo aborda: la transferencia de conocimiento tácito.

### 3.10 Namespaces v2

| Namespace | Propósito | Persistencia | Acceso |
|-----------|----------|-------------|--------|
| `personal://{user}/*` | Notas, preferencias, shortcuts del dev | Permanente | Solo el autor |
| `project://{name}/*` | Decisiones y contexto del proyecto | Permanente | Todo el equipo del proyecto |
| `team://*` | Convenciones, patterns, procedures | Permanente + governance | Todo el equipo (write con permisos) |
| `org://*` | Estándares de la organización | Permanente + governance | Todos los equipos de la org |
| `system://*` | Config de boot, index, identity | Permanente | Admins write, todos read |
| `session://{id}/*` | Working memory de la sesión actual | Efímero (se archiva al end_session) | Solo la sesión activa |

**Nuevo vs v1**: `org://` para compartir entre proyectos, `session://` explícito para working memory.

### 3.11 Connection & Transport

```yaml
# Local MCP server (cada dev) — stdio transport
# El MCP server corre en la máquina del dev

# .vscode/mcp.json
{
  "servers": {
    "olinkb": {
      "command": "olinkb",
      "args": ["serve"],
      "env": {
        "OLINKB_PG_URL": "postgresql://olinkb:***@db.equipo.internal:5432/olinkb",
        "OLINKB_USER": "${env:USER}",
        "OLINKB_TEAM": "mi-equipo"
      }
    }
  }
}
```

**¿Por qué stdio y no SSE?**
- stdio es más rápido (no HTTP overhead)
- El MCP server corre local — la conexión a PostgreSQL es interna
- Copilot/Claude Code prefieren stdio para servers locales
- El read cache hace que la mayoría de lecturas no toquen la red

**¿Qué hay del PostgreSQL remoto?**
- Connection pooling (PgBouncer o pg_pool) en el server PostgreSQL
- El MCP server mantiene un pool de ~5 conexiones
- Writes: 1 query directa a PostgreSQL
- Reads: cache hit = 0 network, cache miss = 1 query

### 3.12 Estructura del Proyecto

```
olinkb/
├── pyproject.toml
├── README.md
├── src/
│   └── olinkb/
│       ├── __init__.py
│       ├── server.py              # FastMCP server (entry point)
│       ├── cli.py                 # CLI: init, add-member, migrate, serve
│       ├── config.py              # Config from env vars
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── postgres.py        # PostgreSQL client (asyncpg)
│       │   ├── cache.py           # Read cache (LRU + TTL + LISTEN/NOTIFY)
│       │   └── migrations/        # SQL migrations (versioned)
│       │       ├── 001_init.sql
│       │       ├── 002_rls.sql
│       │       └── 003_functions.sql
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── session.py         # boot_session, end_session
│       │   ├── memory.py          # save_memory, update_memory, forget, remember
│       │   ├── team.py            # team_digest, list_conventions, propose_convention
│       │   ├── links.py           # link_memories, suggest_links
│       │   └── analytics.py       # memory_analytics, find_contradictions
│       │
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── pipeline.py        # Intent-aware retrieval pipeline
│       │   ├── intent.py          # Intent classifier (factual/exploratory/temporal/causal)
│       │   ├── ranker.py          # Hybrid reranking (keyword + semantic + vitality)
│       │   └── embeddings.py      # Embedding computation (async, optional)
│       │
│       ├── guards/
│       │   ├── __init__.py
│       │   ├── write_guard.py     # Pre-write validation
│       │   ├── permissions.py     # Role-based permission enforcement
│       │   └── dedup.py           # SHA256 + semantic dedup
│       │
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── forgetting.py      # Vitality decay, TTL, consolidation
│       │   ├── consolidator.py    # LLM-based semantic merge
│       │   └── linker.py          # Auto-linking (glossary pattern, Aho-Corasick)
│       │
│       └── templates/
│           ├── mcp.json.j2        # Template para .vscode/mcp.json
│           └── instructions.md.j2 # Template para .instructions.md
│
├── tests/
│   ├── conftest.py                # PostgreSQL test fixtures (testcontainers)
│   ├── test_storage.py
│   ├── test_retrieval.py
│   ├── test_guards.py
│   ├── test_tools.py
│   └── test_forgetting.py
│
├── docker/
│   ├── Dockerfile                 # OlinkB server
│   ├── docker-compose.yml         # PostgreSQL + pgvector + OlinkB
│   └── init.sql                   # Bootstrap DB
│
└── docs/
    ├── setup.md                   # Guía de instalación
    ├── team-admin.md              # Gestión de equipo
    └── architecture.md            # Decisiones arquitectónicas
```

### 3.13 Fases de Implementación

#### Fase 1: Foundation (2-3 semanas)
- [ ] Schema PostgreSQL + migrations
- [ ] Connection layer (asyncpg + connection pool)
- [ ] 4 tools core: `boot_session`, `remember`, `save_memory`, `end_session`
- [ ] Read cache básico (LRU + TTL, sin LISTEN/NOTIFY)
- [ ] CLI: `olinkb init`, `olinkb serve`
- [ ] Búsqueda keyword con pg_trgm
- [ ] Write Guard básico (SHA256 dedup)
- [ ] Tests con testcontainers
- [ ] docker-compose para dev local

**Entregable**: Un dev puede guardar y buscar memorias. Sin equipo, sin permisos, sin embeddings.

#### Fase 2: Team (2-3 semanas)
- [ ] `team_members` table + CLI: `olinkb add-member`
- [ ] RLS policies
- [ ] Permission enforcement en Write Guard
- [ ] LISTEN/NOTIFY para cache invalidation
- [ ] `team_digest`, `list_conventions`
- [ ] `update_memory`, `forget` con audit log
- [ ] Namespaces: `personal://`, `project://`, `team://`
- [ ] `.instructions.md` template con boot protocol

**Entregable**: Un equipo puede compartir memoria con permisos reales.

#### Fase 3: Intelligence (3-4 semanas)
- [ ] pgvector embeddings (async computation)
- [ ] Hybrid search (keyword + semantic)
- [ ] Intent-aware retrieval pipeline
- [ ] `consolidate` (LLM-based semantic merge)
- [ ] Forgetting engine (decay + TTL + consolidation)
- [ ] `link_memories`, `suggest_links`
- [ ] `find_contradictions`
- [ ] `memory_analytics`

**Entregable**: La memoria se vuelve inteligente — busca con intención, se auto-limpia, detecta contradicciones.

#### Fase 4: Scale (2-3 semanas)
- [ ] `org://` namespace + multi-team
- [ ] `propose_convention` workflow (governance)
- [ ] `search_by_author` para handoffs
- [ ] Connection pooling optimizado (PgBouncer)
- [ ] Bulk import/export (JSON/YAML)
- [ ] Métricas Prometheus/OpenTelemetry
- [ ] Documentación completa

**Entregable**: Listo para organizaciones con múltiples equipos.

---

## Parte 4: Comparación v1 vs v2

### 4.1 Tabla Comparativa Directa

| Aspecto | v1 (SQLite) | v2 (PostgreSQL) | Ventaja |
|---------|-------------|-----------------|---------|
| **Storage** | SQLite local | PostgreSQL central + read cache | v2: un equipo de 50 devs funciona sin lock contention |
| **Concurrencia** | WAL mode (1 writer) | MVCC (N writers) | v2: escrituras concurrentes nativas |
| **Búsqueda keyword** | FTS5 | pg_trgm (fuzzy) + GIN | v2: fuzzy matching sin setup adicional |
| **Búsqueda semántica** | Opcional (futura) | pgvector nativo (HNSW) | v2: embeddings integrados desde fase 3 |
| **Retrieval** | FTS5 → resultados | Intent-aware pipeline (4 fases) | v2: entiende qué tipo de pregunta es |
| **Dedup** | SHA256 | SHA256 + clustering semántico LLM | v2: detecta duplicados con palabras diferentes |
| **Permisos** | Namespace string check | RLS PostgreSQL + RBAC | v2: permisos reales a nivel de DB |
| **Roles** | No hay | admin / lead / developer / viewer | v2: governance real |
| **Sharing** | SQLite file + sync (vago) | PostgreSQL central (nativo) | v2: compartir sin sync |
| **Real-time** | No | LISTEN/NOTIFY → cache invalidation | v2: otros devs ven cambios en segundos |
| **Modo offline** | Completo (local-first) | Parcial (read cache + working memory) | v1: funciona sin red |
| **Latencia lectura** | <1ms (SQLite) | <1ms (cache hit) / ~10ms (cache miss) | Empate en práctica |
| **Latencia escritura** | <1ms (SQLite) | ~5-20ms (red + PostgreSQL) | v1: más rápido |
| **Setup** | `pip install` + file | PostgreSQL + pip install + config | v1: más simple |
| **Dependencias** | 3 (fastmcp, aiosqlite, pydantic) | 4 (fastmcp, asyncpg, pydantic, pgvector) | v1: más ligero |
| **Olvidación** | vitality_score (sin impl.) | Forgetting engine completo | v2: implementación real |
| **Grafo de relaciones** | No | `memory_links` table + link_type | v2: memorias conectadas |
| **Audit trail** | Snapshots | `audit_log` inmutable + temporal | v2: auditoría completa |
| **Onboarding** | Manual | boot_session carga contexto del equipo | v2: automatizado |
| **Multi-proyecto** | No | `project://`, `org://` namespaces | v2: múltiples proyectos y equipos |
| **Working memory** | No distingue | `session://*` separado de long-term | v2: separación clara |
| **Analytics** | No | `memory_analytics` tool | v2: visibilidad del uso |

### 4.2 Pros y Contras Resumidos

#### v1: SQLite Local-First

**Pros**:
- ✅ Setup en 2 minutos (`pip install olinkb`)
- ✅ Zero infraestructura (no requiere servidor)
- ✅ Funciona completamente offline
- ✅ Latencia mínima (<1ms todo)
- ✅ Suficiente para 1 dev o equipo de 2-3 personas
- ✅ No hay costos de hosting

**Contras**:
- ❌ No escala más allá de ~5 devs (lock contention)
- ❌ Compartir requiere workarounds (Git sync, file copy)
- ❌ No hay permisos reales
- ❌ Retrieval primitivo (solo keyword)
- ❌ No hay mecanismo de olvido real
- ❌ No hay audit trail confiable
- ❌ No soporta equipos reales en producción

#### v2: PostgreSQL Central + Cache

**Pros**:
- ✅ Escala de 1 dev a 100+ devs sin cambios
- ✅ Compartición nativa — una DB, una verdad
- ✅ Permisos reales con RLS (no es solo convención, es enforcement)
- ✅ Búsqueda híbrida (keyword + semántica) desde el core
- ✅ Forgetting engine automático (la memoria se auto-limpia)
- ✅ Audit trail inmutable (compliance, accountability)
- ✅ Grafo de relaciones (memorias conectadas, no aisladas)
- ✅ Onboarding automático (nuevo dev = contexto inmediato)
- ✅ Real-time cache invalidation (LISTEN/NOTIFY)
- ✅ `org://` permite compartir entre proyectos

**Contras**:
- ❌ Requiere PostgreSQL server (infra, hosting, backup)
- ❌ Escrituras offline no funcionan (necesita conectividad)
- ❌ Setup más complejo (DB + roles + config)
- ❌ Latencia de escritura mayor (~10-20ms vs <1ms)
- ❌ Más código que mantener (cache, RLS, retrieval pipeline)
- ❌ Dependencia en PostgreSQL extensions (pgvector, pg_trgm)

### 4.3 ¿Cuándo usar cuál?

| Escenario | Recomendación |
|-----------|---------------|
| Dev solo / hobby project | v1 (SQLite) |
| Equipo de 2-3 devs, misma máquina | v1 con shared SQLite |
| Equipo de 3-10 devs | **v2** — PostgreSQL ya justifica el setup |
| Equipo de 10-50 devs | **v2** — imposible con SQLite |
| Organización multi-equipo | **v2** con `org://` namespace |
| Equipo sin infra propia | v2 con PostgreSQL managed (Supabase, Railway, Neon) |
| Equipo con reqs de privacidad | v2 self-hosted con RLS |

---

## Parte 5: Lo que Tomamos de Cada Repo (v2 actualizado)

| Repo | Lo que se adopta en v2 | Cómo se mejora en v2 |
|------|----------------------|---------------------|
| **nocturne_memory** | URI namespaces, Write Guard, soberanía de memoria | + `org://` + `session://`, RLS enforcement real, RBAC |
| **LycheeMem** | Memory types (7+3 nuevos), intent-aware retrieval pipeline | + integrado en PostgreSQL functions, sin LanceDB separado |
| **everything-claude-code** | Session lifecycle hooks, boot protocol | + session table en PostgreSQL, working memory explícita |
| **TeleMem** | SHA256 dedup, clustering semántico | + consolidator con LLM-based merge + superseded_by chain |
| **mcp-mem0** | MCP server template, PostgreSQL como storage | + read cache + LISTEN/NOTIFY + RLS (no solo user-scoped) |
| **DeerFlow** | Fact dedup, sub-agent isolation | + memoria compartida entre agentes del mismo equipo |
| **PraisonAI** | Simplicidad de API (`save_memory` minimal) | + pero con permisos y namespaces under the hood |
| **Awesome-AI-Memory** | Forgetting policies (4 tipos), benchmarks, taxonomía | + implementación real en Forgetting Engine |
| **GPTCache** | Concepto multi-backend (12+ stores) | + pero opinado: PostgreSQL only, sin abstracción innecesaria |
| **nocturne_memory** | Glossary auto-linking (Aho-Corasick) | + en `engine/linker.py` como auto-linking de memorias |

---

## Parte 6: Innovaciones Únicas de OlinkB v2

Cosas que **ningún** repo de los 20 analizados implementa:

1. **Permission governance en memoria**: Workflows de `propose_convention` → approval por lead → `active`. La memoria tiene gobierno, no es un free-for-all.

2. **Onboarding automático**: Un dev nuevo hace `boot_session` y recibe toda la historia relevante del equipo. Resuelve la transferencia de conocimiento tácito.

3. **Memory graph** (`memory_links`): Las memorias no son documentos aislados — se enlazan con relaciones tipadas (`supersedes`, `contradicts`, `implements`, `derived_from`, `references`). Esto permite seguir la evolución de decisiones.

4. **Forgetting engine con consolidation**: No solo decay — merge activo de memorias similares via LLM, creando memorias más ricas y eliminando redundancia.

5. **Intent-aware retrieval nativo en PostgreSQL**: El pipeline de retrieval no es un servicio externo — las funciones SQL de PostgreSQL hacen hybrid search con reranking, todo en una query.

6. **Analytics de uso**: ¿Qué memorias se acceden más? ¿Qué tipo de memoria guarda más cada dev? ¿Qué convenciones se ignoran? Data para mejorar el sistema y el equipo.

7. **Cross-project memory** (`org://`): Un patrón descubierto en un proyecto se eleva a `org://patterns/` y está disponible para todos los proyectos de la organización.

8. **Contradiction detection activa**: No espera a que alguien note la inconsistencia — `find_contradictions` cruza memorias y detecta conflictos automáticamente.

---

## Parte 7: Quick Start v2

```bash
# === Opción 1: PostgreSQL managed (más rápido) ===

# 1. Crear PostgreSQL en Supabase/Railway/Neon (free tier suficiente para empezar)
# 2. Copiar connection string

# 3. Instalar OlinkB
pip install olinkb

# 4. Inicializar DB + crear admin
olinkb init \
  --pg-url "postgresql://user:pass@host:5432/olinkb" \
  --team "mi-equipo" \
  --admin "$USER"

# 5. Agregar miembros
olinkb add-member --username "maria" --role developer
olinkb add-member --username "carlos" --role lead

# 6. Copiar config al repo del equipo
olinkb template mcp > .vscode/mcp.json
olinkb template instructions > .github/copilot-instructions.md

# 7. Commit al repo — todos los devs configurados al hacer pull
git add .vscode/mcp.json .github/copilot-instructions.md
git commit -m "feat: add OlinkB team memory"

# 8. Abrir VSCode — Copilot ya tiene acceso a la memoria del equipo


# === Opción 2: Self-hosted (docker-compose) ===

# 1. Clonar repo
git clone https://github.com/equipo/olinkb && cd olinkb

# 2. Levantar PostgreSQL + OlinkB
docker-compose up -d

# 3. Mismo flujo desde paso 4
olinkb init --pg-url "postgresql://olinkb:olinkb@localhost:5432/olinkb" ...
```

---

*Documento generado como evolución del plan v1 tras re-análisis profundo de 20 repositorios.*
*Siguiente paso: validar con el equipo y comenzar Fase 1 (Foundation).*
