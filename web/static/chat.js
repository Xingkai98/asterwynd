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
const questionCards = new Map();
let pendingImages = [];
let sendInFlight = false;
const wsUploadWaiters = new Map();
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
    ws.onclose = (event) => {
      if (event.code === 1009) {
        addMessage('error', 'Image message too large. Try a smaller image.');
        sendBtn.disabled = false;
        sendInFlight = false;
      } else if (sendInFlight) {
        addMessage('error', 'Connection closed before the message was sent. Reconnect and try again.');
        sendBtn.disabled = false;
        sendInFlight = false;
      }
      rejectWsUploadWaiters(new Error('connection closed during image upload'));
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
    if (isImageFile(file)) {
      addImageFromFile(file);
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
    sendInFlight = false;
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
