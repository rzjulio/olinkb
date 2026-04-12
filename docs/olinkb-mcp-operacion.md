# OlinKB — Operación MCP en VS Code

## Propósito
Este documento describe cómo debe funcionar OlinKB dentro de VS Code para comportarse como Engram: instalado localmente, registrado como servidor MCP por `stdio`, y llamado automáticamente por el agente cuando el prompt realmente requiere memoria.

La idea central no es que OlinKB esté "haciendo polling" ni corriendo como daemon permanente, sino que esté siempre disponible y que el cliente MCP lo invoque bajo demanda cuando la conversación necesite contexto, recuperación de memoria o persistencia de hallazgos.

## Modelo Operativo Deseado
OlinKB debe operar en tres capas:

1. **Disponibilidad**
  OlinKB existe como comando local instalable, por ejemplo `olinkb`.

2. **Integración MCP**
   VS Code lo registra como servidor MCP `stdio` en `mcp.json`.

3. **Uso automático guiado por instrucciones**
   El agente decide usar sus tools cuando el prompt lo amerita, siguiendo un protocolo explícito del repositorio.

## Qué significa "funcionar como Engram"
Funcionar como Engram significa esto:

- OlinKB está instalado como binario o CLI local.
- VS Code sabe cómo levantarlo como servidor MCP.
- El cliente lo arranca bajo demanda.
- El modelo invoca sus tools cuando necesita memoria.
- El usuario no tiene que escribir comandos manuales para usarlo.

No significa necesariamente que OlinKB tenga que vivir como proceso siempre activo en segundo plano.

## Registro en VS Code
La integración esperada es mediante un registro MCP similar a este:

```json
{
  "servers": {
    "olinkb": {
      "command": "olinkb",
      "args": ["serve"],
      "type": "stdio",
      "env": {
        "OLINKB_PG_URL": "postgresql://usuario:password@host:5432/olinkb",
        "OLINKB_TEAM": "mi-equipo",
        "OLINKB_USER": "${env:USER}"
      }
    }
  }
}
```

También podría usar un entrypoint más directo:

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

La decisión final entre `serve` y `mcp` depende del diseño del CLI, pero el comportamiento esperado es el mismo: VS Code levanta el proceso y se comunica con él por `stdin/stdout`.

## Cómo lo llamaría VS Code
Cuando el usuario manda un prompt, el flujo esperado es este:

```mermaid
sequenceDiagram
    participant User as Usuario
    participant IDE as VS Code + Copilot
    participant MCP as OlinKB MCP Local
    participant PG as PostgreSQL

    User->>IDE: Envía prompt
    IDE->>IDE: El agente evalúa si necesita memoria
    alt requiere memoria
        IDE->>MCP: Llama tool MCP
        MCP->>PG: Lee o escribe memoria compartida
        PG-->>MCP: Resultado
        MCP-->>IDE: Respuesta de la tool
    else no requiere memoria
        IDE->>IDE: Responde sin usar OlinKB
    end
    IDE-->>User: Respuesta final
```

## Qué significa "automático"
En este diseño, "automático" significa que el agente invoca OlinKB sin que el usuario lo pida explícitamente, siempre que el prompt parezca requerir memoria del equipo.

No significa:

- ejecutarlo por cada tecla,
- ejecutar todas las tools en todos los prompts,
- interceptar todos los mensajes con un proxy externo obligatorio.

Sí significa:

- `boot_session` al inicio de la sesión,
- `remember` cuando el prompt necesita contexto previo,
- `save_memory` cuando se descubre algo importante,
- `end_session` al cierre.

## Política de Invocación Recomendada

### 1. Inicio de sesión
En la primera interacción relevante de la sesión, el agente debe llamar:

```text
boot_session(author, team, project)
```

Esto sirve para:

- validar identidad,
- cargar `team://conventions/*`,
- cargar `project://*` relevante,
- cargar memoria personal útil,
- calentar el read cache.

### 2. Recuperación automática
Cuando el prompt pregunta por contexto, decisiones previas, convenciones, bugs conocidos o procedimientos, el agente debe llamar:

```text
remember(query)
```

Ejemplos donde sí debería dispararse:

- "¿cómo manejamos auth aquí?"
- "recuérdame cómo hacemos refresh tokens"
- "¿por qué usamos Result en vez de excepciones?"
- "¿ya habíamos resuelto este bug?"

Ejemplos donde probablemente no hace falta:

- "hola"
- "cámbiame este color"
- "qué hora es"
- preguntas triviales que solo requieren contexto local inmediato

### 3. Persistencia automática
Cuando durante la conversación se produce una decisión, convención, descubrimiento o bugfix, el agente debe llamar:

```text
save_memory(...)
```

Usando un `memory_type` compatible, por ejemplo `decision`, `convention`, `discovery`, `bugfix` o `procedure`.

Ejemplos:

- se descubre la causa raíz de un bug,
- se acuerda una nueva convención,
- se decide una restricción arquitectónica,
- se documenta un procedimiento reutilizable.

### 4. Cierre
Cuando la sesión termina o se completa un bloque relevante de trabajo, el agente debe llamar:

```text
end_session(summary)
```

## Flujo MCP Esperado por Tool

### `boot_session`
```mermaid
sequenceDiagram
    participant IDE as Cliente MCP
    participant MCP as OlinKB
    participant PG as PostgreSQL
    participant Cache as Read Cache

    IDE->>MCP: boot_session(author, team, project)
    MCP->>PG: validar identidad y cargar contexto
    PG-->>MCP: memorias relevantes
    MCP->>Cache: precargar entradas
    MCP-->>IDE: sesión lista
```

### `remember`
```mermaid
sequenceDiagram
    participant IDE as Cliente MCP
    participant MCP as OlinKB
    participant Cache as Read Cache
    participant PG as PostgreSQL

    IDE->>MCP: remember(query)
    MCP->>Cache: buscar en cache
    alt cache hit
        Cache-->>MCP: resultados
    else cache miss
        MCP->>PG: buscar memoria relevante
        PG-->>MCP: resultados
    end
    MCP-->>IDE: contexto recuperado
```

### `save_memory`
```mermaid
sequenceDiagram
    participant IDE as Cliente MCP
    participant MCP as OlinKB
    participant Guard as Write Guard
    participant PG as PostgreSQL
    participant Notify as LISTEN/NOTIFY

    IDE->>MCP: save_memory(...)
    MCP->>Guard: validar write
    Guard-->>MCP: permitido o propuesto
    MCP->>PG: persistir memoria
    PG-->>Notify: emitir cambio
    MCP-->>IDE: guardado exitoso
```

## Qué tiene que existir para que esto funcione

### 1. CLI instalable
Debe existir algo ejecutable como:

```bash
olinkb serve
```

o

```bash
olinkb mcp
```

### 2. Servidor MCP por `stdio`
OlinKB debe hablar MCP por `stdin/stdout`, igual que Engram.

### 3. Tools mínimas
Para que la experiencia sea útil y automática, OlinKB necesita al menos:

- `boot_session`
- `remember`
- `save_memory`
- `end_session`

### 4. Instrucciones del repositorio
El agente necesita reglas explícitas para saber cuándo usar OlinKB. Sin eso, el servidor estará registrado pero el modelo podría usarlo de forma inconsistente.

## Bloque de Instrucciones Recomendado
Este es el tipo de instrucción que debe vivir en el repositorio para forzar el comportamiento deseado:

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

## Qué no resuelve MCP por sí solo
Es importante dejar claro que MCP no garantiza una interceptación dura de cada prompt. El cliente expone tools y el agente decide si llamarlas.

Eso implica:

- MCP sí permite que OlinKB esté disponible siempre.
- MCP sí permite que el agente lo invoque automáticamente.
- MCP no obliga por sí solo a que cada prompt pase por OlinKB.

Si alguna vez se quisiera una garantía absoluta de "prefetch antes de cada prompt", eso ya sería otra capa: proxy, middleware u orquestador externo. Para la arquitectura actual, la recomendación correcta es no ir por ahí al inicio.

## Recomendación Final
El modelo correcto para OlinKB es este:

1. Instalar OlinKB como CLI local.
2. Registrarlo en VS Code como MCP `stdio`.
3. Exponer un conjunto mínimo de tools bien diseñadas.
4. Guiar su uso con instrucciones del repositorio.
5. Conectar esas tools a PostgreSQL como memoria compartida del equipo.

Con eso, OlinKB se comporta igual que Engram desde el punto de vista del usuario: está disponible siempre, VS Code lo llama cuando hace falta, y la memoria aparece integrada al flujo normal del agente en lugar de sentirse como una herramienta aparte.
