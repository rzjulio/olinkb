# Brainstorming Visual Companion: Cómo Replicarlo Bien

Esta guía documenta cómo volver a montar el visual companion de la skill de brainstorming con estas propiedades:

- branding visual fijo y consistente
- sistema de diseño compartido en todas las pantallas renderizadas como fragmentos HTML
- flujo explícito de selección con botón `Accept selection`
- emisión de un evento final `choice-confirmed`
- preparación para una integración futura con VS Code o un host bridge

La intención es que puedas repetir el cambio sin redescubrir la arquitectura ni perder detalles operativos.

## 1. Qué se cambió exactamente

El companion ya no depende solo del estilo del HTML que se renderice. Ahora existe una capa base reusable que envuelve los fragmentos y les aplica una identidad visual común.

Además, la selección del usuario ya no se interpreta únicamente por clicks exploratorios. El flujo correcto es:

1. el usuario selecciona una opción
2. el footer habilita `Accept selection`
3. el usuario confirma
4. el helper emite un evento estructurado `choice-confirmed`

Ese evento se publica en varios canales para no quedar acoplado a una sola integración.

## 2. Archivos que forman el sistema

La implementación vive fuera de este repo, en la skill local de brainstorming.

Archivos clave:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/frame-template.html`
- `/Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js`
- `/Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs`
- `/Users/rzjulio/.agents/skills/brainstorming/visual-companion.md`

Responsabilidad de cada uno:

- `frame-template.html`: shell visual fija. Define branding, layout global, footer, botón Accept y tokens CSS.
- `helper.js`: lógica cliente. Maneja selección, confirmación, envío de eventos y hooks hacia host.
- `server.cjs`: persiste eventos del navegador en `state_dir/events`.
- `visual-companion.md`: contrato operativo para usar correctamente el sistema.

## 3. Arquitectura del flujo

El flujo completo es este:

1. el servidor de brainstorming observa `screen_dir`
2. cuando aparece un HTML nuevo, sirve la pantalla más reciente
3. si el archivo es un fragmento, el servidor lo envuelve en `frame-template.html`
4. el navegador carga `helper.js`
5. el usuario hace clicks sobre nodos con `data-choice`
6. el helper actualiza el estado visual del footer
7. al hacer click en `Accept selection`, el helper construye el payload final
8. ese payload se emite por WebSocket, DOM event y host bridge si existe
9. `server.cjs` lo escribe en `state_dir/events`

## 4. Branding persistente

Si quieres que el companion siempre se vea igual, la regla importante es esta:

**usa fragmentos HTML por defecto, no documentos completos.**

Cuando escribes un fragmento, el servidor lo envuelve con la plantilla base. Eso garantiza:

- header con identidad visual
- paleta fija para light y dark
- tipografía y espaciados comunes
- footer con indicador y botón de confirmación
- comportamiento interactivo compartido

Si en cambio sirves un documento HTML completo con `<!DOCTYPE html>` o `<html>`, el sistema solo inyecta el helper. No hereda automáticamente la shell visual ni el flujo base del footer.

## 5. Cómo reconstruir la plantilla visual

El archivo a tocar es:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/frame-template.html`

La plantilla debe contener al menos estas piezas:

### 5.1 Variables de diseño

Define tokens globales en `:root` y en `@media (prefers-color-scheme: dark)`.

Recomendación mínima:

- fondos: `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`
- tipografía: `--text-primary`, `--text-secondary`, `--text-tertiary`
- identidad: `--accent`, `--highlight`
- interacción: `--selected-bg`, `--selected-border`
- feedback: `--success`, `--warning`, `--error`
- profundidad: `--shadow-soft`, `--shadow-strong`
- radios: `--radius-xl`, `--radius-lg`, `--radius-md`

### 5.2 Shell visual

La estructura recomendada es:

```html
<body>
  <div class="header">...</div>
  <div class="main">
    <div id="claude-content">
      <!-- CONTENT -->
    </div>
  </div>
  <div class="indicator-bar">...</div>
</body>
```

Dentro del header conviene mantener:

- marca visual pequeña, por ejemplo `SP`
- título del producto o flujo
- subtítulo corto
- estado de sesión vivo

### 5.3 Footer fijo

El footer debe incluir:

- `#indicator-text`
- `#indicator-note`
- botón `#accept-selection`

Ejemplo mínimo:

```html
<div class="indicator-bar">
  <div class="indicator-copy">
    <span id="indicator-text">Select an option, then confirm it with Accept</span>
    <div id="indicator-note" class="indicator-note">The final confirmed choice is emitted as a structured event for the companion host.</div>
  </div>
  <div class="indicator-actions">
    <button id="accept-selection" class="accept-button" type="button" disabled>Accept selection</button>
  </div>
</div>
```

Sin estos IDs, `helper.js` no puede sincronizar correctamente el estado del footer.

## 6. Cómo reconstruir el flujo de selección

El archivo a tocar es:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js`

### 6.1 Qué hace el helper

Debe cubrir estas responsabilidades:

1. conectarse por WebSocket al companion server
2. emitir todos los clicks exploratorios
3. mantener el estado de selección actual
4. habilitar o deshabilitar el botón Accept
5. construir un payload final cuando el usuario confirma
6. enviar ese payload por más de un canal

### 6.2 Contrato de selección

Los elementos seleccionables deben usar `data-choice`.

Ejemplo:

```html
<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Layout A</h3>
      <p>Descripción</p>
    </div>
  </div>
</div>
```

Para multiselección, el contenedor debe tener `data-multiselect`.

### 6.3 Payload final recomendado

Al confirmar, el helper debe construir algo como esto:

```json
{
  "type": "choice-confirmed",
  "choice": "b",
  "choices": ["b"],
  "label": "Hybrid",
  "labels": ["Hybrid"],
  "selections": [
    {
      "containerType": "options",
      "multi": false,
      "choices": ["b"],
      "labels": ["Hybrid"],
      "ids": [null]
    }
  ],
  "screenTitle": "Which layout works better?",
  "confirmed": true,
  "timestamp": 1706000117
}
```

### 6.4 Canales donde debe emitirse

La confirmación final debe emitirse al menos en estos canales:

- WebSocket local del companion
- `window.dispatchEvent(new CustomEvent(...))`
- `window.parent.postMessage(...)`
- `acquireVsCodeApi().postMessage(...)` si existe

Esto no significa que Copilot Chat vaya a reaccionar automáticamente. Significa que el navegador ya queda preparado para que un host bridge pueda escucharlo.

## 7. Cómo persistir el evento confirmado

El archivo a tocar es:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs`

En `handleMessage(text)`, el servidor debe seguir escribiendo al archivo `state_dir/events` no solo cuando existe `event.choice`, sino también cuando exista un arreglo de `event.choices`.

La condición importante es esta idea:

```js
if (event.choice || (Array.isArray(event.choices) && event.choices.length > 0)) {
  fs.appendFileSync(eventsFile, JSON.stringify(event) + '\n');
}
```

Eso permite persistir tanto clicks simples como confirmaciones finales más ricas.

## 8. Cómo documentar el contrato de uso

El archivo a tocar es:

- `/Users/rzjulio/.agents/skills/brainstorming/visual-companion.md`

Debe dejar explícito lo siguiente:

- que los fragmentos HTML heredan la shell visual compartida
- que el flujo estándar de selección ahora es de dos pasos: elegir y confirmar
- que existe un evento `choice-confirmed`
- que el companion emite eventos para un host bridge futuro
- que, por ahora, el flujo principal sigue dependiendo del próximo turno del chat

## 9. Cómo probar que funciona de verdad

La validación correcta tiene dos partes: sintaxis y flujo real.

### 9.1 Validación de sintaxis

```bash
node --check /Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js
node --check /Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs
```

Si ambos comandos terminan sin salida, la sintaxis JavaScript está bien.

### 9.2 Validación de flujo manual

1. arranca el servidor del visual companion
2. toma la URL devuelta y ábrela en el navegador
3. escribe un fragmento HTML nuevo en `screen_dir`
4. verifica que aparezca con la shell branded
5. selecciona una opción
6. verifica que el footer cambie y habilite `Accept selection`
7. haz click en `Accept selection`
8. abre `state_dir/events`
9. verifica que exista una línea `choice-confirmed`

### 9.3 Fragmento mínimo de prueba

```html
<h2>Which direction should we take?</h2>
<p class="subtitle">Choose one and confirm it from the footer.</p>

<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Warm editorial</h3>
      <p>Más humano, cálido y expresivo.</p>
    </div>
  </div>

  <div class="option" data-choice="b" onclick="toggleSelect(this)">
    <div class="letter">B</div>
    <div class="content">
      <h3>Sharp systems UI</h3>
      <p>Más técnico, estructurado y preciso.</p>
    </div>
  </div>
</div>
```

### 9.4 Evento esperado

Después de confirmar una opción, `state_dir/events` debería contener algo como esto:

```jsonl
{"type":"click","choice":"b","text":"B Sharp systems UI Más técnico, estructurado y preciso.","timestamp":1706000115}
{"type":"choice-confirmed","choice":"b","choices":["b"],"label":"Sharp systems UI","labels":["Sharp systems UI"],"confirmed":true,"screenTitle":"Which direction should we take?","timestamp":1706000117}
```

## 10. Qué sí se puede automatizar y qué no

### Sí se puede hoy

- fijar branding y diseño global del companion
- imponer un footer estándar con botón Accept
- distinguir entre exploración y confirmación final
- persistir la decisión final en `state_dir/events`
- emitir la decisión a un posible host externo

### No se puede solo con la skill actual

No existe hoy un puente soportado para que una página HTML del companion escriba por sí sola en Copilot Chat y dispare automáticamente el siguiente turno dentro del chat de VS Code.

En otras palabras:

- el companion ya puede publicar el evento
- pero alguien más tiene que escucharlo y convertirlo en una acción de chat

## 11. Qué hace falta para el auto-disparo real hacia Copilot Chat

Si quieres que el usuario seleccione una opción, haga click en Accept y que inmediatamente arranque el siguiente paso sin volver manualmente al chat, necesitas una capa adicional.

La ruta correcta es una extensión o host bridge de VS Code que haga esto:

1. renderice el webview o intercepte el mensaje publicado
2. escuche `acquireVsCodeApi().postMessage(...)` o `window.parent.postMessage(...)`
3. reciba el payload `choice-confirmed`
4. lo convierta en una acción de chat o en una llamada al modelo
5. continúe el flujo automáticamente

El companion ya quedó preparado para eso, pero la skill por sí sola todavía no controla Copilot Chat.

### 11.1 La decisión de arquitectura importante

No conviene intentar detectar "el chat que esté abierto" en el momento en que llega la confirmación desde el browser.

Ese enfoque parece cómodo, pero técnicamente es frágil por tres razones:

1. puede haber varios chats abiertos o varias pestañas activas
2. la API pública no está pensada para inyectar texto arbitrario en cualquier hilo estándar de Copilot Chat
3. un mensaje tardío del companion puede llegar cuando el usuario ya cambió de chat, editor o contexto visual

La solución correcta no es adivinar el chat correcto después. La solución correcta es **amarrar el companion al chat correcto desde el momento en que se lanza**.

En esta guía, esa correlación se hace con un identificador único llamado `launchId`.

### 11.2 La arquitectura recomendada

La recomendación fuerte es esta:

1. crear una extensión de VS Code propia
2. registrar un chat participant propio, por ejemplo `@brainstorm`
3. hacer que solo ese participant pueda abrir el Visual Companion
4. generar un `launchId` por cada lanzamiento del companion
5. guardar un registro interno con el contexto del request que originó ese companion
6. cuando el browser envíe `choice-confirmed`, usar `launchId` para reanudar exactamente ese flujo

La clave está en que ya no dependes del "chat activo". Dependes de una correlación explícita y estable.

### 11.3 Qué APIs sí son fiables para esto

Las piezas públicas y razonables sobre las que conviene construir son estas:

- `vscode.chat.createChatParticipant(...)`
- `ChatRequest`
- `ChatContext.history`
- `request.model.sendRequest(...)` o `vscode.lm.selectChatModels(...)`
- `webview.onDidReceiveMessage(...)`
- `acquireVsCodeApi().postMessage(...)`

Estas piezas te permiten:

- recibir una petición dentro de un flujo de chat controlado por tu extensión
- abrir un webview o asociarte a uno existente
- mandar mensajes desde el webview hacia la extensión
- continuar el razonamiento automáticamente cuando el usuario confirme una opción

Lo que no debes tomar como base de arquitectura es cualquier comando interno o no documentado de GitHub Copilot Chat que aparente "meter texto en el input y enviarlo".

### 11.4 Modelo mental del sistema

Piensa la solución como cuatro capas:

1. **Chat origin**
   - el usuario hace una petición a `@brainstorm`
   - el participant decide que necesita apoyo visual

2. **Launch registry**
   - la extensión crea `launchId`
   - persiste estado suficiente para reanudar

3. **Visual companion bridge**
   - el webview recibe `launchId`
   - el usuario selecciona y confirma
   - el browser devuelve `choice-confirmed`

4. **Resume engine**
   - la extensión recibe la confirmación
   - busca el `launchId`
   - reconstruye el prompt de continuación
   - dispara automáticamente la siguiente llamada al modelo

### 11.5 Estructura mínima del registro de lanzamiento

La extensión necesita mantener un mapa de sesiones pendientes. No hace falta una base de datos compleja al principio. Un `Map<string, PendingLaunch>` en memoria puede servir para el MVP. Si quieres resiliencia ante reloads de la ventana, luego lo persistes en `ExtensionContext.workspaceState`.

Tipo sugerido:

```ts
type PendingLaunch = {
  launchId: string;
  createdAt: number;
  participantId: string;
  command?: string;
  originalPrompt: string;
  serializedHistory: Array<{ role: 'user' | 'assistant'; content: string }>;
  workspaceFolder?: string;
  visualQuestion: string;
  state: 'waiting-for-selection' | 'confirmed' | 'completed' | 'expired';
  webviewPanelId?: string;
  metadata?: Record<string, unknown>;
};
```

Qué debe guardar como mínimo:

- `launchId`: correlación principal
- `originalPrompt`: la intención original del usuario
- `serializedHistory`: contexto suficiente para continuar
- `visualQuestion`: la pregunta concreta que se estaba resolviendo visualmente
- `state`: para evitar dobles procesamientos
- timestamps: para expiración y limpieza

### 11.6 Cómo se genera y usa `launchId`

Regla simple:

- cada vez que el participant abre un companion, genera un ID nuevo
- ese ID se guarda en el registro interno
- el mismo ID se inyecta en el HTML del companion
- el helper lo devuelve al confirmar

Ejemplo de payload enriquecido desde el webview:

```json
{
  "type": "choice-confirmed",
  "launchId": "bs_20260413_01HXYZ...",
  "choice": "b",
  "choices": ["b"],
  "label": "Sharp systems UI",
  "screenTitle": "Which direction should we take?",
  "confirmed": true,
  "timestamp": 1776139999999
}
```

Con eso, la extensión ya no tiene que preguntarse "de qué chat vino esto". Solo hace:

1. tomar `launchId`
2. buscarlo en `pendingLaunches`
3. continuar la sesión correcta

### 11.7 Flujo end-to-end recomendado

#### Fase A: arranque desde chat

1. el usuario escribe algo a `@brainstorm`
2. el participant detecta que necesita una pregunta visual
3. la extensión crea `launchId`
4. serializa el contexto mínimo necesario
5. abre o actualiza el webview del companion
6. inyecta el contenido HTML más `launchId`
7. responde en el chat con algo como: "Te abrí el companion visual. Haz tu selección y confirma con Accept."

#### Fase B: interacción visual

1. el webview renderiza opciones
2. el usuario explora clicando opciones
3. el helper actualiza el footer
4. el usuario hace click en `Accept selection`
5. el helper emite `choice-confirmed` con `launchId`

#### Fase C: reanudación automática

1. la extensión recibe el mensaje del webview
2. valida que `launchId` exista
3. valida que la sesión siga en estado `waiting-for-selection`
4. marca el registro como `confirmed`
5. construye un prompt de continuación con la selección
6. llama al modelo automáticamente
7. publica el resultado en la superficie que hayas decidido
8. marca la sesión como `completed`

### 11.8 Dónde debe mostrarse la continuación

Aquí hay una decisión importante. Hay tres opciones reales.

#### Opción A: seguir dentro de tu participant propio

Esta es la mejor opción.

Cómo funciona:

- el usuario inicia el flujo en `@brainstorm`
- la continuación también pertenece a `@brainstorm`
- el estado se conserva porque el origen del companion siempre fue ese participant

Ventajas:

- control total del contexto
- correlación clara
- no dependes de hacks de la UI estándar de Copilot
- evitas que la respuesta termine en un chat equivocado

Desventaja:

- la experiencia ocurre en tu participant, no en cualquier chat genérico de Copilot

#### Opción B: disparar un request al modelo y mostrar el resultado en una vista propia

Esto también es válido, pero es menos integrado visualmente con la experiencia de chat.

Ventajas:

- flujo totalmente automático
- control técnico alto

Desventajas:

- la continuación ya no vive como mensaje dentro del hilo de chat

#### Opción C: intentar insertar el texto en la UI estándar de Copilot Chat

No es la opción recomendada.

Problemas:

- no hay una API pública estable para eso
- puedes terminar dependiendo de comandos internos
- se vuelve frágil con actualizaciones
- es muy difícil garantizar que llegue al hilo correcto en todos los casos

Conclusión: para que funcione perfecto, usa la Opción A.

### 11.9 Cómo reconstruir el contexto correcto

La extensión no debe depender de tener un identificador interno del chat estándar de Copilot. Debe depender del contexto que capturó cuando nació el launch.

Al crear `PendingLaunch`, conviene guardar:

- `request.prompt`
- `request.command` si existe
- historial serializado desde `ChatContext.history`
- cualquier referencia relevante al workspace o al archivo activo

Ejemplo de serialización simple:

```ts
function serializeHistory(history: readonly (vscode.ChatRequestTurn | vscode.ChatResponseTurn)[]) {
  const items: Array<{ role: 'user' | 'assistant'; content: string }> = [];

  for (const turn of history) {
    if (turn instanceof vscode.ChatRequestTurn) {
      items.push({ role: 'user', content: turn.prompt });
      continue;
    }

    if (turn instanceof vscode.ChatResponseTurn) {
      const content = turn.response
        .map(part => 'value' in part ? String(part.value.value ?? '') : '')
        .join('')
        .trim();

      if (content) {
        items.push({ role: 'assistant', content });
      }
    }
  }

  return items;
}
```

Con eso puedes reconstruir un prompt compuesto como:

```text
We are resuming a brainstorming flow.

Original user request:
...

Visual question shown to the user:
...

Confirmed choice:
- choice: b
- label: Sharp systems UI

Relevant prior conversation:
...

Continue the brainstorming process from this confirmed visual decision.
```

### 11.10 Cómo abrir el webview sin perder la correlación

Hay dos modelos posibles:

#### Modelo 1: un panel por lanzamiento

Cada `launchId` abre su propio panel.

Ventajas:

- aislamiento total
- casi imposible mezclar confirmaciones

Desventajas:

- puede llenar la UI si el usuario lanza muchos companions

#### Modelo 2: un panel reutilizable con estado interno

Un solo panel que se reutiliza y actualiza su contenido.

Ventajas:

- menos ruido visual

Desventajas:

- exige disciplina fuerte con `launchId`
- si reemplazas contenido mientras hay una confirmación pendiente, puedes crear errores de correlación

Para un MVP serio, yo empezaría con el Modelo 1. Es más fácil de razonar y más difícil de romper.

### 11.11 Manejo de errores y casos límite

Si quieres que funcione perfecto, estos casos deben resolverse explícitamente:

#### Caso: el usuario abre dos companions desde dos chats distintos

Solución:

- dos `launchId` distintos
- dos entradas distintas en `pendingLaunches`
- idealmente dos paneles distintos

#### Caso: el usuario confirma una selección con un `launchId` expirado

Solución:

- la extensión rechaza el mensaje
- muestra aviso: "Esta sesión visual ya expiró. Lanza una nueva desde el chat."

#### Caso: llega doble click sobre Accept

Solución:

- usa `state`
- solo procesas si está en `waiting-for-selection`
- si ya está en `confirmed` o `completed`, ignoras el duplicado

#### Caso: el usuario cierra el panel y luego vuelve

Solución:

- si el launch sigue vivo, restauras desde `workspaceState`
- si no quieres soportar restore en el MVP, expira la sesión con claridad

#### Caso: el modelo falla al continuar automáticamente

Solución:

- no pierdas la selección confirmada
- cambia el estado a `confirmed`
- ofrece botón o comando para `retry`

### 11.12 Política de expiración y limpieza

No conviene dejar `launchId` vivos indefinidamente.

Regla práctica inicial:

- `waiting-for-selection`: expira en 30 minutos
- `confirmed`: conservar unos minutos extra por si hace falta retry
- `completed`: limpiar pronto

Limpieza sugerida:

- al activar la extensión
- cada vez que llega un evento nuevo
- con un `setInterval` liviano

### 11.13 Pseudocódigo del bridge recomendado

```ts
const pendingLaunches = new Map<string, PendingLaunch>();

async function handleBrainstormRequest(request, context, stream) {
  const launchId = createLaunchId();

  pendingLaunches.set(launchId, {
    launchId,
    createdAt: Date.now(),
    participantId: 'brainstorm',
    command: request.command,
    originalPrompt: request.prompt,
    serializedHistory: serializeHistory(context.history),
    visualQuestion: 'Which direction should we take?',
    state: 'waiting-for-selection'
  });

  const panel = openCompanionPanel({ launchId });
  renderCompanion(panel, { launchId, screen: buildScreenHtml() });

  stream.markdown('Visual companion opened. Confirm a choice there and I will continue automatically.');
}

async function handleWebviewMessage(message) {
  if (message.type !== 'choice-confirmed') return;

  const pending = pendingLaunches.get(message.launchId);
  if (!pending) {
    showExpiredLaunchError();
    return;
  }

  if (pending.state !== 'waiting-for-selection') {
    return;
  }

  pending.state = 'confirmed';

  const resumePrompt = buildResumePrompt(pending, message);
  const [model] = await vscode.lm.selectChatModels({ vendor: 'copilot' });
  const response = await model.sendRequest(resumePrompt, {}, new vscode.CancellationTokenSource().token);

  await showOrStreamContinuation(pending, response);
  pending.state = 'completed';
}
```

### 11.14 La recomendación final, sin ambigüedad

Si el requisito es:

"quiero que el usuario seleccione en el Visual Companion y que automáticamente continúe el flujo correcto, sin mezclarse con otros chats"

entonces la arquitectura recomendada es esta:

1. participant propio `@brainstorm`
2. bridge de extensión propio
3. correlación explícita por `launchId`
4. estado pendiente guardado por lanzamiento
5. continuación automática controlada por la extensión
6. nada de depender del chat activo visible ni de inyectar texto en la UI estándar de Copilot

Ese enfoque sí puede quedar robusto, trazable y mantenible.

## 12. Checklist corto para repetir el trabajo

Usa este checklist cuando quieras rehacerlo desde cero:

1. actualiza `frame-template.html` con tokens, branding, shell y footer fijo
2. asegura que el footer tenga `indicator-text`, `indicator-note` y `accept-selection`
3. actualiza `helper.js` para manejar selección, confirmación y emisión multinivel
4. actualiza `server.cjs` para persistir eventos con `choices`
5. actualiza `visual-companion.md` para fijar el contrato de uso
6. valida con `node --check`
7. valida con una sesión real del companion
8. confirma que `state_dir/events` contiene `choice-confirmed`

## 13. Regla operativa importante

Si el objetivo es mantener siempre la misma identidad visual, evita mandar documentos HTML completos salvo que de verdad necesites control total. El comportamiento reusable y estable vive en la combinación de:

- `frame-template.html`
- `helper.js`
- `server.cjs`
- el contrato explicado en `visual-companion.md`

Si uno de esos cuatro elementos se desvía, la experiencia deja de ser consistente.