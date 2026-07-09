// web/static/chat.js
// Chat UI: message list, input box, WebSocket communication

let ws = null;
let sessionId = null;
let currentMode = 'build';
let currentAssistantMsg = null;
let debugEvents = [];
let activeView = 'chat';
let slashCommands = [];
let slashMatches = [];
let activeSlashIndex = 0;
let shouldReconnect = true;
const approvalCards = new Map();
let pendingImages = [];

// --- DOM refs ---
const messagesEl = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const slashSuggestionsEl = document.getElementById('slash-suggestions');
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
const imagePreviewsEl = document.getElementById('image-previews');
const imageFileInput = document.getElementById('image-file-input');
const uploadBtn = document.getElementById('upload-btn');

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
      statusEl.textContent = shouldReconnect ? 'disconnected' : 'ended';
      if (shouldReconnect) {
        setTimeout(connect, 2000);
      }
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

    case 'command_result': {
      const data = event.data || {};
      const metadata = data.metadata || {};
      if (metadata.command === 'clear') {
        messagesEl.textContent = '';
      }
      if (metadata.transition && metadata.transition.new_mode) {
        syncMode(metadata.transition.new_mode);
      }
      if (data.message) {
        addMessage('system', data.message);
      }
      if (data.continue_session === false) {
        shouldReconnect = false;
        userInput.disabled = true;
        sendBtn.disabled = true;
      }
      break;
    }

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

    case 'approval_request':
      currentAssistantMsg = null;
      renderApprovalRequest(event.data || {});
      break;

    case 'approval_response':
      renderApprovalResponse(event.data || {});
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

    case 'todo_updated':
      renderTodoState(event.data);
      break;

    case 'pong':
      break;
  }
}

function syncMode(mode) {
  currentMode = mode || currentMode;
  modeValueEl.textContent = currentMode;
  modeSelectEl.value = currentMode;
  planningItemsEl.textContent = '';
  planningPanel.hidden = true;
  planningPanel.querySelector('.planning-panel-header').textContent =
    currentMode === 'plan' ? 'Plan' : 'Progress';
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

function renderApprovalRequest(data) {
  const approvalId = data.approval_id;
  if (!approvalId) return;

  const el = document.createElement('div');
  el.className = 'approval-card';

  const header = document.createElement('div');
  header.className = 'approval-card-header';

  const title = document.createElement('span');
  title.textContent = `Approval required: ${data.tool_name || 'tool'}`;
  header.appendChild(title);

  const risk = document.createElement('span');
  risk.className = 'approval-risk';
  risk.textContent = data.risk || '';
  header.appendChild(risk);
  el.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'approval-meta';
  const capability = Array.isArray(data.capability) ? data.capability.join(', ') : '';
  meta.textContent = `mode=${data.mode || ''} capability=${capability} origin=${data.origin || ''}`;
  el.appendChild(meta);

  if (data.reason) {
    const reason = document.createElement('div');
    reason.className = 'approval-reason';
    reason.textContent = data.reason;
    el.appendChild(reason);
  }

  const pre = document.createElement('pre');
  pre.className = 'approval-args';
  pre.textContent = data.args_summary || JSON.stringify(data.redacted_args || {}, null, 2);
  el.appendChild(pre);

  const controls = document.createElement('div');
  controls.className = 'approval-controls';

  const approve = document.createElement('button');
  approve.type = 'button';
  approve.className = 'approval-approve';
  approve.textContent = 'Approve';
  approve.addEventListener('click', () => sendApprovalDecision(approvalId, 'approved'));

  const deny = document.createElement('button');
  deny.type = 'button';
  deny.className = 'approval-deny';
  deny.textContent = 'Deny';
  deny.addEventListener('click', () => sendApprovalDecision(approvalId, 'denied'));

  const status = document.createElement('span');
  status.className = 'approval-status';
  status.textContent = 'pending';

  controls.appendChild(approve);
  controls.appendChild(deny);
  controls.appendChild(status);
  el.appendChild(controls);

  messagesEl.appendChild(el);
  approvalCards.set(approvalId, { el, approve, deny, status });
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function sendApprovalDecision(approvalId, decision) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const card = approvalCards.get(approvalId);
  if (card) {
    card.approve.disabled = true;
    card.deny.disabled = true;
    card.status.textContent = 'sent';
  }
  ws.send(JSON.stringify({
    type: 'approval_response',
    approval_id: approvalId,
    decision,
  }));
}

function renderApprovalResponse(data) {
  const approvalId = data.approval_id;
  const card = approvalCards.get(approvalId);
  if (!card) return;
  card.approve.disabled = true;
  card.deny.disabled = true;
  card.status.textContent = data.status || 'completed';
}

function renderPlanningState(state) {
  const items = state && Array.isArray(state.items) ? state.items : [];
  planningItemsEl.textContent = '';

  if (items.length === 0) {
    planningPanel.hidden = true;
    return;
  }

  planningPanel.querySelector('.planning-panel-header').textContent = 'Plan';
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

function renderTodoState(state) {
  const items = state && Array.isArray(state.items) ? state.items : [];
  planningItemsEl.textContent = '';

  if (items.length === 0) {
    planningPanel.hidden = true;
    return;
  }

  planningPanel.querySelector('.planning-panel-header').textContent = 'Progress';
  planningPanel.hidden = false;
  const statusLabels = { pending: ' ', in_progress: '▶', completed: '✓' };
  for (const item of items) {
    const row = document.createElement('li');
    row.className = `planning-item status-${item.status}`;

    const status = document.createElement('span');
    status.className = 'planning-status';
    status.textContent = statusLabels[item.status] || item.status;

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

// --- Image upload ---
uploadBtn.addEventListener('click', () => imageFileInput.click());

imageFileInput.addEventListener('change', () => {
  const files = imageFileInput.files;
  if (!files || files.length === 0) return;
  for (const file of files) {
    addImageFromFile(file);
  }
  imageFileInput.value = '';
});

document.addEventListener('paste', (e) => {
  if (document.activeElement !== userInput) return;
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      addImageFromFile(item.getAsFile());
    }
  }
});

// Drag and drop
const inputArea = document.getElementById('input-area');
let dragCounter = 0;

inputArea.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
});

inputArea.addEventListener('dragenter', (e) => {
  e.preventDefault();
  e.stopPropagation();
  dragCounter++;
  inputArea.classList.add('drag-over');
});

inputArea.addEventListener('dragleave', (e) => {
  e.preventDefault();
  e.stopPropagation();
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    inputArea.classList.remove('drag-over');
  }
});

inputArea.addEventListener('drop', (e) => {
  e.preventDefault();
  e.stopPropagation();
  dragCounter = 0;
  inputArea.classList.remove('drag-over');
  const files = e.dataTransfer && e.dataTransfer.files;
  if (!files || files.length === 0) return;
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      addImageFromFile(file);
    }
  }
});

async function addImageFromFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  if (file.size > 20 * 1024 * 1024) {
    addMessage('error', 'Image too large (max 20MB)');
    return;
  }
  try {
    const dataUrl = await readFileAsDataUrl(file);
    const resp = await fetch('/api/upload-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data_url: dataUrl }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      addMessage('error', `Upload failed: ${err.error || resp.status}`);
      return;
    }
    const result = await resp.json();
    pendingImages.push({
      data_url: dataUrl,
      file_path: result.file_path,
      url: result.url,
      name: file.name,
    });
    renderImagePreviews();
  } catch (e) {
    addMessage('error', `Upload failed: ${e.message}`);
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

function removeImage(index) {
  pendingImages.splice(index, 1);
  renderImagePreviews();
}

function renderImagePreviews() {
  if (!imagePreviewsEl) return;
  imagePreviewsEl.textContent = '';
  if (pendingImages.length === 0) {
    imagePreviewsEl.hidden = true;
    return;
  }
  imagePreviewsEl.hidden = false;
  pendingImages.forEach((img, index) => {
    const thumb = document.createElement('div');
    thumb.className = 'image-preview-item';
    const pic = document.createElement('img');
    pic.src = img.data_url;
    pic.alt = img.name || 'pasted image';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'image-preview-remove';
    remove.textContent = '×';
    remove.setAttribute('aria-label', 'Remove image');
    remove.addEventListener('click', () => removeImage(index));
    thumb.appendChild(pic);
    thumb.appendChild(remove);
    imagePreviewsEl.appendChild(thumb);
  });
}

// --- Send message ---
async function sendMessage() {
  const text = userInput.value.trim();
  const hasImages = pendingImages.length > 0;
  if ((!text && !hasImages) || !ws || ws.readyState !== WebSocket.OPEN) return;

  hideSlashSuggestions();

  if (hasImages) {
    const imagePreview = pendingImages.map(img => `[image: ${img.name || 'pasted'}]`).join(' ');
    const label = text ? `${text}\n${imagePreview}` : imagePreview;
    addMessage('user', label);
  } else {
    addMessage('user', text);
  }

  userInput.value = '';
  sendBtn.disabled = true;
  statusEl.textContent = text.startsWith('/') ? 'running command...' : 'thinking...';

  const payload = { type: 'chat', content: text || '' };
  if (hasImages) {
    payload.images = pendingImages.map(img => ({ url: img.data_url, file_path: img.file_path }));
    pendingImages = [];
    renderImagePreviews();
  }
  ws.send(JSON.stringify(payload));
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
userInput.addEventListener('input', updateSlashSuggestions);
userInput.addEventListener('blur', () => {
  setTimeout(hideSlashSuggestions, 100);
});
userInput.addEventListener('keydown', (e) => {
  if (slashSuggestionsEl && !slashSuggestionsEl.hidden) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveSlashSelection(1);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveSlashSelection(-1);
      return;
    }
    if (e.key === 'Tab' || e.key === 'Enter') {
      e.preventDefault();
      applySlashSuggestion(activeSlashIndex);
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      hideSlashSuggestions();
      return;
    }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// --- Slash command suggestions ---
function slashQueryFromInput() {
  const value = userInput.value;
  const cursor = userInput.selectionStart ?? value.length;
  const beforeCursor = value.slice(0, cursor);
  if (!beforeCursor.startsWith('/')) return null;
  if (beforeCursor.includes('\n')) return null;
  if (/\s/.test(beforeCursor)) return null;
  return beforeCursor.slice(1).toLowerCase();
}

function updateSlashSuggestions() {
  if (!slashSuggestionsEl) return;
  const query = slashQueryFromInput();
  if (query === null) {
    hideSlashSuggestions();
    return;
  }
  slashMatches = slashCommands.filter(command => {
    const aliases = Array.isArray(command.aliases) ? command.aliases : [];
    return command.name.startsWith(query) || aliases.some(alias => alias.startsWith(query));
  });
  activeSlashIndex = 0;
  renderSlashSuggestions();
}

function renderSlashSuggestions() {
  slashSuggestionsEl.textContent = '';
  if (slashMatches.length === 0) {
    hideSlashSuggestions();
    return;
  }
  slashSuggestionsEl.hidden = false;
  slashMatches.forEach((command, index) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = `slash-suggestion${index === activeSlashIndex ? ' active' : ''}`;
    option.setAttribute('role', 'option');
    option.setAttribute('aria-selected', index === activeSlashIndex ? 'true' : 'false');
    option.addEventListener('mousedown', event => {
      event.preventDefault();
      applySlashSuggestion(index);
    });

    const main = document.createElement('span');
    main.className = 'slash-suggestion-main';
    const name = document.createElement('code');
    name.textContent = command.command;
    main.appendChild(name);
    if (command.argument_hint) {
      const hint = document.createElement('span');
      hint.className = 'slash-suggestion-hint';
      hint.textContent = ` ${command.argument_hint}`;
      main.appendChild(hint);
    }

    const desc = document.createElement('span');
    desc.className = 'slash-suggestion-desc';
    desc.textContent = command.description || '';

    option.appendChild(main);
    option.appendChild(desc);
    slashSuggestionsEl.appendChild(option);
  });
}

function hideSlashSuggestions() {
  if (!slashSuggestionsEl) return;
  slashSuggestionsEl.hidden = true;
  slashSuggestionsEl.textContent = '';
  slashMatches = [];
  activeSlashIndex = 0;
}

function moveSlashSelection(delta) {
  if (slashMatches.length === 0) return;
  activeSlashIndex = (activeSlashIndex + delta + slashMatches.length) % slashMatches.length;
  renderSlashSuggestions();
}

function applySlashSuggestion(index) {
  const command = slashMatches[index];
  if (!command) return;
  userInput.value = command.insert_text || command.command;
  userInput.focus();
  userInput.setSelectionRange(userInput.value.length, userInput.value.length);
  hideSlashSuggestions();
}

// Watch for done event to re-enable send button
const origHandleEvent = handleEvent;
handleEvent = function(event) {
  origHandleEvent(event);
  if (event.type === 'done' || event.type === 'error') {
    sendBtn.disabled = !shouldReconnect;
    statusEl.textContent = shouldReconnect ? 'connected' : 'ended';
  }
};

// --- Init ---
async function init() {
  try {
    await connect();
    const commandResp = await fetch('/api/slash-commands');
    const commandCatalog = await commandResp.json();
    slashCommands = Array.isArray(commandCatalog.commands) ? commandCatalog.commands : [];
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
