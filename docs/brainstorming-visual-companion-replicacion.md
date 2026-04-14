# Brainstorming Visual Companion: How to Replicate It Properly

This guide documents how to rebuild the brainstorming skill's visual companion with these properties:

- fixed and consistent visual branding
- a shared design system across all screens rendered as HTML fragments
- an explicit selection flow with an `Accept selection` button
- emission of a final `choice-confirmed` event
- preparation for future integration with VS Code or a host bridge

The goal is to let you repeat the change without rediscovering the architecture or losing operational details.

## 1. What changed exactly

The companion no longer depends only on the style of whatever HTML gets rendered. There is now a reusable base layer that wraps fragments and gives them a shared visual identity.

In addition, user selection is no longer interpreted only through exploratory clicks. The correct flow is:

1. the user selects an option
2. the footer enables `Accept selection`
3. the user confirms
4. the helper emits a structured `choice-confirmed` event

That event is published on several channels so the system is not coupled to a single integration.

## 2. Files that make up the system

The implementation lives outside this repository, in the local brainstorming skill.

Key files:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/frame-template.html`
- `/Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js`
- `/Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs`
- `/Users/rzjulio/.agents/skills/brainstorming/visual-companion.md`

Responsibility of each one:

- `frame-template.html`: fixed visual shell. Defines branding, global layout, footer, Accept button, and CSS tokens.
- `helper.js`: client-side logic. Handles selection, confirmation, event dispatch, and host hooks.
- `server.cjs`: persists browser events to `state_dir/events`.
- `visual-companion.md`: operational contract for using the system correctly.

## 3. Flow architecture

The complete flow is this:

1. the brainstorming server watches `screen_dir`
2. when new HTML appears, it serves the latest screen
3. if the file is a fragment, the server wraps it in `frame-template.html`
4. the browser loads `helper.js`
5. the user clicks nodes with `data-choice`
6. the helper updates the footer's visual state
7. when the user clicks `Accept selection`, the helper builds the final payload
8. that payload is emitted through WebSocket, a DOM event, and a host bridge if one exists
9. `server.cjs` writes it to `state_dir/events`

## 4. Persistent branding

If you want the companion to always look the same, this is the important rule:

**use HTML fragments by default, not full documents.**

When you write a fragment, the server wraps it with the base template. That guarantees:

- a header with visual identity
- a fixed palette for light and dark
- shared typography and spacing
- a footer with an indicator and confirmation button
- shared interactive behavior

If instead you serve a complete HTML document with `<!DOCTYPE html>` or `<html>`, the system only injects the helper. It does not automatically inherit the visual shell or the base footer flow.

## 5. How to rebuild the visual template

The file to edit is:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/frame-template.html`

The template must contain at least these pieces:

### 5.1 Design variables

Define global tokens in `:root` and in `@media (prefers-color-scheme: dark)`.

Minimum recommendation:

- backgrounds: `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`
- typography: `--text-primary`, `--text-secondary`, `--text-tertiary`
- identity: `--accent`, `--highlight`
- interaction: `--selected-bg`, `--selected-border`
- feedback: `--success`, `--warning`, `--error`
- depth: `--shadow-soft`, `--shadow-strong`
- radii: `--radius-xl`, `--radius-lg`, `--radius-md`

### 5.2 Visual shell

The recommended structure is:

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

Inside the header, it is useful to keep:

- a small visual mark, for example `SP`
- the product or flow title
- a short subtitle
- live session state

### 5.3 Fixed footer

The footer must include:

- `#indicator-text`
- `#indicator-note`
- button `#accept-selection`

Minimum example:

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

Without those IDs, `helper.js` cannot correctly synchronize footer state.

## 6. How to rebuild the selection flow

The file to edit is:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js`

### 6.1 What the helper does

It should cover these responsibilities:

1. connect to the companion server by WebSocket
2. emit all exploratory clicks
3. keep track of current selection state
4. enable or disable the Accept button
5. build a final payload when the user confirms
6. send that payload through more than one channel

### 6.2 Selection contract

Selectable elements must use `data-choice`.

Example:

```html
<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Layout A</h3>
      <p>Description</p>
    </div>
  </div>
</div>
```

For multi-select, the container must have `data-multiselect`.

### 6.3 Recommended final payload

When the user confirms, the helper should build something like this:

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

### 6.4 Channels where it should be emitted

The final confirmation should be emitted through at least these channels:

- the companion's local WebSocket
- `window.dispatchEvent(new CustomEvent(...))`
- `window.parent.postMessage(...)`
- `acquireVsCodeApi().postMessage(...)` if it exists

That does not mean Copilot Chat will react automatically. It means the browser is already prepared for a host bridge to listen to it.

## 7. How to persist the confirmed event

The file to edit is:

- `/Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs`

In `handleMessage(text)`, the server should keep writing to the `state_dir/events` file not only when `event.choice` exists, but also when an `event.choices` array exists.

The important condition is this idea:

```js
if (event.choice || (Array.isArray(event.choices) && event.choices.length > 0)) {
  fs.appendFileSync(eventsFile, JSON.stringify(event) + '\n');
}
```

That makes it possible to persist both simple clicks and richer final confirmations.

## 8. How to document the usage contract

The file to edit is:

- `/Users/rzjulio/.agents/skills/brainstorming/visual-companion.md`

It should make the following explicit:

- that HTML fragments inherit the shared visual shell
- that the standard selection flow is now two steps: choose and confirm
- that a `choice-confirmed` event exists
- that the companion emits events for a future host bridge
- that, for now, the main flow still depends on the next chat turn

## 9. How to test that it really works

Correct validation has two parts: syntax and real flow.

### 9.1 Syntax validation

```bash
node --check /Users/rzjulio/.agents/skills/brainstorming/scripts/helper.js
node --check /Users/rzjulio/.agents/skills/brainstorming/scripts/server.cjs
```

If both commands finish without output, JavaScript syntax is fine.

### 9.2 Manual flow validation

1. start the visual companion server
2. take the returned URL and open it in the browser
3. write a new HTML fragment into `screen_dir`
4. verify that it appears with the branded shell
5. select an option
6. verify that the footer changes and enables `Accept selection`
7. click `Accept selection`
8. open `state_dir/events`
9. verify that there is a `choice-confirmed` line

### 9.3 Minimum test fragment

```html
<h2>Which direction should we take?</h2>
<p class="subtitle">Choose one and confirm it from the footer.</p>

<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Warm editorial</h3>
      <p>More human, warm, and expressive.</p>
    </div>
  </div>

  <div class="option" data-choice="b" onclick="toggleSelect(this)">
    <div class="letter">B</div>
    <div class="content">
      <h3>Sharp systems UI</h3>
      <p>More technical, structured, and precise.</p>
    </div>
  </div>
</div>
```

### 9.4 Expected event

After confirming an option, `state_dir/events` should contain something like this:

```jsonl
{"type":"click","choice":"b","text":"B Sharp systems UI More technical, structured, and precise.","timestamp":1706000115}
{"type":"choice-confirmed","choice":"b","choices":["b"],"label":"Sharp systems UI","labels":["Sharp systems UI"],"confirmed":true,"screenTitle":"Which direction should we take?","timestamp":1706000117}
```

## 10. What can and cannot be automated today

### What can be automated today

- fix branding and the companion's global design
- enforce a standard footer with an Accept button
- distinguish between exploration and final confirmation
- persist the final decision in `state_dir/events`
- emit the decision to a possible external host

### What cannot be done with the current skill alone

There is currently no supported bridge that allows a companion HTML page to write to Copilot Chat by itself and automatically trigger the next turn inside the VS Code chat.

In other words:

- the companion can already publish the event
- but something else still has to listen and convert it into a chat action

## 11. What is needed for real automatic triggering into Copilot Chat

If you want the user to select an option, click Accept, and immediately start the next step without manually returning to the chat, you need an additional layer.

The correct path is a VS Code extension or host bridge that does this:

1. render the webview or intercept the published message
2. listen to `acquireVsCodeApi().postMessage(...)` or `window.parent.postMessage(...)`
3. receive the `choice-confirmed` payload
4. convert it into a chat action or a model call
5. continue the flow automatically

The companion is already prepared for that, but the skill alone still does not control Copilot Chat.

### 11.1 The important architecture decision

It is not a good idea to try to detect "whatever chat is currently open" at the moment a confirmation arrives from the browser.

That approach looks convenient, but it is technically fragile for three reasons:

1. there may be multiple chats open or several active tabs
2. the public API is not designed to inject arbitrary text into any standard Copilot Chat thread
3. a delayed companion message may arrive after the user has already changed chats, editors, or visual context

The correct solution is not to guess the right chat afterward. The correct solution is to **bind the companion to the right chat from the moment it launches**.

In this guide, that correlation is done with a unique identifier called `launchId`.

### 11.2 The recommended architecture

The strong recommendation is this:

1. create your own VS Code extension
2. register your own chat participant, for example `@brainstorm`
3. make only that participant able to open the Visual Companion
4. generate a `launchId` for each companion launch
5. store an internal record with the context of the request that created that companion
6. when the browser sends `choice-confirmed`, use `launchId` to resume exactly that flow

The key point is that you no longer depend on the "active chat". You depend on explicit, stable correlation.

### 11.3 Which APIs are actually reliable for this

The public, reasonable pieces to build on are these:

- `vscode.chat.createChatParticipant(...)`
- `ChatRequest`
- `ChatContext.history`
- `request.model.sendRequest(...)` or `vscode.lm.selectChatModels(...)`
- `webview.onDidReceiveMessage(...)`
- `acquireVsCodeApi().postMessage(...)`

These let you:

- receive a request inside a chat flow controlled by your extension
- open a webview or attach to an existing one
- send messages from the webview back to the extension
- continue reasoning automatically when the user confirms an option

What you should not use as an architectural foundation is any internal or undocumented GitHub Copilot Chat command that appears to "type text into the input and send it".

### 11.4 System mental model

Think of the solution as four layers:

1. **Chat origin**
   - the user makes a request to `@brainstorm`
   - the participant decides visual support is needed

2. **Launch registry**
   - the extension creates `launchId`
   - it persists enough state to resume

3. **Visual companion bridge**
   - the webview receives `launchId`
   - the user selects and confirms
   - the browser returns `choice-confirmed`

4. **Resume engine**
   - the extension receives the confirmation
   - it looks up `launchId`
   - it rebuilds the continuation prompt
   - it automatically triggers the next model call

### 11.5 Minimum launch registry structure

The extension needs to keep a map of pending sessions. You do not need a complex database at first. A `Map<string, PendingLaunch>` in memory can serve for the MVP. If you want resilience across window reloads, then persist it later in `ExtensionContext.workspaceState`.

Suggested type:

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

What it must store at minimum:

- `launchId`: the main correlation key
- `originalPrompt`: the user's original intent
- `serializedHistory`: enough context to continue
- `visualQuestion`: the specific question being solved visually
- `state`: to avoid double-processing
- timestamps: for expiration and cleanup

### 11.6 How `launchId` is generated and used

Simple rule:

- every time the participant opens a companion, generate a new ID
- store that ID in the internal registry
- inject the same ID into the companion HTML
- return it from the helper on confirmation

Example enriched payload from the webview:

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

With that, the extension no longer has to ask "which chat did this come from?". It only does:

1. take `launchId`
2. look it up in `pendingLaunches`
3. continue the correct session

### 11.7 Recommended end-to-end flow

#### Phase A: launch from chat

1. the user writes something to `@brainstorm`
2. the participant detects that a visual question is needed
3. the extension creates `launchId`
4. it serializes the minimum context needed
5. it opens or updates the companion webview
6. it injects the HTML content plus `launchId`
7. it responds in the chat with something like: "I opened the visual companion for you. Make your selection there and confirm with Accept."

#### Phase B: visual interaction

1. the webview renders options
2. the user explores by clicking options
3. the helper updates the footer
4. the user clicks `Accept selection`
5. the helper emits `choice-confirmed` with `launchId`

#### Phase C: automatic resume

1. the extension receives the webview message
2. it validates that `launchId` exists
3. it validates that the session is still in `waiting-for-selection`
4. it marks the registry entry as `confirmed`
5. it builds a continuation prompt with the selection
6. it calls the model automatically
7. it publishes the result on whatever surface you chose
8. it marks the session as `completed`

### 11.8 Where the continuation should appear

There is an important decision here. There are three real options.

#### Option A: continue inside your own participant

This is the best option.

How it works:

- the user starts the flow in `@brainstorm`
- the continuation also belongs to `@brainstorm`
- state is preserved because the companion always originated from that participant

Advantages:

- full control of context
- clear correlation
- you do not depend on hacks around standard Copilot UI
- you avoid the answer landing in the wrong chat

Disadvantage:

- the experience lives in your participant, not in any generic Copilot chat

#### Option B: send a model request and show the result in your own view

This is also valid, but it is less visually integrated with the chat experience.

Advantages:

- fully automatic flow
- high technical control

Disadvantages:

- the continuation no longer appears as a message inside the chat thread

#### Option C: try to insert text into the standard Copilot Chat UI

This is not the recommended option.

Problems:

- there is no stable public API for that
- you can end up depending on internal commands
- it becomes fragile across updates
- it is very hard to guarantee that it reaches the correct thread in every case

Conclusion: if you want it to work correctly, use Option A.

### 11.9 How to reconstruct the correct context

The extension should not depend on having an internal identifier for standard Copilot Chat. It should depend on the context it captured when the launch was created.

When creating `PendingLaunch`, it is useful to store:

- `request.prompt`
- `request.command` if present
- serialized history from `ChatContext.history`
- any relevant reference to the workspace or active file

Simple serialization example:

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

With that, you can reconstruct a composite prompt like:

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

### 11.10 How to open the webview without losing correlation

There are two possible models:

#### Model 1: one panel per launch

Each `launchId` opens its own panel.

Advantages:

- total isolation
- almost impossible to mix confirmations

Disadvantages:

- it can clutter the UI if the user launches many companions

#### Model 2: one reusable panel with internal state

A single panel is reused and its content updated.

Advantages:

- less visual noise

Disadvantages:

- requires strict discipline around `launchId`
- if you replace content while a confirmation is still pending, you can create correlation errors

For a serious MVP, I would start with Model 1. It is easier to reason about and harder to break.

### 11.11 Error handling and edge cases

If you want this to work reliably, these cases must be handled explicitly:

#### Case: the user opens two companions from two different chats

Solution:

- two different `launchId` values
- two different entries in `pendingLaunches`
- ideally two different panels

#### Case: the user confirms a selection with an expired `launchId`

Solution:

- the extension rejects the message
- it shows a notice: "This visual session has already expired. Launch a new one from the chat."

#### Case: Accept gets double-clicked

Solution:

- use `state`
- only process if it is in `waiting-for-selection`
- if it is already `confirmed` or `completed`, ignore the duplicate

#### Case: the user closes the panel and later comes back

Solution:

- if the launch is still alive, restore from `workspaceState`
- if you do not want restore in the MVP, expire the session clearly

#### Case: the model fails during automatic continuation

Solution:

- do not lose the confirmed selection
- switch state to `confirmed`
- offer a button or command for `retry`

### 11.12 Expiration and cleanup policy

You should not keep `launchId` values alive indefinitely.

Practical starting rule:

- `waiting-for-selection`: expire after 30 minutes
- `confirmed`: keep a few extra minutes in case retry is needed
- `completed`: clean up soon

Suggested cleanup:

- when the extension activates
- every time a new event arrives
- with a lightweight `setInterval`

### 11.13 Recommended bridge pseudocode

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

### 11.14 Final recommendation, without ambiguity

If the requirement is:

"I want the user to select in the Visual Companion and have the correct flow continue automatically, without mixing with other chats"

then the recommended architecture is this:

1. your own `@brainstorm` participant
2. your own extension bridge
3. explicit correlation through `launchId`
4. pending state stored per launch
5. automatic continuation controlled by the extension
6. no dependence on whichever active chat is visible, and no text injection into the standard Copilot UI

That approach can actually be robust, traceable, and maintainable.

## 12. Short checklist to repeat the work

Use this checklist when you want to rebuild it from scratch:

1. update `frame-template.html` with tokens, branding, shell, and a fixed footer
2. ensure the footer has `indicator-text`, `indicator-note`, and `accept-selection`
3. update `helper.js` to handle selection, confirmation, and multi-channel emission
4. update `server.cjs` to persist events with `choices`
5. update `visual-companion.md` to lock in the usage contract
6. validate with `node --check`
7. validate with a real companion session
8. confirm that `state_dir/events` contains `choice-confirmed`

## 13. Important operating rule

If the goal is to always keep the same visual identity, avoid sending full HTML documents unless you truly need total control. Reusable and stable behavior lives in the combination of:

- `frame-template.html`
- `helper.js`
- `server.cjs`
- the contract explained in `visual-companion.md`

Si uno de esos cuatro elementos se desvía, la experiencia deja de ser consistente.