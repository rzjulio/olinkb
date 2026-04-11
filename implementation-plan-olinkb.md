# Plan de Implementación: OlinkB — Sistema de Memoria Compartida para Equipos

> "One Link to the Brain" — Memoria persistente compartida para desarrolladores con GitHub Copilot
> Versión: 1.0 — Abril 2026

---

## Resumen Ejecutivo

Construir un servidor MCP ligero que actúe como memoria de largo plazo compartida para un equipo de desarrolladores. GitHub Copilot lee y escribe en esta memoria automáticamente al inicio y fin de cada sesión. El sistema es local-first, rápido (<10ms para reads), seguro, y no genera conflictos.

**Inspirado en**: nocturne_memory (arquitectura y filosofía URI), LycheeMem (tipos de memoria), everything-claude-code (hooks de sesión).

---

## 1. Principios de Diseño

| Principio | Descripción |
|-----------|-------------|
| **MCP-nativo** | Interfaz via Model Context Protocol — compatible con Copilot, Claude Code, Cursor, etc. |
| **Local-first** | SQLite como storage primario. Funciona sin internet. |
| **Extremely fast** | FTS5 para retrieval, sin embeddings obligatorios. <10ms por query. |
| **No-conflicts** | Write serialization via write lanes. Un writer a la vez por recurso. |
| **Auditable** | Cada escritura genera snapshot. Rollback disponible. |
| **Team-aware** | Namespace `personal://` vs `team://` — aislamiento natural. |
| **Zero dependencies pesadas** | Python stdlib + FastMCP + SQLite. No Docker, no Redis, no vector DB obligatorio. |

---

## 2. Arquitectura

```
┌────────────────────────────────────────────────────────────────┐
│                    GitHub Copilot (VSCode)                      │
│                                                                │
│  ┌─────────────────┐                    ┌──────────────────┐   │
│  │ .instructions.md │ ← boot protocol → │  MCP Tools        │   │
│  │ (session hooks)  │                    │  (olinkb server)  │   │
│  └─────────────────┘                    └────────┬─────────┘   │
└──────────────────────────────────────────────────┼─────────────┘
                                                   │ stdio
                                                   ▼
┌────────────────────────────────────────────────────────────────┐
│                    OlinkB MCP Server                           │
│                                                                │
│  ┌──────────┐  ┌───────────┐  ┌────────────────────────────┐  │
│  │ Router   │→ │Write Guard│→ │   SQLite DB                │  │
│  │ (intent  │  │(validate, │  │   ├── memories (FTS5)      │  │
│  │  detect) │  │ serialize)│  │   ├── snapshots            │  │
│  └──────────┘  └───────────┘  │   ├── sessions             │  │
│                               │   └── metadata             │  │
│  ┌──────────────────────┐     └────────────────────────────┘  │
│  │ Optional: Embeddings │ ← lazy init, no blocker             │
│  │ (nomic-embed / OAI)  │                                     │
│  └──────────────────────┘                                     │
└────────────────────────────────────────────────────────────────┘
```

### 2.1 Componentes

| Componente | Responsabilidad | Tecnología |
|-----------|----------------|-----------|
| **MCP Server** | Exposición de tools via stdio | `fastmcp` (Python) |
| **Router** | Detectar intent de búsqueda (factual/exploratory/temporal) | Reglas simples, sin LLM |
| **Write Guard** | Validar escrituras, prevenir duplicados, serializar | Python `asyncio.Lock` + SHA256 |
| **SQLite DB** | Almacenamiento persistente con FTS5 | `aiosqlite` + SQLAlchemy 2.0 |
| **Snapshot Engine** | Captura pre-write para rollback | JSON diff almacenado en tabla |
| **Embeddings** (opt.) | Semantic search cuando FTS5 no es suficiente | nomic-embed-text local o OpenAI |

### 2.2 Schema de Base de Datos

```sql
-- Tabla principal de memorias
CREATE TABLE memories (
    id TEXT PRIMARY KEY,           -- UUID
    uri TEXT NOT NULL UNIQUE,      -- e.g., team://conventions/naming
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,     -- fact | preference | event | constraint | procedure | failure_pattern
    scope TEXT NOT NULL DEFAULT 'personal',  -- personal | team | project
    author TEXT NOT NULL,          -- username del desarrollador
    tags TEXT,                     -- comma-separated
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    vitality_score REAL DEFAULT 1.0,
    retrieval_count INTEGER DEFAULT 0,
    content_hash TEXT NOT NULL     -- SHA256 para dedup
);

-- FTS5 para búsqueda full-text ultrarrápida
CREATE VIRTUAL TABLE memories_fts USING fts5(
    title, content, tags, uri,
    content='memories',
    content_rowid='rowid'
);

-- Snapshots para auditoría y rollback
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    content_before TEXT,
    content_after TEXT NOT NULL,
    operation TEXT NOT NULL,       -- create | update | delete
    author TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id)
);

-- Sesiones de trabajo
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    author TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary TEXT,
    memories_read INTEGER DEFAULT 0,
    memories_written INTEGER DEFAULT 0
);

-- Aliases para memorias (búsqueda by nickname)
CREATE TABLE aliases (
    alias TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id)
);
```

---

## 3. MCP Tools (API del Servidor)

### 3.1 Tools Esenciales (MVP)

```python
@mcp.tool()
async def boot_session(author: str) -> dict:
    """
    Iniciar sesión de trabajo. Carga memorias core:
    - team://conventions/* (convenciones del equipo)
    - personal://{author}/context (contexto previo del dev)
    - system://boot (configuración de arranque)
    Retorna resumen compacto para inyectar en contexto.
    """

@mcp.tool()
async def remember(query: str, scope: str = "all", limit: int = 5) -> list:
    """
    Buscar memorias relevantes. Usa FTS5 por defecto.
    scope: 'personal' | 'team' | 'project' | 'all'
    Retorna memorias rankeadas por relevancia + vitality.
    """

@mcp.tool()
async def save_memory(
    uri: str,
    title: str,
    content: str,
    memory_type: str,
    scope: str = "personal",
    tags: str = ""
) -> dict:
    """
    Guardar una nueva memoria o actualizar si URI ya existe (upsert).
    Write Guard valida antes de escribir.
    Genera snapshot automáticamente.
    """

@mcp.tool()
async def end_session(author: str, summary: str) -> dict:
    """
    Cerrar sesión de trabajo. Guarda resumen.
    Registra estadísticas (memorias leídas/escritas).
    """

@mcp.tool()
async def forget(uri: str, reason: str) -> dict:
    """
    Marcar memoria como eliminada (soft-delete).
    Requiere razón para auditoría.
    Genera snapshot antes de eliminar.
    """
```

### 3.2 Tools de Mantenimiento (Post-MVP)

```python
@mcp.tool()
async def compact_context(author: str, max_tokens: int = 2000) -> str:
    """Comprimir memorias recientes en resumen denso."""

@mcp.tool()
async def search_semantic(query: str, limit: int = 5) -> list:
    """Búsqueda semántica con embeddings (requiere modelo configurado)."""

@mcp.tool()
async def rollback(memory_id: str, snapshot_id: str) -> dict:
    """Restaurar memoria a un estado anterior."""

@mcp.tool()
async def team_digest(days: int = 7) -> str:
    """Resumen de memorias del equipo en los últimos N días."""

@mcp.tool()
async def add_alias(alias: str, uri: str) -> dict:
    """Agregar alias para una memoria (búsqueda por nickname)."""
```

---

## 4. Protocolo de Sesión (Hooks en .instructions.md)

### 4.1 Boot Protocol

Cada desarrollador tiene un `.instructions.md` que instruye a Copilot:

```markdown
## Memory Protocol

Al inicio de cada sesión:
1. Llama `boot_session(author: "{username}")` para cargar contexto
2. El resultado contiene convenciones del equipo y tu contexto previo
3. Sigue las convenciones cargadas durante toda la sesión

Al hacer descubrimientos, decisiones, o corregir bugs:
- Llama `save_memory` inmediatamente con:
  - uri: `personal://{username}/discoveries/{topic}` o `team://decisions/{topic}`
  - memory_type: fact | decision | bugfix | procedure | failure_pattern
  - scope: team (si aplica a todos) o personal (si es tuyo)

Antes de cerrar la sesión:
1. Llama `end_session(author: "{username}", summary: "...")`
2. El summary debe incluir: qué se hizo, qué se descubrió, qué falta
```

### 4.2 URI Conventions

```
# Memorias del equipo
team://conventions/naming         → Convenciones de naming
team://conventions/testing        → Prácticas de testing
team://decisions/auth-migration   → Decisiones arquitectónicas
team://patterns/error-handling    → Patrones establecidos
team://onboarding/setup           → Setup guide para nuevos devs

# Memorias personales
personal://{user}/context         → Contexto de sesión anterior
personal://{user}/discoveries/*   → Descubrimientos personales
personal://{user}/preferences     → Preferencias de código

# Memorias de proyecto
project://architecture            → Arquitectura del proyecto
project://dependencies            → Decisiones de dependencias
project://known-issues            → Issues conocidos

# Sistema
system://boot                     → Config de arranque
system://audit                    → Log de auditoría
```

---

## 5. Seguridad

| Amenaza | Mitigación |
|---------|-----------|
| **Inyección en memorias** | Write Guard sanitiza contenido, SHA256 para integridad |
| **Acceso no autorizado** | Namespace isolation (`personal://` solo para el autor) |
| **Pérdida de datos** | Snapshots en cada escritura, backup SQLite trivial |
| **Race conditions** | Write lanes serializados con `asyncio.Lock` |
| **Prompt injection via memorias** | Memorias son data, no instrucciones. El boot carga solo URIs específicos |
| **Datos sensibles** | No almacenar secrets/tokens. Tag `sensitivity: high` para review |

---

## 6. Fases de Implementación

### Fase 1: MVP (1-2 semanas)

**Objetivo**: Un solo desarrollador usando memoria persistente con Copilot.

- [ ] Scaffold del proyecto Python (pyproject.toml, estructura)
- [ ] Schema SQLite con FTS5
- [ ] MCP server con `fastmcp` (stdio transport)
- [ ] 5 tools esenciales: `boot_session`, `remember`, `save_memory`, `end_session`, `forget`
- [ ] Write Guard básico (dedup por SHA256, serialización)
- [ ] Snapshot engine
- [ ] `.instructions.md` template con boot protocol
- [ ] Configuración MCP en VSCode (`mcp.json`)
- [ ] Tests unitarios

**Stack**: Python 3.12+, fastmcp, aiosqlite, pydantic

**Entregable**: `pip install olinkb` + config MCP = memoria persistente funcionando.

### Fase 2: Team Features (1-2 semanas)

**Objetivo**: Múltiples desarrolladores compartiendo memorias de equipo.

- [ ] Namespace isolation (personal vs team vs project)
- [ ] `team_digest` tool
- [ ] Vitality score con decay (half-life configurable)
- [ ] `compact_context` tool
- [ ] `rollback` tool
- [ ] CLI básico: `olinkb search`, `olinkb list`, `olinkb export`
- [ ] Sync mechanism: SQLite backup to shared location (git-ignored folder, S3, etc.)
- [ ] Documentación de onboarding

**Decisión**: Para equipos <10 devs, un SQLite compartido en red local o S3 sync es suficiente. Para más, migrar a PostgreSQL.

### Fase 3: Intelligence (2-4 semanas)

**Objetivo**: Retrieval más inteligente, memoria que se auto-organiza.

- [ ] Semantic search con embeddings opcionales (nomic-embed-text local)
- [ ] Intent-aware search (factual/exploratory/temporal/causal)
- [ ] Memory consolidation automática (merge memorias similares)
- [ ] Alias system
- [ ] Dashboard web simple (React, lectura-only)
- [ ] Métricas de uso (qué memorias se leen más, cuáles decaen)
- [ ] Benchmarking: hit ratio, latency, recall

### Fase 4: Enterprise (opcional)

- [ ] PostgreSQL backend para equipos grandes
- [ ] Auth (API key per developer)
- [ ] SSE transport para acceso remoto
- [ ] Embedding pipeline async (background worker)
- [ ] Integración con CI/CD (auto-save decisiones de deploy)

---

## 7. Estructura del Proyecto

```
olinkb/
├── pyproject.toml
├── README.md
├── src/
│   └── olinkb/
│       ├── __init__.py
│       ├── server.py          # MCP server entry point
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── session.py     # boot_session, end_session
│       │   ├── memory.py      # remember, save_memory, forget
│       │   └── maintenance.py # compact, rollback, digest, alias
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── sqlite.py      # SQLite + FTS5 backend
│       │   ├── schema.py      # Table definitions
│       │   └── snapshots.py   # Snapshot engine
│       ├── guards/
│       │   ├── __init__.py
│       │   └── write_guard.py # Validation, dedup, serialization
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── fts.py         # FTS5 search
│       │   ├── semantic.py    # Optional embeddings search
│       │   └── hybrid.py      # Combined search
│       └── config.py          # Settings via env vars
├── tests/
│   ├── test_tools.py
│   ├── test_storage.py
│   ├── test_guards.py
│   └── test_retrieval.py
└── templates/
    ├── instructions.md        # Template .instructions.md para devs
    └── mcp.json               # Template config para VSCode
```

---

## 8. Configuración para GitHub Copilot

### 8.1 mcp.json (en el proyecto o en ~/.vscode/)

```json
{
  "servers": {
    "olinkb": {
      "command": "python",
      "args": ["-m", "olinkb.server"],
      "env": {
        "OLINKB_DB_PATH": "~/.olinkb/memory.db",
        "OLINKB_AUTHOR": "${env:USER}",
        "OLINKB_TEAM": "mi-equipo"
      }
    }
  }
}
```

### 8.2 .instructions.md (en el repo del equipo)

```markdown
---
applyTo: "**"
---

## OlinkB Memory Protocol

You have access to a persistent team memory system via MCP tools.

### On Session Start
1. Call `boot_session(author: "${env:USER}")` to load team context
2. Review loaded conventions and follow them

### During Work
When you make a decision, fix a bug, discover something non-obvious, or establish a pattern:
- Call `save_memory` immediately
- Use `team://` scope for things that affect the whole team
- Use `personal://` scope for your own notes

### Before Ending
1. Call `end_session` with a summary of what was accomplished
```

---

## 9. Comparación con Alternativas

| Aspecto | OlinkB (plan) | Engram (actual) | mcp-mem0 |
|---------|--------------|-----------------|----------|
| Setup | `pip install` + mcp.json | In-process | Docker + Supabase |
| Storage | SQLite local | SQLite | PostgreSQL |
| Search | FTS5 (+ embeddings opt.) | FTS5 | Semantic only |
| Write Safety | Write Guard + snapshots | None | None |
| Team Support | Namespace isolation | Personal only | User-scoped |
| Dependencies | 3 (fastmcp, aiosqlite, pydantic) | 0 (stdlib) | 5+ (Supabase, etc.) |
| Latency | <10ms (FTS5) | <5ms | ~100ms (network) |
| MCP Native | ✅ | ❌ (custom protocol) | ✅ |

---

## 10. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| SQLite lock contention con múltiples devs | Media | Alto | WAL mode + write serialization + fallback retry |
| Memorias duplicadas acumulándose | Media | Medio | SHA256 dedup + vitality decay + periodic cleanup |
| Copilot ignora los tools MCP | Baja | Alto | .instructions.md explícito con protocolo de boot |
| Datos sensibles en memorias | Media | Alto | No guardar secrets, review tags, purge mechanism |
| Pérdida de SQLite file | Baja | Alto | Backup automático, litestream, git-tracked export |
| Over-engineering fase 1 | Alta | Medio | Scope estricto: solo 5 tools, solo FTS5, solo SQLite |

---

## 11. Métricas de Éxito

| Métrica | Objetivo MVP | Objetivo Fase 3 |
|---------|-------------|-----------------|
| Latencia de `remember` | <10ms | <50ms (hybrid) |
| Latencia de `boot_session` | <100ms | <200ms |
| Hit ratio (memorias útiles / totales retornadas) | >50% | >75% |
| Adopción del equipo | 1 dev | Todo el equipo |
| Memorias por semana | 10+ | 50+ |
| Rollback necesarios | 0 | <5% de writes |

---

## 12. Lo que Tomamos de Cada Repo

| Repo | Lo que Adoptamos |
|------|-----------------|
| **nocturne_memory** | URI graph routing (`team://`, `personal://`, `system://`), soberanía de memoria, Write Guard pattern, snapshots, MCP tools (7 tools) |
| **LycheeMem** | Tipos de MemoryRecord (fact, preference, event, constraint, procedure, failure_pattern) |
| **everything-claude-code** | Hook-based session lifecycle (boot → work → save → end) |
| **TeleMem** | SHA256 dedup, FAISS+JSON dual-write pattern (adaptado a FTS5+snapshots) |
| **mcp-mem0** | Template minimalista de MCP server como punto de partida |
| **DeerFlow** | Dedup de facts, sub-agent context isolation |
| **PraisonAI** | API minimal (`memory=True` simplicity goal) |
| **Awesome-AI-Memory** | Taxonomía de tipos de memoria, 4-layer architecture, benchmarks |
| **GPTCache** | Concepto de caché semántico (para optimización futura) |
| **OpenClaw-DeepReeder** | Content hash SHA256 para dedup, YAML frontmatter pattern |

---

## 13. Quick Start (Después de Fase 1)

```bash
# Instalar
pip install olinkb

# Inicializar DB
olinkb init --team "mi-equipo" --author "$USER"

# Agregar config MCP a VSCode
cp $(olinkb template mcp) .vscode/mcp.json

# Agregar instrucciones al repo
cp $(olinkb template instructions) .github/copilot-instructions.md

# Abrir VSCode — Copilot ya tiene acceso a la memoria
# Boot automático al iniciar sesión
```

---

*Documento generado a partir del análisis de 20 repositorios de memoria para IA.*
*Siguiente paso: scaffold del proyecto y comenzar Fase 1 del MVP.*
