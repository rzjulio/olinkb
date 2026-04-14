# Base de Conocimiento: Sistemas de Memoria para IA

> Síntesis de 20 repositorios analizados — Abril 2026
> Objetivo: Fundamentar el diseño de un sistema de memoria compartida para equipos de desarrollo con GitHub Copilot

---

## 1. Taxonomía de Sistemas Analizados

### 1.1 Frameworks de Orquestación (RAG/Agentes)

| Repo | Stars | Licencia | Rol Principal |
|------|-------|----------|--------------|
| **LangChain** | 133k | MIT | Orquestación de agentes, interfaz estándar para modelos/embeddings/vector stores |
| **LlamaIndex** | 48.5k | MIT | Framework centrado en documentos, indexación y retrieval |
| **Haystack** | 24.8k | Apache-2.0 | Pipelines de search+RAG para producción enterprise |
| **Quivr** | 39.1k | Apache-2.0 | "Second Brain" — RAG opinado, `Brain.from_files()` en 5 líneas |
| **AnythingLLM** | 58.1k | MIT | Workspace all-in-one, privacy-first, self-hosted |
| **Open WebUI** | 131k | Custom | Plataforma AI extensible con RAG local y auth enterprise |

**Lección clave**: Estos frameworks son demasiado pesados para memoria de equipo. Sirven como referencia para patrones de retrieval, pero no son la base correcta para un sistema ligero de memoria compartida.

### 1.2 Sistemas de Memoria Persistente para Agentes (CORE)

| Repo | Stars | Licencia | Innovación Principal |
|------|-------|----------|---------------------|
| **nocturne_memory** | 939 | MIT | URI Graph Routing, memoria soberana de primera persona, glossary auto-linking |
| **LycheeMem** | 218 | Apache-2.0 | 3 memory stores (working/semantic/procedural), 4-module pipeline, académicamente riguroso |
| **mcp-mem0** | 670 | MIT | Template MCP mínimo sobre Mem0, 3 tools |
| **DeerFlow** | 60.5k | MIT | Long-term memory con deduplicación, sub-agentes con contexto aislado |
| **PraisonAI** | 6.9k | MIT | `memory=True` flag, persistencia a 20+ DBs, CLI para memoria |

**Lección clave**: nocturne_memory es el más relevante directamente (filosofía URI, soberanía de memoria). LycheeMem aporta el retrieval más sofisticado académicamente.

### 1.3 Sistemas de Rendimiento y Caché

| Repo | Stars | Licencia | Rol |
|------|-------|----------|-----|
| **TeleMem** | 456 | Apache-2.0 | Drop-in replacement de Mem0, 86.33% accuracy, clustering semántico con LLM |
| **GPTCache** | 8k | MIT | Caché semántico para queries LLM, reduce costos 10× y latencia 100× |
| **Pathway** | 63.5k | BSL 1.1 | ETL en tiempo real, mantiene índices RAG sincronizados |

**Lección clave**: TeleMem demuestra que el dedup semántico con LLM es superior al vector similarity simple. GPTCache aporta el concepto de caché semántico.

### 1.4 Sistemas Especializados

| Repo | Stars | Licencia | Rol |
|------|-------|----------|-----|
| **everything-claude-code** | 151k | MIT | Hooks de persistencia de sesión, 47 agentes, compactación estratégica |
| **Aetherius** | 313 | Custom | Simulacra de memoria humana (implícita/explícita/episódica/flashbulb) |
| **KAG** | 8.7k | Apache-2.0 | Knowledge Augmented Generation con grafos de conocimiento |
| **OpenClaw-DeepReeder** | 222 | MIT | Gateway de ingestión de contenido web → Markdown → memoria |

### 1.5 Meta-Recursos

| Repo | Stars | Licencia | Rol |
|------|-------|----------|-----|
| **Awesome-AI-Memory** | 710 | Apache-2.0 | Taxonomía académica completa, 30+ sistemas listados, benchmarks |

---

## 2. Patrones Arquitectónicos Clave

### 2.1 Protocolo MCP (Model Context Protocol)

**Adoptado por**: nocturne_memory, LycheeMem, mcp-mem0, KAG, DeerFlow, PraisonAI, AnythingLLM

MCP es el estándar emergente de facto para comunicación agente↔memoria. Permite:
- Interfaz universal independiente del modelo LLM ("One Soul, Any Engine")
- Tools estandarizados que cualquier harness puede invocar
- Transporte via stdio o SSE (Server-Sent Events)

**Tools MCP típicos** (7 en nocturne_memory):
```
read_memory, create_memory, update_memory, delete_memory,
add_alias, manage_triggers, search_memory
```

**Implicación para nosotros**: MCP es el protocolo correcto. GitHub Copilot soporta MCP tools.

### 2.2 Almacenamiento: SQLite como Base

**Usado por**: nocturne_memory, LycheeMem, everything-claude-code, GPTCache, PraisonAI

Por qué SQLite domina:
- Zero-config, archivo único, no requiere servidor
- FTS5 para búsqueda full-text nativa
- WAL mode para lecturas concurrentes
- Se puede replicar/backupear como archivo
- Suficiente para equipos de hasta ~50 desarrolladores

**LycheeMem** combina SQLite FTS5 + LanceDB vector index — el mejor combo descubierto.

**GPTCache** soporta 12+ backends de storage (SQLite, PostgreSQL, MySQL, Redis, MongoDB, DynamoDB, etc.) pero SQLite es el default.

### 2.3 Organización de Memoria: URI Jerárquico

**Originado en**: nocturne_memory

```
core://agent/identity          → Identidad del agente
project://architecture         → Decisiones arquitectónicas
system://boot                  → Carga automática al iniciar
system://index                 → Índice del sistema
user://preferences/rzjulio     → Preferencias del usuario
team://conventions/naming      → Convenciones del equipo
```

**Por qué funciona**: El path IS semantics — no necesitas vector search para navegar la estructura, el URI ya indica el contexto.

### 2.4 Retrieval: Híbrido con Degradación Graceful

**Mejor implementación**: LycheeMem (4-module pipeline)

**Patrón general de retrieval híbrido**:
- Keyword search (FTS5)
- Semantic search (embeddings)
- Hybrid search (ambos + reranking)
- Si embeddings fallan → degrada a keyword con `degrade_reasons` reportados

**LycheeMem** (más sofisticado):
1. Compact Semantic Encoding → typed extraction → decontextualization
2. Record Fusion + Conflict Update + Hierarchical Consolidation
3. Action-Aware Hierarchical Retrieval → composite-level relevance → tree expansion
4. Candidate Aggregation + Context Enrichment

**Intent-Aware Search** (LycheeMem):
- 4 categorías: factual, exploratory, temporal, causal
- Cada intent → estrategia de retrieval diferente

### 2.5 Seguridad de Escritura: Write Guard Pattern

**Patrón propuesto por**: nocturne_memory, refinado como concepto general

Pipeline de escritura auditible:
```
Request → Write Guard (pre-check) → Write Lane (serializado) → SQLite → Snapshot
```

- Write Guard: valida antes de escribir
- Write Lane: serializa escrituras para evitar race conditions
- Snapshots: permiten rollback completo
- SQLite lock retry: manejo transient de locks

### 2.6 Ciclo de Vida de Sesión

**Patrón consolidado** (everything-claude-code + nocturne_memory):

```
1. Boot     → system://boot carga memorias core (identidad, contexto)
2. Recall   → Buscar memorias relevantes al task actual
3. Work     → El agente trabaja con contexto enriquecido
4. Write    → Guardar descubrimientos, decisiones, bugs corregidos
5. Compact  → Consolidar contexto antes de cierre
6. Recover  → En caso de compactación o crash, recuperar desde snapshots
```

### 2.7 Tipos de Memoria (Taxonomía Consolidada)

De Awesome-AI-Memory + Aetherius + LycheeMem:

| Tipo | Descripción | Persistencia | Ejemplo |
|------|-------------|-------------|---------|
| **Working Memory** | Contexto activo de la sesión | Sesión | "Estoy refactorizando el módulo auth" |
| **Semantic Memory** | Hechos, preferencias, procedimientos | Permanente | "El proyecto usa TypeScript strict mode" |
| **Episodic Memory** | Eventos específicos timestamped | Permanente | "El 15/04 migramos de Redux a Zustand" |
| **Procedural Memory** | How-to knowledge reutilizable | Permanente | "Para deployar: `npm run build && vercel`" |
| **Flashbulb Memory** | Eventos significativos/emocionales | Permanente | "Descubrimos memory leak que causaba OOM en prod" |

**LycheeMem** define 7 MemoryRecord types: `fact, preference, event, constraint, procedure, failure_pattern, tool_affordance`

### 2.8 Deduplicación y Conflictos

| Repo | Estrategia |
|------|-----------|
| **TeleMem** | Clustering semántico con LLM — merge de memorias similares via LLM call |
| **LycheeMem** | SHA256 hash para dedup exacto + CompositeRecord hierarchy |
| **DeerFlow** | Deduplicación de facts en long-term memory |
| **nocturne_memory** | Glossary auto-hyperlinking con Aho-Corasick (memory network auto-weaves) |

### 2.9 Observabilidad y Auditoría

**TeleMem**:
- FAISS + JSON dual-write → retrieval rápido + auditoría humana legible
- Metadata con timestamp, round_index, character

### 2.10 Ingestión de Contenido

**OpenClaw-DeepReeder** aporta el patrón:
- URL → Router (Twitter/Reddit/YouTube/Generic) → Parser → Clean Markdown → Memory
- YAML frontmatter con `content_hash: sha256:...` para dedup
- Zero API keys para fuentes principales

---

## 3. Arquitectura de Referencia Propuesta

Síntesis de los mejores patrones de nocturne_memory (FastAPI + SQLite), LycheeMem (retrieval pipeline) y everything-claude-code (session hooks):

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

**Basado en**: nocturne_memory (FastAPI + SQLite + URI routing) + LycheeMem (retrieval pipeline) + everything-claude-code (session hooks)

**4 Deployment Profiles**:
- **A**: Pure local (SQLite only, no embeddings)
- **B**: Local + embeddings (SQLite + local model)
- **C**: Local + cloud embeddings (SQLite + OpenAI)
- **D**: Cloud-connected (PostgreSQL + cloud embeddings)

---

## 4. Conceptos Académicos Relevantes (de Awesome-AI-Memory)

### 4.1 Cuatro Capas del Sistema de Memoria
1. **Storage Layer**: Vector DBs, graph DBs, almacenamiento híbrido
2. **Processing Layer**: Embedding models, summarization, segmenters
3. **Retrieval Layer**: Multi-stage retrievers, reranking, context injectors
4. **Control Layer**: Priorización, forgetting controllers, consistency coordinators

### 4.2 Operaciones Atómicas de Memoria
- **Writing**: Convertir contenido en vectores + almacenar
- **Retrieval**: Generar query → obtener Top-K memorias relevantes
- **Updating**: Encontrar memorias similares → reemplazar o enriquecer
- **Deletion**: Eliminar por instrucción o política (privacy/expiration)
- **Compression**: Merge de memorias relacionadas en resúmenes

### 4.3 Clasificación por Alcance de Compartición
- **Personal Memory**: Un solo usuario
- **Team Memory**: Espacios colaborativos
- **Public Memory**: Knowledge bases compartidas

### 4.4 Mecanismos de Olvido
- **Selective Forgetting**: Machine unlearning de información específica
- **Privacy-Driven**: Auto-eliminación de PII
- **Memory Decay**: Reducción de prioridad por inactividad (configurable, e.g. half-life 30 días)
- **Conflict-Driven**: Actualizar/descartar memorias contradichas por nueva evidencia

### 4.5 Benchmarks de Evaluación
- **LOCOMO, LONGMEMEVAL**: Long-term memory evaluation
- **MemBench, Minerva**: Memory mechanism evaluation
- **MemoryAgentBench**: Comprehensive agent memory evaluation
- **HaluMem**: Memory hallucination detection

---

## 5. Decisiones de Diseño Críticas

### 5.1 ¿Vector RAG o Memory System?

nocturne_memory lo articuló mejor: "NOT another RAG system"

**Problemas de Vector RAG puro**:
- Semantic shredding: pierde contexto al chunk-ear documentos
- Read-only: no permite al agente escribir/actualizar su propia memoria
- Trigger blindness: no sabe CUÁNDO una memoria es relevante
- Memory islands: memorias aisladas sin conexiones entre sí
- No identity: no mantiene un "yo" persistente

**Solución**: Sistema de memoria soberana donde el agente decide qué recordar.

### 5.2 ¿Dónde almacenar para un equipo?

| Opción | Pros | Contras | Veredicto |
|--------|------|---------|-----------|
| SQLite local por dev | Rápido, zero-config | No compartido | ✅ Para memoria personal |
| SQLite + sync (Git/S3) | Compartible, auditable | Merge conflicts | ⚠️ Viable con write serialization |
| PostgreSQL central | Multi-user nativo | Requiere servidor | ✅ Para memoria compartida de equipo |
| SQLite + Litestream | Replicación continua, zero-config | Solo 1 writer | ⚠️ Suficiente para equipos pequeños |

**Recomendación**: Arquitectura de 2 niveles:
1. SQLite local para memoria personal del desarrollador (rápido, offline)
2. PostgreSQL compartido para memoria del equipo (convenciones, decisiones, patterns)

### 5.3 ¿Qué embeddings usar?

| Opción | Latencia | Costo | Calidad |
|--------|----------|-------|---------|
| text-embedding-3-small (OpenAI) | ~50ms | $0.02/1M tokens | Buena |
| nomic-embed-text (local) | ~10ms | Gratis | Buena |
| Sin embeddings (FTS5 only) | ~1ms | Gratis | Suficiente para keyword |

**Recomendación**: Empezar con FTS5 only (Profile A — solo local), agregar embeddings como mejora incremental.

---

## 6. Sistemas Existentes Descartados para Nuestro Caso

| Sistema | Razón de Descarte |
|---------|------------------|
| LangChain/LlamaIndex/Haystack | Demasiado pesado, framework completo no necesario |
| Quivr | Inactivo (~10 meses sin commits) |
| Open WebUI | Orientado a UI de chat, no a memoria de agentes |
| Pathway | BSL 1.1 (restricciones comerciales), orientado a streaming ETL |
| KAG | Enfocado a knowledge graphs para QA, no a memoria de agentes |
| Aetherius | Stale (2 años sin commits), monolítico, requiere Qdrant |
| Memory-Palace | Proyecto con poca tracción real (266 stars), documentación ambiciosa pero sin evidencia de producción verificable |
| GPTCache | Cache, no memoria — concepto útil pero problema diferente |
| OpenClaw-DeepReeder | Ingestión, no memoria — podría integrarse como data source |

---

## 7. Ranking de Relevancia para Nuestro Objetivo

1. **nocturne_memory** ⭐⭐⭐⭐⭐ — Filosofía correcta (URI graph, soberanía de memoria), arquitectura FastAPI + SQLite directamente aplicable
2. **LycheeMem** ⭐⭐⭐⭐⭐ — Retrieval más sofisticado, tipos de memoria action-aware, pipeline académicamente riguroso
3. **everything-claude-code** ⭐⭐⭐⭐ — Hook patterns para lifecycle de sesión
4. **TeleMem** ⭐⭐⭐⭐ — Dedup semántico con LLM, benchmarks sólidos
5. **DeerFlow** ⭐⭐⭐ — Long-term memory con dedup, sub-agent patterns
6. **PraisonAI** ⭐⭐⭐ — API minimal (`memory=True`), buena persistencia
7. **mcp-mem0** ⭐⭐⭐ — Template MCP mínimo, buen punto de partida
8. **Awesome-AI-Memory** ⭐⭐⭐ — Taxonomía académica para fundamentar decisiones
9. **GPTCache** ⭐⭐ — Concepto de caché semántico aplicable como optimización
