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
    // 成员运行状态（change web-agent-group-member-status）：房间级完整表 + 单调 seq。
    statuses: {},
    statusSeq: 0,
    statusStale: false,
    connectionEpoch: 0,
    statusText: '',
    statusKind: '',
    // 讨论链（change group-unlimited-discussion）：当前链身份、轮次活跃与停止控件状态。
    // chainId 只用于拒绝「迟到的旧链终态」；round_active 由 room_state / 链事件维护，
    // 停止按钮可见性 = round_active && room.discussion_mode === 'unlimited'（纯函数推导）。
    chainId: null,
    roundActive: false,
    stopPending: false,
    sidebarOpen: false,
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
      name.title = [persona.role, persona.model, persona.mode, ...badges]
        .filter(Boolean).join(' · ');
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
      btn.title = `${room.members.length} 名成员 · 应答模式 ${room.reply_mode}`;
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

  const Status = window.AsterwyndGroupStatus;

  function openSidebar() {
    state.sidebarOpen = true;
    const sidebar = el('group-sidebar');
    if (sidebar) sidebar.classList.add('open');
    const scrim = el('group-sidebar-scrim');
    if (scrim) scrim.hidden = false;
  }

  function closeSidebar() {
    state.sidebarOpen = false;
    const sidebar = el('group-sidebar');
    if (sidebar) sidebar.classList.remove('open');
    const scrim = el('group-sidebar-scrim');
    if (scrim) scrim.hidden = true;
  }

  function resetStatusState() {
    state.statuses = {};
    state.statusSeq = 0;
    state.statusStale = false;
  }

  function resetDiscussionState() {
    state.chainId = null;
    state.roundActive = false;
    state.stopPending = false;
  }

  function closeRoom() {
    closeSidebar();
    if (state.ws) {
      state.ws.onclose = null;
      state.ws.close();
      state.ws = null;
    }
    state.connectionEpoch += 1;
    state.activeRoom = null;
    state.members = [];
    state.timeline = [];
    resetStatusState();
    resetDiscussionState();
    updateStopButton();
    setStatus('', '');
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
      setStatus(`打开群聊失败：${err.message}`, 'op');
      return;
    }
    state.activeRoom = stateBody.room;
    state.members = stateBody.members || [];
    state.timeline = stateBody.timeline || [];
    resetStatusState();
    resetDiscussionState();
    closeSidebar();
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
    // 每次新建 socket 都推进代际：旧连接的尾部事件不得污染新连接的状态。
    state.connectionEpoch += 1;
    const epoch = state.connectionEpoch;
    state.statusSeq = 0;
    state.statusStale = true;
    renderMemberPresence();
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = workspaceParam();
    const url = `${protocol}//${location.host}/ws/room/${roomId}${ws ? '?workspace=' + encodeURIComponent(ws) : ''}`;
    const socket = new WebSocket(url);
    state.ws = socket;
    socket.onopen = () => {
      if (epoch !== state.connectionEpoch) return;
      setStatus('已连接', 'conn');
      clearOpStatus();
    };
    socket.onmessage = (e) => {
      if (epoch !== state.connectionEpoch) return;
      let event;
      try {
        event = JSON.parse(e.data);
      } catch (err) {
        return;
      }
      handleRoomEvent(event);
    };
    socket.onclose = () => {
      if (epoch !== state.connectionEpoch) return;
      if (state.activeRoom && state.activeRoom.id === roomId) {
        state.statusStale = true;
        setStatus('连接断开，重连中...', 'conn');
        renderMemberPresence();
        setTimeout(() => {
          if (epoch !== state.connectionEpoch) return;
          if (state.activeRoom && state.activeRoom.id === roomId) connectRoom(roomId);
        }, 2000);
      }
    };
  }

  function statusSnapshot() {
    return { statuses: state.statuses, seq: state.statusSeq };
  }

  function memberName(personaId) {
    const member = state.members.find(m => m.id === personaId);
    return member ? member.name : personaId;
  }

  function memberNames() {
    const names = {};
    state.members.forEach(member => { names[member.id] = member.name; });
    return names;
  }

  function hasNonIdle() {
    return Object.values(state.statuses).some(status => status.phase !== 'idle');
  }

  function updateLiveRegion(prev) {
    if (!Status) return;
    const text = Status.describeChange(prev, statusSnapshot(), memberNames());
    if (!text) return;
    const live = el('group-presence-live');
    if (live) live.textContent = text;
  }

  function appendTimeline(entry) {
    if (entry.seq != null && state.timeline.some(item => item.seq === entry.seq)) {
      return;
    }
    state.timeline.push(entry);
  }

  function clearRoundStatus() {
    if (state.statusKind === 'round') setStatus('', '');
  }

  function clearOpStatus() {
    if (state.statusKind === 'op') setStatus('', '');
  }

  // ------------------------------------------------------------ 讨论链

  function isUnlimitedRoom() {
    return Boolean(state.activeRoom && state.activeRoom.discussion_mode === 'unlimited');
  }

  function stopSnapshot() {
    return { round_active: state.roundActive, room: state.activeRoom || {} };
  }

  function updateStopButton() {
    const button = el('group-room-stop');
    if (!button) return;
    const visible = Status
      ? Status.shouldShowStop(stopSnapshot())
      : (state.roundActive && isUnlimitedRoom());
    button.hidden = !visible;
    button.disabled = state.stopPending;
    button.textContent = state.stopPending ? '正在停止…' : '停止讨论';
    if (visible) button.setAttribute('aria-busy', state.stopPending ? 'true' : 'false');
    else button.removeAttribute('aria-busy');
  }

  function chainEventAllowed(data) {
    return Status ? Status.shouldApplyChainEvent(state.chainId, data) : true;
  }

  function adoptChain(chainId) {
    if (chainId == null || chainId === '') return;
    state.chainId = chainId;
  }

  // 「讨论中（第 k 轮）」与链终态共用 statusKind='discussion'：与 single 的
  // 'round' 区分开，避免 member_status 的既有清理逻辑把讨论进度擦掉。
  function setDiscussionStatus(text) {
    if (text) setStatus(text, 'discussion');
  }

  function stopDiscussion() {
    if (!state.activeRoom || state.stopPending) return;
    if (!Status || !Status.shouldShowStop(stopSnapshot())) return;
    state.stopPending = true;
    updateStopButton();
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      // 主路径：房间 WS 消息（后端 request_stop 的幂等优雅停止）。
      state.ws.send(JSON.stringify({ type: 'stop_discussion' }));
      return;
    }
    // WS 未连通 → REST 降级（POST /api/team/rooms/{id}/discussion/stop）。
    api(withWorkspace(`/api/team/rooms/${state.activeRoom.id}/discussion/stop`), {
      method: 'POST',
      body: JSON.stringify({ workspace: workspaceParam() }),
    }).then(body => {
      // stopping=true：等 round_ended(stopped)/discussion_ended(stopped) 收尾；
      // stopping=false：没有活动链（幂等 no-op），不会再有事件，立刻恢复控件。
      if (body && body.stopping) return;
      state.stopPending = false;
      state.roundActive = false;
      updateStopButton();
    }).catch(err => {
      state.stopPending = false;
      updateStopButton();
      setStatus(`停止失败：${err.message}`, 'op');
    });
  }

  function handleRoomEvent(event) {
    const data = event.data || {};
    const prev = statusSnapshot();
    switch (event.type) {
      case 'room_state': {
        state.activeRoom = data.room || state.activeRoom;
        state.members = data.members || state.members;
        state.timeline = data.timeline || [];
        if (Status) {
          const result = Status.applySnapshot(prev, data);
          state.statuses = result.state.statuses;
          state.statusSeq = result.state.seq;
        } else {
          resetStatusState();
        }
        state.statusStale = false;
        // 链身份在新连接/快照里未知：清空并等后续链事件认链（迟到旧链事件由守卫拦截）。
        state.chainId = null;
        state.stopPending = false;
        state.roundActive = data.round_active === true;
        // 刷新/重连恢复：discussion_round 恢复「讨论中（第 k 轮）」，
        // discussion_reason 恢复最近一次链终态；single 房不恢复讨论文案。
        const snapshotRoom = data.room || {};
        if (snapshotRoom.discussion_mode === 'unlimited') {
          const round = Number(data.discussion_round) || 0;
          const reason = data.discussion_reason || null;
          if (state.roundActive && round > 0) {
            setDiscussionStatus(`讨论中（第 ${round} 轮）`);
          } else if (reason) {
            setDiscussionStatus(Status ? Status.describeDiscussionEnd(reason) : null);
          }
        }
        renderRoom();
        break;
      }
      case 'user_message':
        appendTimeline({
          seq: data.seq, speaker: 'user', kind: 'user', text: data.text, ts: '',
        });
        if (!data.queued) clearRoundStatus();
        renderTimeline();
        break;
      case 'member_status': {
        if (!Status) break;
        const result = Status.applyStatusEvent(prev, data);
        if (!result.applied) break;
        state.statuses = result.state.statuses;
        state.statusSeq = result.state.seq;
        if (hasNonIdle()) clearRoundStatus();
        updateLiveRegion(prev);
        renderMemberPresence(true);
        break;
      }
      case 'member_speaking': {
        // 旧服务端降级：没有 member_status 时用 speaking 表示 running。
        if (!Status) break;
        const result = Status.applySpeakingFallback(prev, data);
        if (!result.changed) break;
        state.statuses = result.state.statuses;
        state.statusSeq = result.state.seq;
        updateLiveRegion(prev);
        renderMemberPresence(true);
        break;
      }
      case 'member_post': {
        if (Status) {
          const result = Status.applyTerminal(prev, data);
          state.statuses = result.state.statuses;
          state.statusSeq = result.state.seq;
        }
        appendTimeline({
          seq: data.seq, speaker: data.speaker, kind: 'post', text: data.text, ts: '',
        });
        updateLiveRegion(prev);
        renderTimeline();
        renderMemberPresence();
        break;
      }
      case 'member_silent': {
        if (Status) {
          const result = Status.applyTerminal(prev, data);
          state.statuses = result.state.statuses;
          state.statusSeq = result.state.seq;
        }
        updateLiveRegion(prev);
        renderMemberPresence();
        break;
      }
      case 'member_failed': {
        if (Status) {
          const result = Status.applyTerminal(prev, data);
          state.statuses = result.state.statuses;
          state.statusSeq = result.state.seq;
        }
        appendTimeline({
          seq: null, speaker: null, kind: 'system',
          text: `${data.name || memberName(data.persona_id)} 运行失败：${data.reason || ''}`,
          ts: '',
        });
        updateLiveRegion(prev);
        renderTimeline();
        renderMemberPresence();
        break;
      }
      case 'round_ended': {
        if (!chainEventAllowed(data)) break;
        adoptChain(data.chain_id);
        // 讨论链扩展字段（chain_id / round_index / chain_continues）存在即视为链事件；
        // single 的 round_ended 四键不变，走既有文案与清理时机。
        const chainRound = data.chain_id != null || data.chain_continues != null;
        if (chainRound) {
          state.roundActive = data.chain_continues === true;
        } else {
          state.roundActive = false;
        }
        if (Status) {
          const result = Status.applyTerminal(prev, data);
          if (result.applied) {
            state.statuses = result.state.statuses;
            state.statusSeq = result.state.seq;
            const text = Status.describeRoundEnd(data);
            if (text) setStatus(text, chainRound ? 'discussion' : 'round');
          }
        }
        updateStopButton();
        // 迟到终态即使不改状态，limit 的 system 条目仍需重拉；响应应用前校验房间。
        if (data.termination === 'limit') {
          const roomId = state.activeRoom && state.activeRoom.id;
          if (roomId) {
            api(withWorkspace(`/api/team/rooms/${roomId}/timeline`))
              .then(body => {
                if (!state.activeRoom || state.activeRoom.id !== roomId) return;
                // 按 seq 合并：重拉期间到达的新消息不能丢；同 seq 以服务端为准。
                state.timeline = Status
                  ? Status.mergeTimeline(state.timeline, body.timeline)
                  : (body.timeline || []);
                renderTimeline();
              })
              .catch(() => {});
          }
        }
        updateLiveRegion(prev);
        renderMemberPresence();
        break;
      }
      case 'discussion_started': {
        // 链起点不设 chain_id 守卫：新链必须能认领；此后旧链迟到事件才被新链 id 挡住。
        adoptChain(data.chain_id);
        if (data.discussion_mode && state.activeRoom) {
          state.activeRoom.discussion_mode = data.discussion_mode;
        }
        state.roundActive = true;
        state.stopPending = false;
        const roundIndex = Number(data.round_index) || 1;
        setDiscussionStatus(`讨论中（第 ${roundIndex} 轮）`);
        updateStopButton();
        break;
      }
      case 'system_entry': {
        // 链内 system 条目实时追加（按 seq 去重，与时间线合并口径一致）。
        if (!chainEventAllowed(data)) break;
        adoptChain(data.chain_id);
        appendTimeline({
          seq: data.seq != null ? Number(data.seq) : null,
          speaker: null,
          kind: 'system',
          text: String(data.text || ''),
          ts: '',
        });
        renderTimeline();
        break;
      }
      case 'discussion_stop_requested': {
        if (!chainEventAllowed(data)) break;
        adoptChain(data.chain_id);
        state.stopPending = true;
        updateStopButton();
        break;
      }
      case 'discussion_ended': {
        if (!chainEventAllowed(data)) break;
        adoptChain(data.chain_id);
        state.roundActive = false;
        state.stopPending = false;
        setDiscussionStatus(Status ? Status.describeDiscussionEnd(data.reason) : null);
        updateStopButton();
        break;
      }
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
    renderMemberPresence();
    renderTimeline();
    updateStopButton();
  }

  function renderMemberPresence(focusActive) {
    const list = el('group-presence-list');
    if (!list) return;
    // 移动端 overflow-x 在 aside 上（不是 ul）；桌面 aside 纵向滚动、scrollLeft 恒 0。
    const scroller = el('group-room-presence') || list;
    const previousScroll = scroller.scrollLeft;
    list.textContent = '';
    let activeRow = null;
    state.members.forEach(member => {
      const status = state.statuses[member.id];
      const phase = status ? status.phase : 'idle';
      const row = document.createElement('li');
      row.className = `group-presence-row phase-${phase}`;
      if (state.statusStale) row.classList.add('stale');
      row.dataset.personaId = member.id;
      row.style.setProperty('--group-hue', String(hueFor(member.id)));

      const avatar = document.createElement('span');
      avatar.className = 'group-avatar';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = (member.name || member.id).slice(0, 1);

      const info = document.createElement('span');
      info.className = 'group-presence-info';
      const name = document.createElement('span');
      name.className = 'group-presence-name';
      name.textContent = member.name + (member.is_admin ? '（admin）' : '');
      const statusText = document.createElement('span');
      statusText.className = 'group-presence-status';
      statusText.textContent = Status
        ? Status.formatPhase(phase, status ? status.tools : [], status ? status.tool_count : 0)
        : phase;
      if (status && status.tools && status.tools.length) {
        statusText.title = status.tools.join('、');
      }
      info.appendChild(name);
      info.appendChild(statusText);
      row.appendChild(avatar);
      row.appendChild(info);
      list.appendChild(row);
      if (!activeRow && phase !== 'idle') activeRow = row;
    });
    if (focusActive && activeRow) {
      // 只滚动状态条自身，绝不调用 scrollIntoView（会纵向滚动页面/时间线）。
      const left = activeRow.offsetLeft;
      const right = left + activeRow.offsetWidth;
      if (left < scroller.scrollLeft) {
        scroller.scrollLeft = Math.max(0, left - 8);
      } else if (right > scroller.scrollLeft + scroller.clientWidth) {
        scroller.scrollLeft = right - scroller.clientWidth + 8;
      }
    } else {
      scroller.scrollLeft = previousScroll;
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

  function setStatus(text, kind) {
    state.statusText = text || '';
    state.statusKind = text ? (kind || 'op') : '';
    const status = el('group-room-status');
    if (status) status.textContent = state.statusText;
  }

  async function sendRoomMessage() {
    const input = el('group-room-input');
    if (!input || !state.activeRoom) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: 'chat', content: text }));
      clearOpStatus();
      return;
    }
    // WS 未连通时的降级：走 HTTP（会等整轮跑完才返回）。
    try {
      const body = await api(`/api/team/rooms/${state.activeRoom.id}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: text, workspace: workspaceParam() }),
      });
      state.timeline = body.timeline || state.timeline;
      clearOpStatus();
      renderRoom();
    } catch (err) {
      setStatus(`发送失败：${err.message}`, 'op');
    }
  }

  // ---------------------------------------------------------------- 对话框

  function openDialog(title, fields, onSubmit) {
    closeSidebar();
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
          // option.disabled：不可用选项（例如 admin 应答模式下的 unlimited 讨论模式）。
          if (opt.disabled) option.disabled = true;
          input.appendChild(option);
        });
        if (field.value != null) input.value = String(field.value);
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
      if (field.hint !== undefined) {
        const hint = document.createElement('div');
        hint.className = 'group-field-hint';
        hint.textContent = field.hint;
        label.appendChild(hint);
      }
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
    return inputs;
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
        name: 'mode', label: '运行模式', type: 'select',
        value: persona ? persona.mode : 'bypass',
        options: [
          { value: 'bypass', label: 'bypass（不受审批阻塞，默认）' },
          { value: 'build', label: 'build' },
          { value: 'read_only', label: 'read_only' },
          { value: 'plan', label: 'plan' },
        ],
      },
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
        mode: values.mode,
        main_bot: values.main_bot === '1',
      };
      const body = persona
        ? await api(`/api/team/personas/${persona.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
        : await api('/api/team/personas', { method: 'POST', body: JSON.stringify(payload) });
      applyState(body);
    });
  }

  function roomDialogError(err) {
    const raw = err && err.message ? String(err.message) : '';
    const known = {
      discussion_mode_requires_everyone:
        '仅 everyone 应答模式可以选择无限讨论；请先把「应答模式」设为 everyone 并保存，再修改讨论模式。',
      invalid_discussion_mode: '讨论模式取值非法，请选择 single（单轮）或 unlimited（无限讨论）。',
    };
    return new Error(known[raw] || raw || '保存失败');
  }

  function discussionModeHint(replyMode) {
    if (replyMode === 'everyone') return '';
    return '无限讨论仅在 everyone 应答模式可用：把上方「应答模式」切换为 everyone 后'
      + '即可立即选择（无需先保存）。';
  }

  function openRoomDialog(room) {
    const isNew = !room;
    const memberOptions = state.personas.map(p => ({ value: p.id, label: p.name || p.id }));
    const adminOptions = [{ value: '', label: '（无）' }].concat(memberOptions);
    const replyMode = room ? room.reply_mode : 'admin';
    const inputs = openDialog(isNew ? '新建群聊' : `设置群聊：${room.name}`, [
      { name: 'name', label: '名称', value: room ? room.name : '' },
      { name: 'notice', label: '群公告（每名成员发言前注入）', type: 'textarea', value: room ? room.notice : '' },
      {
        name: 'reply_mode', label: '应答模式', type: 'select',
        value: room ? room.reply_mode : 'admin',
        options: [
          { value: 'admin', label: 'admin（无 @ 时只由房间 admin 应答，默认）' },
          { value: 'everyone', label: 'everyone（无 @ 时全体成员按序各得一次机会）' },
        ],
      },
      {
        name: 'discussion_mode', label: '讨论模式', type: 'select',
        value: room && room.discussion_mode ? room.discussion_mode : 'single',
        hint: discussionModeHint(replyMode),
        options: [
          { value: 'single', label: 'single（单轮，默认）' },
          { value: 'unlimited', label: 'unlimited（无限讨论）' },
        ],
      },
      { name: 'members', label: '成员', type: 'members', options: memberOptions, value: room ? room.members : [] },
      { name: 'admin', label: '房间 admin（默认应答者）', type: 'select', value: room ? (room.admin || '') : '', options: adminOptions },
    ], async (values) => {
      const payload = {
        workspace: workspaceParam(),
        name: values.name,
        notice: values.notice,
        reply_mode: values.reply_mode,
        discussion_mode: values.discussion_mode,
        members: values.members,
        admin: values.admin || null,
      };
      try {
        const body = room
          ? await api(`/api/team/rooms/${room.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
          : await api('/api/team/rooms', { method: 'POST', body: JSON.stringify(payload) });
        applyState(body);
      } catch (err) {
        // 结构化错误必须如实展示（spec：SHALL NOT 静默丢弃）。
        throw roomDialogError(err);
      }
    });

    // 讨论模式可用性随「应答模式」选择即时联动：同一对话框内切到 everyone 立即可选，
    // 切回 admin 立即置灰并把已选 unlimited 复位为 single；服务端仍按合并后的生效值
    // 校验（400 兜底展示，见 roomDialogError）。
    const discussionSelect = inputs.discussion_mode;
    const unlimitedOption = discussionSelect.querySelector("option[value='unlimited']");
    const discussionHint = discussionSelect
      .closest('label')
      .querySelector('.group-field-hint');
    function syncDiscussionModeAvailability() {
      const available = Status && Status.unlimitedDiscussionAvailable
        ? Status.unlimitedDiscussionAvailable(inputs.reply_mode.value)
        : inputs.reply_mode.value === 'everyone';
      unlimitedOption.disabled = !available;
      unlimitedOption.textContent = available
        ? 'unlimited（无限讨论：成员自动连续多轮）'
        : 'unlimited（无限讨论，仅 everyone 应答模式可用）';
      if (!available && discussionSelect.value === 'unlimited') {
        discussionSelect.value = 'single';
      }
      if (discussionHint) {
        discussionHint.textContent = discussionModeHint(inputs.reply_mode.value);
        discussionHint.hidden = discussionHint.textContent === '';
      }
    }
    inputs.reply_mode.addEventListener('change', syncDiscussionModeAvailability);
    syncDiscussionModeAvailability();
  }

  // ---------------------------------------------------------------- 绑定

  function bind() {
    const personaAdd = el('group-persona-add');
    if (personaAdd) personaAdd.addEventListener('click', () => openPersonaDialog(null));
    const roomAdd = el('group-room-add');
    if (roomAdd) roomAdd.addEventListener('click', () => openRoomDialog(null));
    const drawerToggle = el('group-drawer-toggle');
    if (drawerToggle) drawerToggle.addEventListener('click', openSidebar);
    const emptyDrawer = el('group-empty-drawer');
    if (emptyDrawer) emptyDrawer.addEventListener('click', openSidebar);
    const sidebarScrim = el('group-sidebar-scrim');
    if (sidebarScrim) sidebarScrim.addEventListener('click', closeSidebar);
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
    const stop = el('group-room-stop');
    if (stop) stop.addEventListener('click', stopDiscussion);
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
