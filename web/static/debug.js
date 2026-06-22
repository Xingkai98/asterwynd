// web/static/debug.js
// Debug UI: renders iteration-by-iteration message assembly view

const debugContent = document.getElementById('debug-content');
let iterBlocks = {};

const PHASE_LABELS = {
  before_iteration: { icon: '📤', label: '发送给 LLM 的消息', cls: 'send' },
  after_llm_call:    { icon: '📥', label: 'LLM 响应', cls: 'response' },
  before_tool_execute: { icon: '🔧', label: '工具调用（执行前）', cls: 'tool-pre' },
  after_tool_execute:  { icon: '✅', label: '工具结果', cls: 'tool-post' },
  on_error:          { icon: '❌', label: '错误', cls: 'error' },
  on_completion:     { icon: '🏁', label: '完成', cls: 'done' },
  memory_compaction: { icon: '🗜️', label: 'Memory 压缩', cls: 'memory' },
  planning_state_updated: { icon: '📋', label: 'Planning State', cls: 'planning' },
};

function renderDebug() {
  for (const [eventIndex, event] of debugEvents.entries()) {
    if (event.type !== 'debug') continue;
    const iter = event.iteration;
    const turn = event.turn || 1;
    const phase = event.phase;
    const blockKey = `${turn}:${iter}`;

    if (!iterBlocks[blockKey]) {
      iterBlocks[blockKey] = createIterationBlock(turn, iter);
      debugContent.appendChild(iterBlocks[blockKey].el);
    }

    const block = iterBlocks[blockKey];
    if (block.renderedEvents.has(eventIndex)) continue;
    block.renderedEvents.add(eventIndex);

    const section = renderPhase(phase, event.data);
    block.body.appendChild(section);
  }
  debugContent.scrollTop = debugContent.scrollHeight;
}

function createIterationBlock(turn, iteration) {
  const el = document.createElement('div');
  el.className = 'iteration-block';

  const header = document.createElement('div');
  header.className = 'iteration-header';
  header.innerHTML = `第 ${turn} 次对话 · 第 ${iteration + 1} 轮迭代 <span>▶</span>`;
  header.addEventListener('click', () => {
    body.classList.toggle('collapsed');
    header.querySelector('span').textContent = body.classList.contains('collapsed') ? '▶' : '▼';
  });

  const body = document.createElement('div');
  body.className = 'iteration-body';

  el.appendChild(header);
  el.appendChild(body);

  return { el, body, renderedEvents: new Set() };
}

function renderPhase(phase, data) {
  const section = document.createElement('div');
  section.className = 'debug-section';

  const info = PHASE_LABELS[phase] || { icon: '📋', label: phase, cls: '' };
  const header = document.createElement('div');
  header.className = 'debug-section-header';
  header.innerHTML = `<span class="phase-icon">${info.icon}</span> ${info.label}`;
  section.appendChild(header);

  const body = document.createElement('div');
  body.className = 'debug-section-body';
  section.appendChild(body);

  switch (phase) {
    case 'before_iteration':
      body.appendChild(renderMessagesTable(data.messages || []));
      break;
    case 'after_llm_call':
      body.appendChild(renderLLMResponse(data));
      break;
    case 'before_tool_execute':
      body.appendChild(renderToolCallPre(data));
      break;
    case 'after_tool_execute':
      body.appendChild(renderToolCallResult(data));
      break;
    case 'on_error':
      body.innerHTML = `<span style="color:var(--error)">${esc(data.error_type)}: ${esc(data.error_message)}</span>`;
      break;
    case 'on_completion':
      body.innerHTML = `<div>stop_reason: <strong>${esc(data.stop_reason)}</strong></div>
                        <div>content: <pre style="margin-top:6px;white-space:pre-wrap">${esc(data.content || '')}</pre></div>
                        <div>tool_calls_made: ${data.tool_calls_made}</div>`;
      break;
    case 'memory_compaction':
      body.innerHTML = `<div>当前上下文消息总数: <strong>${data.total_messages}</strong></div>`;
      break;
    case 'planning_state_updated':
      body.appendChild(renderPlanningDebugTable(data));
      break;
    default:
      body.textContent = JSON.stringify(data, null, 2);
  }

  return section;
}

function renderPlanningDebug(data) {
  const section = renderPhase('planning_state_updated', data);
  debugContent.appendChild(section);
  debugContent.scrollTop = debugContent.scrollHeight;
}

function renderPlanningDebugTable(data) {
  const items = data && Array.isArray(data.items) ? data.items : [];
  if (items.length === 0) {
    const el = document.createElement('div');
    el.textContent = '(empty planning state)';
    el.style.cssText = 'color:var(--text2);font-style:italic';
    return el;
  }

  const table = document.createElement('table');
  table.className = 'msg-table planning-debug-table';
  table.innerHTML = `<thead><tr>
    <th style="width:84px">Status</th>
    <th>Content</th>
    <th>Note</th>
  </tr></thead>`;
  const tbody = document.createElement('tbody');
  for (const item of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="planning-status status-${esc(item.status)}">${esc(item.status)}</span></td>
      <td>${esc(item.content || '')}</td>
      <td>${esc(item.note || '')}</td>`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return table;
}

function renderMessagesTable(messages) {
  if (!messages || messages.length === 0) {
    const el = document.createElement('div');
    el.textContent = '(空消息列表)';
    el.style.cssText = 'color:var(--text2);font-style:italic';
    return el;
  }
  const table = document.createElement('table');
  table.className = 'msg-table';
  table.innerHTML = `<thead><tr>
    <th style="width:36px">#</th>
    <th style="width:64px">Role</th>
    <th>Content</th>
  </tr></thead>`;
  const tbody = document.createElement('tbody');
  messages.forEach((m, i) => {
    const tr = document.createElement('tr');
    const roleClass = `role-${m.role}`;
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td><span class="role-badge ${roleClass}">${m.role}</span></td>
      <td>${esc(m.content || '')}</td>`;
    // Show tool_calls if present
    if (m.tool_calls && m.tool_calls.length > 0) {
      let tcInfo = '';
      for (const tc of m.tool_calls) {
        tcInfo += `\n→ tool_call: ${tc.name}(${tc.arguments})`;
      }
      tr.querySelector('td:last-child').innerHTML += `<pre style="margin-top:4px;color:var(--info);white-space:pre-wrap;font-size:0.75rem">${esc(tcInfo.trim())}</pre>`;
    }
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

function renderLLMResponse(data) {
  const el = document.createElement('div');
  let html = `<div><strong>stop_reason:</strong> ${esc(data.stop_reason || 'N/A')}</div>`;
  if (data.content) {
    html += `<div style="margin-top:6px"><strong>content:</strong></div>
             <pre style="background:var(--bg);padding:8px;border-radius:4px;margin-top:4px;white-space:pre-wrap">${esc(data.content)}</pre>`;
  }
  if (data.tool_calls && data.tool_calls.length > 0) {
    html += '<div style="margin-top:6px"><strong>tool_calls:</strong></div>';
    for (const tc of data.tool_calls) {
      html += `<div class="tool-event" style="margin-top:4px">
        <span class="name">${esc(tc.name)}</span>
        (<span style="color:var(--text2)">${esc(tc.id)}</span>)
        <pre style="background:var(--bg);padding:4px 8px;margin-top:4px;border-radius:3px">${esc(tc.arguments)}</pre>
      </div>`;
    }
  }
  el.innerHTML = html;
  return el;
}

function renderToolCallPre(data) {
  const el = document.createElement('div');
  el.className = 'tool-event';
  el.innerHTML = `<span class="name">${esc(data.tool_name)}</span>
    <pre style="background:var(--bg);padding:4px 8px;margin-top:4px;border-radius:3px">${esc(JSON.stringify(data.arguments, null, 2))}</pre>`;
  return el;
}

function renderToolCallResult(data) {
  const el = document.createElement('div');
  el.className = 'tool-event';
  el.innerHTML = `<span class="name">${esc(data.tool_name)}</span> → result:
    <pre style="background:var(--bg);padding:4px 8px;margin-top:4px;border-radius:3px;white-space:pre-wrap">${esc(data.result)}</pre>`;
  return el;
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
