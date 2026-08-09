// web/static/chat.js
// Chat UI: message list, input box, WebSocket communication, multi-session tabs.

// --- Multi-session tab state (issue #117) ---
let tabs = new Map();          // tabId -> tab
let activeTabId = null;

// 每个会话一个 Tab，独立持有 WebSocket、消息容器与运行状态。
function createTab(tabId, sessionId, workspace, mode) {
  const tab = {
    id: tabId,
    sessionId: sessionId || null,
    workspace: workspace || null,
    mode: mode || 'build',
    ws: null,
    currentAssistantMsg: null,
    debugEvents: [],
    debugIterBlocks: {},
    approvalCards: new Map(),
    questionCards: new Map(),
    pendingImages: [],
    shouldReconnect: true,
    slashMatches: [],
    activeSlashIndex: 0,
    inFlight: false,
    uploadWaiters: new Map(),
    pane: null,
    messagesEl: null,
    inputEl: null,
    previewsEl: null,
    slashSuggestionsEl: null,
    sendBtn: null,
    uploadBtn: null,
    imageFileInput: null,
  };
  tabs.set(tabId, tab);
  return tab;
}

function getActiveTab() {
  return activeTabId ? tabs.get(activeTabId) : null;
}

// 全局状态变量作为「当前 active tab 上下文」的代理：渲染/事件函数读写的就是
// 当前 tab 的状态，切换 tab 时 bindActiveTab 重新指向。
let ws = null;
let sessionId = null;
let currentMode = 'build';
let currentAssistantMsg = null;
let debugEvents = [];
let activeView = 'hub';
let slashCommands = [];
let slashMatches = [];
let activeSlashIndex = 0;
let shouldReconnect = true;
let approvalCards = new Map();
let questionCards = new Map();
let pendingImages = [];
let sendInFlight = false;
let wsUploadWaiters = new Map();
let iterBlocks = {};  // debug 迭代块索引（per-tab，见 debug.js）
// per-tab DOM（在 tab pane 内动态创建；bindActiveTab 时指向 active tab）
let messagesEl = null;
let userInput = null;
let slashSuggestionsEl = null;
let sendBtn = null;
let imagePreviewsEl = null;
let imageFileInput = null;
let uploadBtn = null;
// 全局 chrome（header/面板，保持单例）
const statusEl = document.getElementById('status');
const sessionIdEl = document.getElementById('session-id');
const runIdEl = document.getElementById('run-id');
const modeValueEl = document.getElementById('mode-value');
const modeSelectEl = document.getElementById('mode-select');
const modeApplyBtn = document.getElementById('mode-apply');
const debugTabBtn = document.getElementById('debug-tab');
const chatTabBtn = document.getElementById('chat-tab');
const hubTabBtn = document.getElementById('hub-tab');
const planDocumentPanel = document.getElementById('plan-document-panel');
const planDocumentTitleEl = document.getElementById('plan-document-title');
const planDocumentBodyEl = document.getElementById('plan-document-body');
const planDocumentToggle = document.getElementById('plan-document-toggle');
const planningPanel = document.getElementById('planning-panel');
const planningItemsEl = document.getElementById('planning-items');
const planningToggle = document.getElementById('planning-toggle');
const planningTitle = document.getElementById('planning-title');
const planningCount = document.getElementById('planning-count');
const chatPanesEl = document.getElementById('chat-panes');
const sessionTabsEl = document.getElementById('session-tabs');
const hubViewEl = document.getElementById('hub-view');
const chatViewEl = document.getElementById('chat-view');
const hubWorkspaceSelect = document.getElementById('hub-workspace-select');
const hubNewMode = document.getElementById('hub-new-mode');
const hubNewWorkspace = document.getElementById('hub-new-workspace');
const hubNewBtn = document.getElementById('hub-new-btn');
const hubSessionList = document.getElementById('hub-session-list');
const hubListCount = document.getElementById('hub-list-count');

const MAX_IMAGE_FILE_BYTES = 20 * 1024 * 1024;
const MAX_CHAT_PAYLOAD_CHARS = 12 * 1024 * 1024;
const WS_UPLOAD_CHUNK_CHARS = 256 * 1024;
const HTTP_UPLOAD_TIMEOUT_MS = 30000;
const WS_UPLOAD_EVENT_TIMEOUT_MS = 45000;
const IMAGE_NORMALIZE_THRESHOLD_BYTES = 2 * 1024 * 1024;
const MAX_NORMALIZED_IMAGE_SIDE = 1600;
const JPEG_QUALITY = 0.82;
const SUPPORTED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);
const HEIC_IMAGE_TYPES = new Set(['image/heic', 'image/heif']);

// --- Tab lifecycle ---
function buildTabPane(tab) {
  const pane = document.createElement('div');
  pane.className = 'tab-pane';
  pane.dataset.tabId = tab.id;
  pane.innerHTML = `
    <div class="tab-messages"></div>
    <div class="input-area">
      <div class="input-shell">
        <div class="slash-suggestions" role="listbox" aria-label="Slash commands" hidden></div>
        <div class="image-previews" hidden></div>
        <div class="input-row">
          <textarea class="user-input" placeholder="输入消息..." rows="2" autocomplete="off"></textarea>
          <input type="file" class="image-file-input" accept="image/*" multiple hidden>
          <button type="button" class="upload-btn" title="上传图片">+</button>
          <button type="button" class="send-btn">发送</button>
        </div>
      </div>
    </div>`;
  tab.pane = pane;
  tab.messagesEl = pane.querySelector('.tab-messages');
  tab.inputEl = pane.querySelector('.user-input');
  tab.slashSuggestionsEl = pane.querySelector('.slash-suggestions');
  tab.previewsEl = pane.querySelector('.image-previews');
  tab.imageFileInput = pane.querySelector('.image-file-input');
  tab.uploadBtn = pane.querySelector('.upload-btn');
  tab.sendBtn = pane.querySelector('.send-btn');

  // 输入区事件绑定（闭包捕获 tab）：先切到该 tab 再执行，保证全局代理指向它。
  tab.sendBtn.addEventListener('click', () => { switchTab(tab.id); sendMessage(); });
  tab.uploadBtn.addEventListener('click', () => { switchTab(tab.id); tab.imageFileInput.click(); });
  tab.imageFileInput.addEventListener('change', () => {
    switchTab(tab.id);
    const files = tab.imageFileInput.files;
    if (!files || files.length === 0) return;
    for (const file of files) addImageFromFile(file);
    tab.imageFileInput.value = '';
  });
  tab.inputEl.addEventListener('input', () => { switchTab(tab.id); updateSlashSuggestions(); });
  tab.inputEl.addEventListener('blur', () => { setTimeout(hideSlashSuggestions, 100); });
  tab.inputEl.addEventListener('keydown', (e) => {
    switchTab(tab.id);
    const suggestions = tab.slashSuggestionsEl;
    if (suggestions && !suggestions.hidden) {
      if (e.key === 'ArrowDown') { e.preventDefault(); moveSlashSelection(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); moveSlashSelection(-1); return; }
      if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); applySlashSuggestion(activeSlashIndex); return; }
      if (e.key === 'Escape') { e.preventDefault(); hideSlashSuggestions(); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  chatPanesEl.appendChild(pane);
  return tab;
}

function bindActiveTab(tab) {
  if (!tab) return;
  activeTabId = tab.id;
  ws = tab.ws;
  sessionId = tab.sessionId;
  currentMode = tab.mode;
  currentAssistantMsg = tab.currentAssistantMsg;
  debugEvents = tab.debugEvents;
  approvalCards = tab.approvalCards;
  questionCards = tab.questionCards;
  pendingImages = tab.pendingImages;
  shouldReconnect = tab.shouldReconnect;
  slashMatches = tab.slashMatches;
  activeSlashIndex = tab.activeSlashIndex;
  sendInFlight = tab.inFlight;
  wsUploadWaiters = tab.uploadWaiters;
  iterBlocks = tab.debugIterBlocks;
  messagesEl = tab.messagesEl;
  userInput = tab.inputEl;
  slashSuggestionsEl = tab.slashSuggestionsEl;
  sendBtn = tab.sendBtn;
  imagePreviewsEl = tab.previewsEl;
  imageFileInput = tab.imageFileInput;
  uploadBtn = tab.uploadBtn;
  // header chrome
  sessionIdEl.textContent = tab.sessionId || 'pending';
  modeValueEl.textContent = tab.mode;
  modeSelectEl.value = tab.mode;
  runIdEl.textContent = 'none';
  statusEl.textContent = tab.ws && tab.ws.readyState === WebSocket.OPEN ? 'connected' : (tab.shouldReconnect ? 'disconnected' : 'ended');
  syncMode(tab.mode);
  renderSessionTabs();
}

function syncActiveTab() {
  const tab = getActiveTab();
  if (!tab) return;
  tab.ws = ws;
  tab.sessionId = sessionId;
  tab.mode = currentMode;
  tab.currentAssistantMsg = currentAssistantMsg;
  tab.debugEvents = debugEvents;
  tab.approvalCards = approvalCards;
  tab.questionCards = questionCards;
  tab.pendingImages = pendingImages;
  tab.shouldReconnect = shouldReconnect;
  tab.slashMatches = slashMatches;
  tab.activeSlashIndex = activeSlashIndex;
  tab.inFlight = sendInFlight;
  tab.uploadWaiters = wsUploadWaiters;
  tab.debugIterBlocks = iterBlocks;
}

function renderSessionTabs() {
  if (!sessionTabsEl) return;
  sessionTabsEl.textContent = '';
  for (const tab of tabs.values()) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'session-tab' + (tab.id === activeTabId ? ' active' : '');
    btn.dataset.tabId = tab.id;
    btn.textContent = tab.sessionId ? tab.sessionId.slice(0, 8) : 'new';
    btn.title = tab.sessionId || 'new session';
    btn.addEventListener('click', () => switchTab(tab.id));
    const close = document.createElement('span');
    close.className = 'session-tab-close';
    close.textContent = '×';
    close.addEventListener('click', (e) => {
      e.stopPropagation();
      closeTab(tab.id);
    });
    btn.appendChild(close);
    sessionTabsEl.appendChild(btn);
  }
  sessionTabsEl.hidden = tabs.size === 0;
}

function switchTab(tabId) {
  const tab = tabs.get(tabId);
  if (!tab) return;
  syncActiveTab();
  for (const t of tabs.values()) {
    if (t.pane) t.pane.classList.toggle('active', t.id === tabId);
  }
  bindActiveTab(tab);
  activeView = 'chat';
  document.querySelectorAll('.tab[data-tab]').forEach(t => t.classList.toggle('active', t.dataset.tab === 'chat'));
  chatViewEl.classList.add('active');
  hubViewEl.classList.remove('active');
  document.getElementById('debug-view').classList.remove('active');
}

function closeTab(tabId) {
  const tab = tabs.get(tabId);
  if (!tab) return;
  if (tab.ws) {
    tab.shouldReconnect = false;
    try { tab.ws.close(); } catch (e) { /* ignore */ }
  }
  if (tab.pane) tab.pane.remove();
  tabs.delete(tabId);
  if (activeTabId === tabId) {
    const next = Array.from(tabs.keys())[0];
    if (next) switchTab(next);
    else {
      activeTabId = null;
      showHub();
    }
  } else {
    renderSessionTabs();
  }
}

function showHub() {
  activeView = 'hub';
  document.querySelectorAll('.tab[data-tab]').forEach(t => t.classList.toggle('active', t.dataset.tab === 'hub'));
  hubViewEl.classList.add('active');
  chatViewEl.classList.remove('active');
  document.getElementById('debug-view').classList.remove('active');
  loadHub();
}

function openSessionTab(sessionId, workspace) {
  // 已打开的 tab 直接激活
  if (tabs.has(sessionId)) {
    switchTab(sessionId);
    return;
  }
  const tab = createTab(sessionId, sessionId, workspace, 'build');
  buildTabPane(tab);
  switchTab(sessionId);
  connectTab(tab, sessionId, workspace);
}

// --- Planning panel toggle ---
function setPlanningPanelCollapsed(collapsed) {
  planningPanel.classList.toggle('collapsed', collapsed);
  planningToggle.classList.toggle('collapsed', collapsed);
  planningToggle.setAttribute('aria-expanded', String(!collapsed));
  planningToggle.setAttribute('aria-label', collapsed ? 'Expand panel' : 'Collapse panel');
  planningToggle.title = collapsed ? 'Expand' : 'Collapse';
}

planningToggle.addEventListener('click', () => {
  setPlanningPanelCollapsed(planningPanel.classList.toggle('collapsed'));
});

// Tap/click a truncated progress item to expand it (touch devices have no hover tooltip).
planningItemsEl.addEventListener('click', (e) => {
  const content = e.target.closest('.planning-content');
  if (!content) return;
  content.classList.toggle('expanded');
});

// --- Plan document panel toggle ---
function setPlanDocumentCollapsed(collapsed) {
  planDocumentPanel.classList.toggle('collapsed', collapsed);
  planDocumentToggle.classList.toggle('collapsed', collapsed);
  planDocumentToggle.setAttribute('aria-expanded', String(!collapsed));
  planDocumentToggle.setAttribute('aria-label', collapsed ? 'Expand panel' : 'Collapse panel');
  planDocumentToggle.title = collapsed ? 'Expand' : 'Collapse';
}

planDocumentToggle.addEventListener('click', () => {
  setPlanDocumentCollapsed(planDocumentPanel.classList.toggle('collapsed'));
});

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
async function connectTab(tab, targetSessionId, workspace) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const params = new URLSearchParams();
  if (workspace) params.set('workspace', workspace);
  // 新建会话时把用户选择的 mode 传给服务端；恢复已有会话不传（用快照 mode）。
  if (targetSessionId === 'new' && tab.mode) params.set('mode', tab.mode);
  const qs = params.toString();
  const wsUrl = `${protocol}//${location.host}/ws/${targetSessionId || 'new'}${qs ? '?' + qs : ''}`;

  return new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    tab.ws = socket;
    socket.onopen = () => {
      bindActiveTab(tab);
      statusEl.textContent = 'connected';
      resolve();
    };
    socket.onmessage = (e) => {
      const event = JSON.parse(e.data);
      handleTabEvent(tab, event);
    };
    socket.onclose = (event) => {
      bindActiveTab(tab);
      if (event.code === 1009) {
        addMessage('error', 'Image message too large. Try a smaller image.');
        tab.sendBtn.disabled = false;
        tab.inFlight = false;
      } else if (tab.inFlight) {
        addMessage('error', 'Connection closed before the message was sent. Reconnect and try again.');
        tab.sendBtn.disabled = false;
        tab.inFlight = false;
      }
      rejectWsUploadWaiters(new Error('connection closed during image upload'));
      statusEl.textContent = tab.shouldReconnect ? 'disconnected' : 'ended';
      if (tab.shouldReconnect) {
        setTimeout(() => connectTab(tab, tab.sessionId, tab.workspace), 2000);
      }
    };
    socket.onerror = () => {
      bindActiveTab(tab);
      statusEl.textContent = 'error';
      reject(new Error('WebSocket error'));
    };
  });
}

// 事件路由到指定 tab：bind 该 tab 后执行原 handleEvent，再写回并恢复原 active。
function handleTabEvent(tab, event) {
  const prevTab = getActiveTab();
  bindActiveTab(tab);
  handleEvent(event);
  syncActiveTab();
  const sid = event && (event.session_id || (event.data && event.data.session_id));
  if (sid && tab.id !== sid) {
    tabs.delete(tab.id);
    tab.id = sid;
    tab.sessionId = sid;
    tabs.set(sid, tab);
  }
  if (prevTab && prevTab !== tab && tabs.has(prevTab.id)) bindActiveTab(prevTab);
}

function handleEvent(event) {
  switch (event.type) {
    case 'session_created':
      sessionId = event.session_id;
      sessionIdEl.textContent = sessionId;
      runIdEl.textContent = 'none';
      syncMode(event.mode || currentMode);
      rememberSessionId(sessionId);
      break;

    case 'session_resumed':
      sessionId = event.session_id;
      sessionIdEl.textContent = sessionId;
      runIdEl.textContent = 'none';
      syncMode(event.mode || currentMode);
      rememberSessionId(sessionId);
      break;

    case 'session_history':
      if (event.data && Array.isArray(event.data.messages)) {
        renderHistory(event.data.messages);
      }
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

    case 'user_question':
      currentAssistantMsg = null;
      renderQuestionCard(event.data || {});
      break;

    case 'user_answer':
      renderQuestionResponse(event.data || {});
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

    case 'image_upload_started':
    case 'image_upload_chunk_ack':
    case 'image_upload_complete':
    case 'image_upload_error':
      handleWsUploadEvent(event);
      break;
  }
}

function syncMode(mode) {
  currentMode = mode || currentMode;
  modeValueEl.textContent = currentMode;
  modeSelectEl.value = currentMode;
  planningItemsEl.textContent = '';
  planningPanel.hidden = true;
  planningCount.hidden = true;
  planningTitle.textContent = currentMode === 'plan' ? 'Plan' : 'Progress';
}

// 记忆最近使用的 session id 与 workspace，刷新/重开页面后优先回到原 session。
function rememberSessionId(sessionId) {
  if (!sessionId) return;
  localStorage.setItem('asterwynd.session_id', sessionId);
  const tab = getActiveTab();
  if (tab && tab.workspace) {
    localStorage.setItem('asterwynd.session_workspace', tab.workspace);
  }
}

function renderHistory(messages) {
  messagesEl.textContent = '';
  for (const message of messages) {
    if (!message || !message.content) continue;
    const role = message.role === 'assistant' ? 'assistant' : 'user';
    addMessage(role, message.content);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
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

function addUserMessage(content, images) {
  const body = addMessage('user', content || '');
  if (images && images.length > 0) {
    appendMessageImages(body, images);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendMessageImages(body, images) {
  const grid = document.createElement('div');
  grid.className = 'message-images';
  images.forEach((image) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'message-image-button';
    button.title = image.name || 'image';
    button.setAttribute('aria-label', `Open ${image.name || 'image'}`);

    const img = document.createElement('img');
    img.src = image.data_url;
    img.alt = image.name || 'uploaded image';
    button.appendChild(img);
    button.addEventListener('click', () => openImageLightbox(image.data_url, image.name || 'uploaded image'));
    grid.appendChild(button);
  });
  body.appendChild(grid);
}

function openImageLightbox(dataUrl, name) {
  let lightbox = document.getElementById('image-lightbox');
  if (!lightbox) {
    lightbox = document.createElement('div');
    lightbox.id = 'image-lightbox';
    lightbox.className = 'image-lightbox';
    lightbox.hidden = true;
    lightbox.setAttribute('role', 'dialog');
    lightbox.setAttribute('aria-modal', 'true');

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'image-lightbox-close';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Close image preview');

    const img = document.createElement('img');
    img.className = 'image-lightbox-img';

    lightbox.appendChild(close);
    lightbox.appendChild(img);
    document.body.appendChild(lightbox);

    close.addEventListener('click', closeImageLightbox);
    lightbox.addEventListener('click', (event) => {
      if (event.target === lightbox) {
        closeImageLightbox();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !lightbox.hidden) {
        closeImageLightbox();
      }
    });
  }

  const img = lightbox.querySelector('.image-lightbox-img');
  img.src = dataUrl;
  img.alt = name;
  lightbox.hidden = false;
}

function closeImageLightbox() {
  const lightbox = document.getElementById('image-lightbox');
  if (!lightbox) return;
  lightbox.hidden = true;
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

function renderQuestionCard(data) {
  const questionId = data.question_id;
  if (!questionId) return;

  const el = document.createElement('div');
  el.className = 'question-card';

  const header = document.createElement('div');
  header.className = 'question-card-header';

  const icon = document.createElement('span');
  icon.className = 'question-icon';
  icon.textContent = '?';
  header.appendChild(icon);

  const title = document.createElement('span');
  title.textContent = data.title || 'Question';
  header.appendChild(title);
  el.appendChild(header);

  if (data.body) {
    const body = document.createElement('div');
    body.className = 'question-card-body';
    if (window.AsterwyndMarkdown && typeof window.AsterwyndMarkdown.render === 'function') {
      body.innerHTML = window.AsterwyndMarkdown.render(data.body);
    } else {
      body.textContent = data.body;
    }
    el.appendChild(body);
  }

  const controls = document.createElement('div');
  controls.className = 'question-controls';

  let inputEl;
  const options = Array.isArray(data.options) ? data.options : [];

  if (options.length > 0) {
    const optionsGroup = document.createElement('div');
    optionsGroup.className = 'question-options-group';
    options.forEach((opt, i) => {
      const label = document.createElement('label');
      label.className = 'question-option';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = `question-${questionId}`;
      radio.value = opt;
      if (i === 0) radio.checked = true;
      label.appendChild(radio);
      label.appendChild(document.createTextNode(' ' + opt));
      optionsGroup.appendChild(label);
    });
    controls.appendChild(optionsGroup);
  } else {
    inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'question-text-input';
    inputEl.placeholder = 'Type your answer...';
    controls.appendChild(inputEl);
  }

  const submitBtn = document.createElement('button');
  submitBtn.type = 'button';
  submitBtn.className = 'question-submit';
  submitBtn.textContent = 'Submit';
  submitBtn.addEventListener('click', () => {
    let answer = '';
    if (options.length > 0) {
      const checked = controls.querySelector(`input[name="question-${questionId}"]:checked`);
      answer = checked ? checked.value : '';
    } else if (inputEl) {
      answer = inputEl.value.trim();
    }
    if (!answer) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitted';
    sendQuestionAnswer(questionId, answer);
  });

  controls.appendChild(submitBtn);
  el.appendChild(controls);

  messagesEl.appendChild(el);
  questionCards.set(questionId, { el, submitBtn });
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function sendQuestionAnswer(questionId, answer) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'user_answer',
    question_id: questionId,
    answer,
  }));
}

function renderQuestionResponse(data) {
  const questionId = data.question_id;
  const card = questionCards.get(questionId);
  if (!card) return;
  card.submitBtn.disabled = true;
  card.submitBtn.textContent = data.status === 'received' ? 'Received' : 'Unavailable';
}

function renderPlanningState(state) {
  const items = state && Array.isArray(state.items) ? state.items : [];
  planningItemsEl.textContent = '';

  if (items.length === 0) {
    planningPanel.hidden = true;
    return;
  }

  planningTitle.textContent = 'Plan';
  planningCount.textContent = items.length;
  planningPanel.hidden = false;

  const wasCollapsed = planningPanel.classList.contains('collapsed');
  const statusLabels = { pending: '○', in_progress: '▶', completed: '✓', failed: '✗', skipped: '⏭' };

  for (const item of items) {
    const row = document.createElement('li');
    row.className = `planning-item status-${item.status}`;

    const status = document.createElement('span');
    status.className = 'planning-status';
    status.textContent = statusLabels[item.status] || item.status;

    const content = document.createElement('span');
    content.className = 'planning-content';
    content.textContent = item.content || '';
    content.title = item.content || '';

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

  // Restore collapsed state
  if (wasCollapsed) {
    setPlanningPanelCollapsed(true);
  }
}

function renderTodoState(state) {
  const items = state && Array.isArray(state.items) ? state.items : [];
  planningItemsEl.textContent = '';

  if (items.length === 0) {
    planningPanel.hidden = true;
    return;
  }

  planningTitle.textContent = 'Progress';
  planningCount.textContent = items.length;
  planningPanel.hidden = false;

  const wasCollapsed = planningPanel.classList.contains('collapsed');
  const statusLabels = { pending: '○', in_progress: '▶', completed: '✓' };
  for (const item of items) {
    const row = document.createElement('li');
    row.className = `planning-item status-${item.status}`;

    const status = document.createElement('span');
    status.className = 'planning-status';
    status.textContent = statusLabels[item.status] || item.status;

    const content = document.createElement('span');
    content.className = 'planning-content';
    content.textContent = item.content || '';
    content.title = item.content || '';

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

  // Restore collapsed state
  if (wasCollapsed) {
    setPlanningPanelCollapsed(true);
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

  const wasCollapsed = planDocumentPanel.classList.contains('collapsed');
  planDocumentPanel.hidden = false;
  const status = document && document.status === 'submitted' ? 'Submitted' : 'Draft';
  planDocumentTitleEl.textContent = title ? `${status}: ${title}` : status;
  planDocumentBodyEl.dataset.markdownSource = markdown;
  if (window.AsterwyndMarkdown && typeof window.AsterwyndMarkdown.render === 'function') {
    planDocumentBodyEl.innerHTML = window.AsterwyndMarkdown.render(markdown);
  } else {
    planDocumentBodyEl.textContent = markdown;
  }
  // Restore collapsed state
  if (wasCollapsed) {
    setPlanDocumentCollapsed(true);
  }
}

// --- Image upload ---
// 上传按钮 / file input 的绑定在 buildTabPane 内（per-tab）；这里用委托处理
// 全局的 paste 与拖拽，路由到焦点所在的 tab pane。
document.addEventListener('paste', (e) => {
  const active = document.activeElement;
  const pane = active && active.closest ? active.closest('.tab-pane') : null;
  if (!pane) return;
  const tab = tabs.get(pane.dataset.tabId);
  if (!tab) return;
  switchTab(tab.id);
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      addImageFromFile(item.getAsFile());
    }
  }
});

// Drag and drop：委托到 chat-panes（tab pane 的 input-area 都在里面）
const dragPaneState = { pane: null, counter: 0 };

chatPanesEl.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
});

chatPanesEl.addEventListener('dragenter', (e) => {
  e.preventDefault();
  e.stopPropagation();
  const pane = e.target.closest ? e.target.closest('.tab-pane') : null;
  if (pane) {
    if (dragPaneState.pane !== pane) {
      dragPaneState.pane = pane;
      dragPaneState.counter = 0;
    }
    dragPaneState.counter++;
    pane.classList.add('drag-over');
  }
});

chatPanesEl.addEventListener('dragleave', (e) => {
  e.preventDefault();
  e.stopPropagation();
  const pane = e.target.closest ? e.target.closest('.tab-pane') : null;
  if (pane && dragPaneState.pane === pane) {
    dragPaneState.counter--;
    if (dragPaneState.counter <= 0) {
      dragPaneState.counter = 0;
      dragPaneState.pane = null;
      pane.classList.remove('drag-over');
    }
  }
});

chatPanesEl.addEventListener('drop', (e) => {
  e.preventDefault();
  e.stopPropagation();
  const pane = e.target.closest ? e.target.closest('.tab-pane') : null;
  if (pane) {
    dragPaneState.pane = null;
    dragPaneState.counter = 0;
    pane.classList.remove('drag-over');
    const tab = tabs.get(pane.dataset.tabId);
    if (tab) {
      switchTab(tab.id);
      const files = e.dataTransfer && e.dataTransfer.files;
      if (!files || files.length === 0) return;
      for (const file of files) {
        if (isImageFile(file)) {
          addImageFromFile(file);
        }
      }
    }
  }
});

async function addImageFromFile(file) {
  if (!isImageFile(file)) return;
  if (file.size > MAX_IMAGE_FILE_BYTES) {
    addMessage('error', 'Image too large (max 20MB)');
    return;
  }
  try {
    const dataUrl = await prepareImageForSend(file);
    const pendingImage = {
      data_url: dataUrl,
      name: file.name,
      upload_id: null,
      upload_error: null,
      upload_promise: null,
    };
    pendingImages.push(pendingImage);
    renderImagePreviews();
    pendingImage.upload_promise = uploadImageDataUrl(dataUrl, file.name)
      .then(result => {
        pendingImage.upload_id = result.upload_id;
        return result;
      })
      .catch(error => {
        pendingImage.upload_error = error;
        throw error;
      })
      .finally(renderImagePreviews);
  } catch (e) {
    addMessage('error', `Failed to read image: ${e.message}`);
  }
}

async function prepareImageForSend(file) {
  const type = normalizedImageType(file);
  if (type === 'image/gif') {
    return readFileAsDataUrl(file);
  }
  if (SUPPORTED_IMAGE_TYPES.has(type) && file.size <= IMAGE_NORMALIZE_THRESHOLD_BYTES) {
    return readFileAsDataUrl(file);
  }
  return convertImageToJpegDataUrl(file);
}

function isImageFile(file) {
  if (!file) return false;
  if (file.type && file.type.startsWith('image/')) return true;
  return /\.(png|jpe?g|gif|webp|heic|heif)$/i.test(file.name || '');
}

function normalizedImageType(file) {
  const type = (file.type || '').toLowerCase();
  if (type) return type;
  const name = (file.name || '').toLowerCase();
  if (name.endsWith('.heic')) return 'image/heic';
  if (name.endsWith('.heif')) return 'image/heif';
  if (name.endsWith('.jpg') || name.endsWith('.jpeg')) return 'image/jpeg';
  if (name.endsWith('.png')) return 'image/png';
  if (name.endsWith('.gif')) return 'image/gif';
  if (name.endsWith('.webp')) return 'image/webp';
  return '';
}

async function convertImageToJpegDataUrl(file) {
  const source = await decodeImageForCanvas(file);
  const maxSide = Math.max(source.width || 0, source.height || 0);
  if (!maxSide) {
    closeImageSource(source);
    throw new Error('Unable to read image dimensions');
  }
  const scale = Math.min(1, MAX_NORMALIZED_IMAGE_SIDE / maxSide);
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    closeImageSource(source);
    throw new Error('Canvas is not available');
  }
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source, 0, 0, width, height);
  closeImageSource(source);
  const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
  if (!dataUrl || dataUrl === 'data:,') {
    throw new Error('Failed to convert image');
  }
  return dataUrl;
}

async function decodeImageForCanvas(file) {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file);
    } catch (e) {
      // Fall back to HTMLImageElement decoding below.
    }
  }
  const dataUrl = await readFileAsDataUrl(file);
  return loadImageElement(dataUrl, file);
}

function loadImageElement(dataUrl, file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => {
      if (HEIC_IMAGE_TYPES.has(normalizedImageType(file))) {
        reject(new Error('HEIC image could not be decoded by this browser. Choose a JPEG/PNG image or set iPhone Camera Formats to Most Compatible.'));
      } else {
        reject(new Error('Failed to decode image'));
      }
    };
    img.src = dataUrl;
  });
}

function closeImageSource(source) {
  if (source && typeof source.close === 'function') {
    source.close();
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

async function uploadImageDataUrl(dataUrl, name) {
  const blob = dataUrlToBlob(dataUrl);
  const formData = new FormData();
  formData.append('file', blob, name || `upload.${blob.type.split('/')[1] || 'jpg'}`);
  let response;
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  let timeoutId = null;
  try {
    if (controller) {
      timeoutId = setTimeout(() => controller.abort(), HTTP_UPLOAD_TIMEOUT_MS);
    }
    response = await fetch('/api/uploads', {
      method: 'POST',
      body: formData,
      signal: controller ? controller.signal : undefined,
    });
  } catch (error) {
    return uploadImageDataUrlOverWebSocket(dataUrl, name, error);
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
  }
  let result = {};
  try {
    result = await response.json();
  } catch (e) {
    result = {};
  }
  if (!response.ok) {
    throw new Error(result.error || `upload failed (${response.status})`);
  }
  if (!result.upload_id) {
    throw new Error('upload response missing upload_id');
  }
  return result;
}

async function uploadImageDataUrlOverWebSocket(dataUrl, name, originalError) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    throw originalError || new Error('connection is not ready');
  }
  const parsed = parseDataUrl(dataUrl);
  const clientUploadId = (
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  );

  ws.send(JSON.stringify({
    type: 'image_upload_start',
    client_upload_id: clientUploadId,
    name: name || 'upload',
    mime: parsed.mime,
    total_chars: parsed.base64.length,
  }));
  await waitForWsUploadEvent(clientUploadId, new Set(['image_upload_started']));

  for (let offset = 0, index = 0; offset < parsed.base64.length; offset += WS_UPLOAD_CHUNK_CHARS, index++) {
    ws.send(JSON.stringify({
      type: 'image_upload_chunk',
      client_upload_id: clientUploadId,
      index,
      chunk: parsed.base64.slice(offset, offset + WS_UPLOAD_CHUNK_CHARS),
    }));
    await waitForWsUploadEvent(clientUploadId, new Set(['image_upload_chunk_ack']));
  }

  ws.send(JSON.stringify({
    type: 'image_upload_finish',
    client_upload_id: clientUploadId,
  }));
  return waitForWsUploadEvent(clientUploadId, new Set(['image_upload_complete']));
}

function dataUrlToBlob(dataUrl) {
  const parsed = parseDataUrl(dataUrl);
  const binary = atob(parsed.base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: parsed.mime });
}

function parseDataUrl(dataUrl) {
  const parts = dataUrl.split(',');
  if (parts.length !== 2 || !parts[0].startsWith('data:')) {
    throw new Error('invalid image data');
  }
  const mime = parts[0].slice(5).split(';')[0] || 'image/jpeg';
  return { mime, base64: parts[1] };
}

function waitForWsUploadEvent(clientUploadId, expectedTypes, timeoutMs = WS_UPLOAD_EVENT_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      wsUploadWaiters.delete(clientUploadId);
      reject(new Error('image upload timed out'));
    }, timeoutMs);
    wsUploadWaiters.set(clientUploadId, {
      expectedTypes,
      resolve: (data) => {
        clearTimeout(timer);
        resolve(data);
      },
      reject: (error) => {
        clearTimeout(timer);
        reject(error);
      },
    });
  });
}

function handleWsUploadEvent(event) {
  const data = event.data || {};
  const clientUploadId = data.client_upload_id || '';
  const waiter = wsUploadWaiters.get(clientUploadId);
  if (!waiter) return;
  if (event.type === 'image_upload_error') {
    wsUploadWaiters.delete(clientUploadId);
    waiter.reject(new Error(data.message || 'image upload failed'));
    return;
  }
  if (!waiter.expectedTypes.has(event.type)) return;
  wsUploadWaiters.delete(clientUploadId);
  waiter.resolve(data);
}

function rejectWsUploadWaiters(error) {
  for (const [clientUploadId, waiter] of wsUploadWaiters.entries()) {
    wsUploadWaiters.delete(clientUploadId);
    waiter.reject(error);
  }
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
    if (img.upload_error) {
      thumb.classList.add('upload-error');
      thumb.title = img.upload_error.message || 'Upload failed';
    } else if (!img.upload_id) {
      thumb.classList.add('uploading');
      thumb.title = 'Uploading image';
    }
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
  if (!text && !hasImages) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    addMessage('error', 'Connection is not ready. Reconnect and try again.');
    sendBtn.disabled = false;
    statusEl.textContent = 'disconnected';
    return;
  }

  hideSlashSuggestions();
  let sentImages = [];

  if (hasImages) {
    statusEl.textContent = 'uploading image...';
    sendBtn.disabled = true;
    try {
      await waitForPendingImageUploads();
    } catch (e) {
      addMessage('error', `Image upload failed: ${e.message}`);
      sendBtn.disabled = false;
      statusEl.textContent = 'connected';
      return;
    }
    sentImages = pendingImages.map(img => ({
      data_url: img.data_url,
      name: img.name || 'pasted',
      upload_id: img.upload_id,
    }));
  }

  const payload = { type: 'chat', content: text || '' };
  if (hasImages) {
    payload.images = sentImages.map(img => ({ upload_id: img.upload_id }));
  }
  const payloadJson = JSON.stringify(payload);
  if (payloadJson.length > MAX_CHAT_PAYLOAD_CHARS) {
    addMessage('error', 'Image message too large. Try a smaller image.');
    sendBtn.disabled = false;
    statusEl.textContent = 'connected';
    return;
  }

  if (hasImages) {
    addUserMessage(text, sentImages);
  } else {
    addMessage('user', text);
  }

  userInput.value = '';
  sendBtn.disabled = true;
  sendInFlight = true;
  statusEl.textContent = text.startsWith('/') ? 'running command...' : 'thinking...';

  if (hasImages) {
    pendingImages = [];
    renderImagePreviews();
  }
  ws.send(payloadJson);
}

async function waitForPendingImageUploads() {
  for (const img of pendingImages) {
    if (img.upload_error) {
      throw img.upload_error;
    }
    if (img.upload_promise) {
      await img.upload_promise;
    }
    if (img.upload_error) {
      throw img.upload_error;
    }
    if (!img.upload_id) {
      throw new Error('image upload did not finish');
    }
  }
}

function sendModeChange() {
  const nextMode = modeSelectEl.value;
  if (!ws || ws.readyState !== WebSocket.OPEN || !nextMode || nextMode === currentMode) {
    return;
  }
  ws.send(JSON.stringify({ type: 'set_mode', mode: nextMode }));
}

modeApplyBtn.addEventListener('click', sendModeChange);

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
    sendInFlight = false;
    sendBtn.disabled = !shouldReconnect;
    statusEl.textContent = shouldReconnect ? 'connected' : 'ended';
  }
};

// --- Hub view (issue #117) ---
async function loadHub() {
  try {
    const wsResp = await fetch('/api/workspaces');
    const wsData = await wsResp.json();
    const workspaces = Array.isArray(wsData.workspaces) ? wsData.workspaces : [];
    const options = workspaces.map(w => {
      const opt = document.createElement('option');
      opt.value = w.path;
      opt.textContent = w.is_primary ? `${w.path} (primary)` : w.path;
      return opt;
    });
    hubWorkspaceSelect.textContent = '';
    hubNewWorkspace.textContent = '';
    for (const opt of options) {
      hubWorkspaceSelect.appendChild(opt.cloneNode(true));
      hubNewWorkspace.appendChild(opt.cloneNode(true));
    }
    renderSessionList();
  } catch (e) {
    hubSessionList.innerHTML = '<div class="hub-empty">加载失败</div>';
  }
}

async function renderSessionList() {
  const workspace = hubWorkspaceSelect.value;
  try {
    const resp = await fetch(`/api/sessions?workspace=${encodeURIComponent(workspace)}`);
    if (!resp.ok) {
      hubSessionList.innerHTML = '<div class="hub-empty">workspace 不可用</div>';
      return;
    }
    const data = await resp.json();
    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    hubListCount.textContent = `${sessions.length} 个`;
    hubSessionList.textContent = '';
    if (sessions.length === 0) {
      hubSessionList.innerHTML = '<div class="hub-empty">暂无会话，新建一个开始</div>';
      return;
    }
    for (const s of sessions) {
      const row = document.createElement('div');
      row.className = 'hub-session-row';
      row.title = `session ${s.session_id}`;
      const info = document.createElement('div');
      info.className = 'hub-session-info';
      const idLine = document.createElement('div');
      idLine.className = 'hub-session-id';
      idLine.textContent = s.session_id;
      const meta = document.createElement('div');
      meta.className = 'hub-session-meta';
      meta.textContent = `mode=${s.mode} · ${s.messages} msgs · ${new Date(s.updated_at).toLocaleString()}`;
      info.appendChild(idLine);
      info.appendChild(meta);
      const openBtn = document.createElement('button');
      openBtn.type = 'button';
      openBtn.className = 'hub-session-open';
      openBtn.textContent = '打开';
      openBtn.addEventListener('click', () => openSessionTab(s.session_id, workspace));
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'hub-session-delete';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', async () => {
        if (!confirm(`删除会话 ${s.session_id}？`)) return;
        try {
          await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}?workspace=${encodeURIComponent(workspace)}`, { method: 'DELETE' });
          closeTab(s.session_id);
          renderSessionList();
        } catch (e) {
          alert('删除失败');
        }
      });
      const actions = document.createElement('div');
      actions.className = 'hub-session-actions';
      actions.appendChild(openBtn);
      actions.appendChild(delBtn);
      row.appendChild(info);
      row.appendChild(actions);
      hubSessionList.appendChild(row);
    }
  } catch (e) {
    hubSessionList.innerHTML = '<div class="hub-empty">加载失败</div>';
  }
}

function setupHub() {
  hubWorkspaceSelect.addEventListener('change', renderSessionList);
  hubNewBtn.addEventListener('click', () => {
    const mode = hubNewMode.value;
    const workspace = hubNewWorkspace.value;
    const tab = createTab('new', null, workspace, mode);
    buildTabPane(tab);
    switchTab(tab.id);
    connectTab(tab, 'new', workspace).catch(() => {
      statusEl.textContent = 'connection failed';
    });
  });
}

// --- Init ---
async function init() {
  // 初始 session 优先级：URL ?session=<id>（显式恢复，可带 ?workspace=）→
  // localStorage 记忆的最近会话（刷新恢复）→ hub（无默认会话则展示列表）。
  const urlParams = new URLSearchParams(location.search);
  const urlSession = urlParams.get('session');
  const urlWorkspace = urlParams.get('workspace') || null;
  const rememberedSession = localStorage.getItem('asterwynd.session_id');
  const rememberedWorkspace = localStorage.getItem('asterwynd.session_workspace') || null;

  try {
    const commandResp = await fetch('/api/slash-commands');
    const commandCatalog = await commandResp.json();
    slashCommands = Array.isArray(commandCatalog.commands) ? commandCatalog.commands : [];
    const resp = await fetch('/api/debug-status');
    const dbg = await resp.json();
    if (dbg.enabled) {
      debugTabBtn.style.display = '';
    }
  } catch (e) {
    // 忽略：hub 仍可渲染
  }

  // 视图 tab 切换（Sessions / Chat / Debug）
  document.querySelectorAll('.tab[data-tab]').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      const target = tabBtn.dataset.tab;
      document.querySelectorAll('.tab[data-tab]').forEach(t => t.classList.toggle('active', t === tabBtn));
      hubViewEl.classList.toggle('active', target === 'hub');
      chatViewEl.classList.toggle('active', target === 'chat');
      document.getElementById('debug-view').classList.toggle('active', target === 'debug');
      activeView = target;
      if (target === 'hub') loadHub();
      if (target === 'debug' && typeof renderTimeline === 'function') renderTimeline();
    });
  });
  setupHub();

  const targetSession = urlSession || rememberedSession;
  if (targetSession) {
    const workspace = urlWorkspace || rememberedWorkspace;
    const tab = createTab(targetSession, targetSession, workspace, 'build');
    buildTabPane(tab);
    switchTab(targetSession);
    try {
      await connectTab(tab, targetSession, workspace);
    } catch (e) {
      statusEl.textContent = 'connection failed';
    }
  } else {
    showHub();
  }
}

init();
