// web/static/group.js
// 群聊 pane（change web-agent-group-chat）：人设/房间管理 + 房间级 WebSocket。
//
// 关键设计：
//  - 群聊**不复用** per-session 的 Chat pane 事件通道：现有 WS 路由按 session 绑定
//    （`/ws/${sessionId}`），房间是「多成员会话的聚合」，需要房间级 WS
//    （`/ws/room/${roomId}`）才能拿到有序的房间时间线（Decision 6）。
//  - 不同 agent 的消息必须**可见地**来自不同 agent（spec「多 agent 消息按来源区分」）：
//    每条 post 渲染发言者名字 + 首字母色块，绝不与用户消息混同。
(function () {
  const state = {
    workspace: null,
    personas: [],
    mainBotIds: [],
    rooms: [],
    activeRoom: null,
    ws: null,
    members: [],
    timeline: [],
    speaking: null,
    els: {},
  };

  function el(id) {
    return document.getElementById(id);
  }

  function workspaceParam() {
    // 复用 hub 的 workspace 选择（同一页面共享一个「当前 workspace」概念）。
    const select = el('hub-workspace-select');
    const value = select && select.value ? select.value : '';
    return value || state.workspace || '';
  }

  async function api(path, options) {
    const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
    const resp = await fetch(path, opts);
    let body = null;
    try {
      body = await resp.json();
    } catch (err) {
      body = null;
    }
    if (!resp.ok) {
      const message = (body && (body.error || body.detail)) || resp.statusText;
      throw new Error(message);
    }
    return body;
  }

  function withWorkspace(path, extra) {
    const params = new URLSearchParams(extra || {});
    const ws = workspaceParam();
    if (ws) params.set('workspace', ws);
    const qs = params.toString();
    return qs ? `${path}?${qs}` : path;
  }

  function applyState(body) {
    if (!body) return;
    state.workspace = body.workspace || state.workspace;
    if (body.personas) state.personas = body.personas;
    if (body.main_bot_ids) state.mainBotIds = body.main_bot_ids;
    if (body.rooms) state.rooms = body.rooms;
    if (state.activeRoom) {
      const still = state.rooms.find(r => r.id === state.activeRoom.id);
      state.activeRoom = still || null;
      if (!still) closeRoom();
    }
    renderSidebar();
  }

  async function refresh() {
    try {
      applyState(await api(withWorkspace('/api/team')));
    } catch (err) {
      setStatus(`加载失败：${err.message}`);
    }
  }

  // ---------------------------------------------------------------- 侧栏

  function renderSidebar() {
    const list = el('group-persona-list');
    const roomList = el('group-room-list');
    if (!list || !roomList) return;
    list.textContent = '';
    state.personas.forEach(persona => {
      const li = document.createElement('li');
      li.className = 'group-item';
      const name = document.createElement('button');
      name.type = 'button';
      name.className = 'group-item-name';
      name.textContent = persona.name || persona.id;
      const badges = [];
      if (state.mainBotIds.includes(persona.id)) badges.push('Chief');
      name.title = [persona.role, persona.model, ...badges].filter(Boolean).join(' · ');
      if (state.mainBotIds.includes(persona.id)) {
        const badge = document.createElement('span');
        badge.className = 'group-badge';
        badge.textContent = 'Chief';
        name.appendChild(badge);
      }
      // 进入人设单聊：单聊就是普通 Chat 会话（各自独立 AgentSession）。
      name.addEventListener('click', () => openPersonaChat(persona.id));
      li.appendChild(name);

      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'group-item-action';
      edit.textContent = '设置';
      edit.addEventListener('click', (e) => {
        e.stopPropagation();
        openPersonaDialog(persona);
      });
      li.appendChild(edit);

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'group-item-action danger';
      del.textContent = '删除';
      del.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!window.confirm(`删除人设「${persona.name}」？其单聊会话、全部记忆与各群成员身份都会被清理。`)) return;
        try {
          applyState(await api(
            withWorkspace(`/api/team/personas/${persona.id}`),
            { method: 'DELETE' },
          ));
        } catch (err) {
          setStatus(`删除失败：${err.message}`);
        }
      });
      li.appendChild(del);
      list.appendChild(li);
    });

    roomList.textContent = '';
    state.rooms.forEach(room => {
      const li = document.createElement('li');
      li.className = 'group-item';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'group-item-name';
      btn.textContent = room.name || room.id;
      btn.title = `${room.members.length} 名成员`;
      if (state.activeRoom && state.activeRoom.id === room.id) btn.classList.add('active');
      btn.addEventListener('click', () => openRoom(room.id));
      li.appendChild(btn);
      roomList.appendChild(li);
    });
  }

  // ---------------------------------------------------------------- 单聊

  async function openPersonaChat(personaId) {
    try {
      const body = await api(withWorkspace(`/api/team/personas/${personaId}/chat`));
      if (window.AsterwyndOpenSession) {
        window.AsterwyndOpenSession(body.session_id, body.workspace);
        if (window.AsterwyndShowView) window.AsterwyndShowView('chat');
      }
    } catch (err) {
      setStatus(`进入单聊失败：${err.message}`);
    }
  }

  // ---------------------------------------------------------------- 房间

  function closeRoom() {
    if (state.ws) {
      state.ws.onclose = null;
      state.ws.close();
      state.ws = null;
    }
    state.activeRoom = null;
    state.members = [];
    state.timeline = [];
    state.speaking = null;
    const room = el('group-room');
    if (room) room.hidden = true;
    const empty = el('group-empty');
    if (empty) empty.hidden = false;
    renderSidebar();
  }

  async function openRoom(roomId) {
    let stateBody;
    try {
      stateBody = await api(withWorkspace(`/api/team/rooms/${roomId}/timeline`));
    } catch (err) {
      setStatus(`打开群聊失败：${err.message}`);
      return;
    }
    state.activeRoom = stateBody.room;
    state.members = stateBody.members || [];
    state.timeline = stateBody.timeline || [];
    state.speaking = null;
    el('group-room').hidden = false;
    el('group-empty').hidden = true;
    renderRoom();
    renderSidebar();
    connectRoom(state.activeRoom.id);
  }

  function connectRoom(roomId) {
    if (state.ws) {
      state.ws.onclose = null;
      state.ws.close();
      state.ws = null;
    }
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = workspaceParam();
    const url = `${protocol}//${location.host}/ws/room/${roomId}${ws ? '?workspace=' + encodeURIComponent(ws) : ''}`;
    const socket = new WebSocket(url);
    state.ws = socket;
    socket.onopen = () => setStatus('已连接');
    socket.onmessage = (e) => {
      let event;
      try {
        event = JSON.parse(e.data);
      } catch (err) {
        return;
      }
      handleRoomEvent(event);
    };
    socket.onclose = () => {
      if (state.activeRoom && state.activeRoom.id === roomId) {
        setStatus('连接断开，重连中...');
        setTimeout(() => {
          if (state.activeRoom && state.activeRoom.id === roomId) connectRoom(roomId);
        }, 2000);
      }
    };
  }

  function handleRoomEvent(event) {
    const data = event.data || {};
    switch (event.type) {
      case 'room_state':
        state.activeRoom = data.room || state.activeRoom;
        state.members = data.members || state.members;
        state.timeline = data.timeline || [];
        state.speaking = null;
        renderRoom();
        break;
      case 'user_message':
        state.timeline.push({ seq: data.seq, speaker: 'user', kind: 'user', text: data.text, ts: '' });
        renderRoom();
        break;
      case 'member_speaking':
        state.speaking = data.persona_id;
        setStatus(`${data.name || data.persona_id} 正在发言...`);
        renderMembers();
        break;
      case 'member_post':
        state.speaking = null;
        state.timeline.push({
          seq: data.seq, speaker: data.speaker, kind: 'post', text: data.text, ts: '',
        });
        renderRoom();
        break;
      case 'member_silent':
        state.speaking = null;
        renderMembers();
        break;
      case 'member_failed':
        state.speaking = null;
        state.timeline.push({
          seq: null, speaker: null, kind: 'system',
          text: `${data.persona_id} 运行失败：${data.reason || ''}`, ts: '',
        });
        renderRoom();
        break;
      case 'round_ended':
        state.speaking = null;
        setStatus(data.termination === 'limit' ? '本轮因达上限结束' : '本轮结束');
        // 达上限那一轮会补一条 system 条目：重拉一次时间线保证与权威数据一致。
        if (data.termination === 'limit') {
          api(withWorkspace(`/api/team/rooms/${state.activeRoom.id}/timeline`))
            .then(body => {
              state.timeline = body.timeline || [];
              renderRoom();
            })
            .catch(() => {});
        }
        break;
      default:
        break;
    }
  }

  function renderRoom() {
    if (!state.activeRoom) return;
    el('group-room-name').textContent = state.activeRoom.name;
    const notice = el('group-room-notice');
    if (notice) {
      notice.textContent = state.activeRoom.notice || '';
      notice.hidden = !state.activeRoom.notice;
    }
    renderMembers();
    renderTimeline();
  }

  function renderMembers() {
    const wrap = el('group-room-members');
    if (!wrap) return;
    wrap.textContent = '';
    state.members.forEach(member => {
      const chip = document.createElement('span');
      chip.className = 'group-member';
      if (member.is_admin) chip.classList.add('admin');
      if (state.speaking === member.id) chip.classList.add('speaking');
      chip.textContent = member.name + (member.is_admin ? ' (admin)' : '');
      wrap.appendChild(chip);
    });
    if (state.activeRoom && state.activeRoom.notice) {
      const notice = document.createElement('div');
      notice.className = 'group-notice';
      notice.textContent = `群公告：${state.activeRoom.notice}`;
      wrap.appendChild(notice);
    }
  }

  function speakerName(speakerId) {
    const member = state.members.find(m => m.id === speakerId);
    return member ? member.name : speakerId;
  }

  function renderTimeline() {
    const list = el('group-room-timeline');
    if (!list) return;
    list.textContent = '';
    state.timeline.forEach(entry => {
      const row = document.createElement('div');
      // 来源区分（spec「多 agent 消息按来源区分」）：user / post / system 三类
      // 有不同的 class 与不同的头部，绝不把不同 agent 渲染成同一来源。
      row.className = `group-msg ${entry.kind}`;
      const head = document.createElement('div');
      head.className = 'group-msg-head';
      if (entry.kind === 'post') {
        head.textContent = speakerName(entry.speaker);
        row.dataset.speaker = entry.speaker || '';
        row.style.setProperty('--group-hue', String(hueFor(entry.speaker || '')));
      } else if (entry.kind === 'user') {
        head.textContent = '你';
      } else {
        head.textContent = '系统';
      }
      const body = document.createElement('div');
      body.className = 'group-msg-body';
      body.textContent = entry.text;
      row.appendChild(head);
      row.appendChild(body);
      list.appendChild(row);
    });
    list.scrollTop = list.scrollHeight;
  }

  function hueFor(key) {
    let hash = 0;
    for (let i = 0; i < key.length; i += 1) {
      hash = (hash * 31 + key.charCodeAt(i)) % 360;
    }
    return hash;
  }

  function setStatus(text) {
    const status = el('group-room-status');
    if (status) status.textContent = text || '';
  }

  async function sendRoomMessage() {
    const input = el('group-room-input');
    if (!input || !state.activeRoom) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: 'chat', content: text }));
      return;
    }
    // WS 未连通时的降级：走 HTTP（会等整轮跑完才返回）。
    try {
      const body = await api(`/api/team/rooms/${state.activeRoom.id}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: text, workspace: workspaceParam() }),
      });
      state.timeline = body.timeline || state.timeline;
      renderRoom();
    } catch (err) {
      setStatus(`发送失败：${err.message}`);
    }
  }

  // ---------------------------------------------------------------- 对话框

  function openDialog(title, fields, onSubmit) {
    const dialog = el('group-dialog');
    const scrim = el('group-dialog-scrim');
    dialog.textContent = '';
    const heading = document.createElement('h3');
    heading.textContent = title;
    dialog.appendChild(heading);
    const form = document.createElement('form');
    const inputs = {};
    fields.forEach(field => {
      const label = document.createElement('label');
      label.textContent = field.label;
      let input;
      if (field.type === 'select') {
        input = document.createElement('select');
        (field.options || []).forEach(opt => {
          const option = document.createElement('option');
          option.value = opt.value;
          option.textContent = opt.label;
          input.appendChild(option);
        });
      } else if (field.type === 'members') {
        input = document.createElement('div');
        input.className = 'group-member-picker';
        (field.options || []).forEach(opt => {
          const wrapper = document.createElement('label');
          wrapper.className = 'group-member-option';
          const box = document.createElement('input');
          box.type = 'checkbox';
          box.value = opt.value;
          box.checked = (field.value || []).includes(opt.value);
          wrapper.appendChild(box);
          wrapper.appendChild(document.createTextNode(opt.label));
          input.appendChild(wrapper);
        });
      } else if (field.type === 'textarea') {
        input = document.createElement('textarea');
        input.rows = 4;
        input.value = field.value || '';
      } else {
        input = document.createElement('input');
        input.type = 'text';
        input.value = field.value || '';
      }
      if (field.type !== 'members') input.id = `group-field-${field.name}`;
      inputs[field.name] = input;
      label.appendChild(input);
      form.appendChild(label);
    });
    const error = document.createElement('div');
    error.className = 'group-dialog-error';
    form.appendChild(error);
    const actions = document.createElement('div');
    actions.className = 'group-dialog-actions';
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.textContent = '保存';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = '取消';
    cancel.addEventListener('click', closeDialog);
    actions.appendChild(submit);
    actions.appendChild(cancel);
    form.appendChild(actions);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const values = {};
      Object.entries(inputs).forEach(([name, input]) => {
        if (input.className === 'group-member-picker') {
          values[name] = Array.from(input.querySelectorAll('input:checked')).map(b => b.value);
        } else {
          values[name] = input.value;
        }
      });
      try {
        await onSubmit(values);
        closeDialog();
      } catch (err) {
        error.textContent = err.message;
      }
    });
    dialog.appendChild(form);
    dialog.hidden = false;
    scrim.hidden = false;
  }

  function closeDialog() {
    el('group-dialog').hidden = true;
    el('group-dialog-scrim').hidden = true;
  }

  function openPersonaDialog(persona) {
    const isNew = !persona;
    openDialog(isNew ? '新建人设' : `设置人设：${persona.name}`, [
      { name: 'name', label: '名称', value: persona ? persona.name : '' },
      { name: 'role', label: '角色标签', value: persona ? persona.role : '' },
      { name: 'instructions', label: '指令', type: 'textarea', value: persona ? persona.instructions : '' },
      { name: 'model', label: '模型绑定（留空用默认）', value: persona ? persona.model : '' },
      {
        name: 'main_bot', label: 'Chief（管理全部人设与房间）', type: 'select',
        value: persona && state.mainBotIds.includes(persona.id) ? '1' : '',
        options: [{ value: '', label: '否' }, { value: '1', label: '是' }],
      },
    ], async (values) => {
      const payload = {
        workspace: workspaceParam(),
        name: values.name,
        role: values.role,
        instructions: values.instructions,
        model: values.model,
        main_bot: values.main_bot === '1',
      };
      const body = persona
        ? await api(`/api/team/personas/${persona.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
        : await api('/api/team/personas', { method: 'POST', body: JSON.stringify(payload) });
      applyState(body);
    });
  }

  function openRoomDialog(room) {
    const isNew = !room;
    const memberOptions = state.personas.map(p => ({ value: p.id, label: p.name || p.id }));
    const adminOptions = [{ value: '', label: '（无）' }].concat(memberOptions);
    openDialog(isNew ? '新建群聊' : `设置群聊：${room.name}`, [
      { name: 'name', label: '名称', value: room ? room.name : '' },
      { name: 'notice', label: '群公告（每名成员发言前注入）', type: 'textarea', value: room ? room.notice : '' },
      { name: 'members', label: '成员', type: 'members', options: memberOptions, value: room ? room.members : [] },
      { name: 'admin', label: '房间 admin（默认应答者）', type: 'select', value: room ? (room.admin || '') : '', options: adminOptions },
    ], async (values) => {
      const payload = {
        workspace: workspaceParam(),
        name: values.name,
        notice: values.notice,
        members: values.members,
        admin: values.admin || null,
      };
      const body = room
        ? await api(`/api/team/rooms/${room.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
        : await api('/api/team/rooms', { method: 'POST', body: JSON.stringify(payload) });
      applyState(body);
    });
  }

  // ---------------------------------------------------------------- 绑定

  function bind() {
    const personaAdd = el('group-persona-add');
    if (personaAdd) personaAdd.addEventListener('click', () => openPersonaDialog(null));
    const roomAdd = el('group-room-add');
    if (roomAdd) roomAdd.addEventListener('click', () => openRoomDialog(null));
    const send = el('group-room-send');
    if (send) send.addEventListener('click', sendRoomMessage);
    const input = el('group-room-input');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendRoomMessage();
        }
      });
    }
    const edit = el('group-room-edit');
    if (edit) edit.addEventListener('click', () => {
      if (state.activeRoom) {
        const fresh = state.rooms.find(r => r.id === state.activeRoom.id) || state.activeRoom;
        openRoomDialog(fresh);
      }
    });
    const del = el('group-room-delete');
    if (del) del.addEventListener('click', async () => {
      if (!state.activeRoom) return;
      if (!window.confirm(`删除群聊「${state.activeRoom.name}」？房间日志、群内会话底座与该群的成员记忆都会被清理。`)) return;
      try {
        applyState(await api(
          withWorkspace(`/api/team/rooms/${state.activeRoom.id}`),
          { method: 'DELETE' },
        ));
        closeRoom();
      } catch (err) {
        setStatus(`删除失败：${err.message}`);
      }
    });
    const scrim = el('group-dialog-scrim');
    if (scrim) scrim.addEventListener('click', closeDialog);
  }

  window.AsterwyndGroup = {
    render: function () {
      refresh();
    },
    _state: state,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
