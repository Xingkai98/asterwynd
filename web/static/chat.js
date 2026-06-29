// web/static/chat.js
// Chat UI: message list, input box, WebSocket communication

let ws = null;
let sessionId = null;
let currentMode = 'build';
let currentAssistantMsg = null;
let debugEvents = [];
let activeView = 'chat';

// --- DOM refs ---
const messagesEl = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusEl = document.getElementById('status');
const sessionIdEl = document.getElementById('session-id');
const runIdEl = document.getElementById('run-id');
const modeValueEl = document.getElementById('mode-value');
const modeSelectEl = document.getElementById('mode-select');
const modeApplyBtn = document.getElementById('mode-apply');
const debugTabBtn = document.getElementById('debug-tab');
const planDocumentPanel = document.getElementById('plan-document-panel');
const planDocumentTitleEl = document.getElementById('plan-document-title');
const planDocumentBodyEl = document.getElementById('plan-document-body');
const planningPanel = document.getElementById('planning-panel');
const planningItemsEl = document.getElementById('planning-items');

// --- Tab switching ---
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const viewName = tab.dataset.tab;
    activeView = viewName;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
    document.getElementById('chat-view').classList.toggle('active', viewName === 'chat');
    document.getElementById('debug-view').classList.toggle('active', viewName === 'debug');
  });
});

// --- WebSocket ---
async function connect() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/${sessionId || 'new'}`;

  return new Promise((resolve, reject) => {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      statusEl.textContent = 'connected';
      resolve();
    };
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      handleEvent(event);
    };
    ws.onclose = () => {
      statusEl.textContent = 'disconnected';
      setTimeout(connect, 2000);
    };
    ws.onerror = () => {
      statusEl.textContent = 'error';
      reject(new Error('WebSocket error'));
    };
  });
}

function handleEvent(event) {
  switch (event.type) {
    case 'session_created':
      sessionId = event.session_id;
      sessionIdEl.textContent = sessionId;
      runIdEl.textContent = 'none';
      syncMode(event.mode || currentMode);
      break;

    case 'run_started':
      if (event.data && event.data.session_id) {
        sessionId = event.data.session_id;
        sessionIdEl.textContent = sessionId;
      }
      if (event.data && event.data.run_id) {
        runIdEl.textContent = event.data.run_id;
      }
      if (event.data && event.data.mode) {
        syncMode(event.data.mode);
      }
      break;

    case 'mode_changed':
      if (event.data && event.data.new_mode) {
        syncMode(event.data.new_mode);
      }
      break;

    case 'llm_response': {
      const data = event.data;
      if (data.streamed) {
        break;
      }
      if (data.content) {
        if (!currentAssistantMsg) {
          currentAssistantMsg = addMessage('assistant', '');
        }
        appendAssistantContent(currentAssistantMsg, data.content);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      break;
    }

    case 'assistant_delta': {
      const data = event.data || {};
      if (data.delta) {
        if (!currentAssistantMsg) {
          currentAssistantMsg = addMessage('assistant', '');
        }
        appendAssistantContent(currentAssistantMsg, data.delta);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      break;
    }

    case 'tool_call':
      currentAssistantMsg = null;
      addToolCallBlock(event.data.name, event.data.arguments);
      break;

    case 'tool_result':
      addToolResultMessage(event.data);
      break;

    case 'done':
      currentAssistantMsg = null;
      if (event.data && event.data.stop_reason === 'max_iterations' && !event.data.content) {
        addMessage('error', 'Run stopped before producing a final response.');
      }
      break;

    case 'error':
      currentAssistantMsg = null;
      addMessage('error', event.data && event.data.message ? event.data.message : 'Run failed.');
      break;

    case 'debug':
      debugEvents.push(event);
      renderDebug();
      break;

    case 'planning_state_updated':
      renderPlanningState(event.data);
      if (typeof renderPlanningDebug === 'function') {
        renderPlanningDebug(event.data);
      }
      break;

    case 'plan_document_updated':
    case 'plan_document_submitted':
      renderPlanDocument(event.data);
      break;

    case 'pong':
      break;
  }
}

function syncMode(mode) {
  currentMode = mode || currentMode;
  modeValueEl.textContent = currentMode;
  modeSelectEl.value = currentMode;
}

// --- Message rendering ---
function addMessage(role, content) {
  const el = document.createElement('div');
  el.className = `message ${role}`;
  if (role === 'tool') {
    const header = document.createElement('div');
    header.className = 'message-header';
    header.textContent = 'tool result';
    el.appendChild(header);
  }
  const body = document.createElement('div');
  body.className = 'message-body';
  if (role === 'assistant') {
    body.classList.add('markdown-body');
    body.dataset.markdownSource = '';
    appendAssistantContent(body, content || '');
  } else {
    body.textContent = content;
  }
  el.appendChild(body);
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return body;
}

function appendAssistantContent(body, content) {
  const source = (body.dataset.markdownSource || '') + (content || '');
  body.dataset.markdownSource = source;
  if (window.AsterwyndMarkdown && typeof window.AsterwyndMarkdown.render === 'function') {
    body.innerHTML = window.AsterwyndMarkdown.render(source);
  } else {
    body.textContent = source;
  }
}

function addToolCallBlock(name, args) {
  const block = document.createElement('div');
  block.className = 'tool-call-block';
  block.innerHTML = `<span class="tool-name">🔧 ${name}</span>`;
  if (args && Object.keys(args).length > 0) {
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(args, null, 2);
    block.appendChild(pre);
  }
  messagesEl.appendChild(block);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addToolResultMessage(data) {
  const el = document.createElement('div');
  el.className = 'message tool';

  const display = data.display || {
    collapsed: false,
    preview: data.result || '',
    char_count: (data.result || '').length,
    line_count: (data.result || '').split('\n').length,
  };
  const fullResult = data.result || '';

  const header = document.createElement('div');
  header.className = 'message-header tool-result-header';

  const title = document.createElement('span');
  title.textContent = `tool result: ${data.name}`;
  header.appendChild(title);

  const meta = document.createElement('span');
  meta.className = 'tool-result-meta';
  meta.textContent = `${display.char_count} chars / ${display.line_count} lines`;
  header.appendChild(meta);

  el.appendChild(header);

  const body = document.createElement('div');
  body.className = 'tool-result-body';
  body.textContent = display.collapsed ? display.preview : fullResult;
  el.appendChild(body);

  if (display.collapsed) {
    const controls = document.createElement('div');
    controls.className = 'tool-result-controls';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'tool-result-toggle';
    toggle.textContent = 'Expand';
    toggle.setAttribute('aria-expanded', 'false');

    let expanded = false;
    toggle.addEventListener('click', () => {
      expanded = !expanded;
      body.textContent = expanded ? fullResult : display.preview;
      toggle.textContent = expanded ? 'Collapse' : 'Expand';
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });

    controls.appendChild(toggle);
    el.appendChild(controls);
  }

  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return body;
}

function renderPlanningState(state) {
  const items = state && Array.isArray(state.items) ? state.items : [];
  planningItemsEl.textContent = '';

  if (items.length === 0) {
    planningPanel.hidden = true;
    return;
  }

  planningPanel.hidden = false;
  for (const item of items) {
    const row = document.createElement('li');
    row.className = `planning-item status-${item.status}`;

    const status = document.createElement('span');
    status.className = 'planning-status';
    status.textContent = item.status;

    const content = document.createElement('span');
    content.className = 'planning-content';
    content.textContent = item.content || '';

    row.appendChild(status);
    row.appendChild(content);

    if (item.note) {
      const note = document.createElement('span');
      note.className = 'planning-note';
      note.textContent = item.note;
      row.appendChild(note);
    }

    planningItemsEl.appendChild(row);
  }
}

function renderPlanDocument(document) {
  const markdown = document && typeof document.markdown === 'string'
    ? document.markdown
    : '';
  const title = document && typeof document.title === 'string'
    ? document.title
    : '';

  if (!markdown) {
    planDocumentPanel.hidden = true;
    planDocumentTitleEl.textContent = '';
    planDocumentBodyEl.textContent = '';
    return;
  }

  planDocumentPanel.hidden = false;
  const status = document && document.status === 'submitted' ? 'Submitted' : 'Draft';
  planDocumentTitleEl.textContent = title ? `${status}: ${title}` : status;
  planDocumentBodyEl.dataset.markdownSource = markdown;
  if (window.AsterwyndMarkdown && typeof window.AsterwyndMarkdown.render === 'function') {
    planDocumentBodyEl.innerHTML = window.AsterwyndMarkdown.render(markdown);
  } else {
    planDocumentBodyEl.textContent = markdown;
  }
}

// --- Send message ---
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  addMessage('user', text);
  userInput.value = '';
  sendBtn.disabled = true;
  statusEl.textContent = 'thinking...';

  ws.send(JSON.stringify({ type: 'chat', content: text }));
}

function sendModeChange() {
  const nextMode = modeSelectEl.value;
  if (!ws || ws.readyState !== WebSocket.OPEN || !nextMode || nextMode === currentMode) {
    return;
  }
  ws.send(JSON.stringify({ type: 'set_mode', mode: nextMode }));
}

sendBtn.addEventListener('click', sendMessage);
modeApplyBtn.addEventListener('click', sendModeChange);
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Watch for done event to re-enable send button
const origHandleEvent = handleEvent;
handleEvent = function(event) {
  origHandleEvent(event);
  if (event.type === 'done' || event.type === 'error') {
    sendBtn.disabled = false;
    statusEl.textContent = 'connected';
  }
};

// --- Init ---
async function init() {
  try {
    await connect();
    // Check debug status
    const resp = await fetch('/api/debug-status');
    const dbg = await resp.json();
    if (dbg.enabled) {
      debugTabBtn.style.display = '';
    }
  } catch (e) {
    statusEl.textContent = 'connection failed';
  }
}

init();
