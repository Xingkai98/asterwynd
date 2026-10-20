// web/static/group_status.js
// 群聊成员状态的纯函数 reducer（change web-agent-group-member-status）。
//
// 与 DOM 解耦：group.js 负责渲染/WS 分发，本文件只做
//   (state, event) -> {state, changed, applied}
// 的纯计算，供 node + vm 单测（tests/web_tests/test_group_status_js.py）。
(function () {
  const PHASES = ['idle', 'running', 'thinking', 'typing', 'tool'];
  const PHASE_LABELS = {
    idle: '空闲',
    running: '运行中',
    thinking: '正在思考',
    typing: '正在输入',
  };

  function createStatusState() {
    return { statuses: {}, seq: 0 };
  }

  function normalizeStatus(item) {
    if (!item || !item.persona_id) return null;
    const phase = PHASES.includes(item.phase) ? item.phase : 'idle';
    if (phase === 'idle') return null;
    const tools = Array.isArray(item.tools)
      ? item.tools.map(name => String(name || '')).filter(Boolean)
      : [];
    const toolCount = Number.isFinite(Number(item.tool_count))
      ? Number(item.tool_count)
      : tools.length;
    return {
      persona_id: String(item.persona_id),
      phase,
      tools,
      tool_count: toolCount,
    };
  }

  function mapFromList(list) {
    const statuses = {};
    (Array.isArray(list) ? list : []).forEach(item => {
      const status = normalizeStatus(item);
      if (status) statuses[status.persona_id] = status;
    });
    return statuses;
  }

  function copyStatuses(statuses) {
    return Object.assign({}, statuses || {});
  }

  function applyStatusEvent(state, data) {
    const seq = Number(data && data.status_seq) || 0;
    if (seq <= state.seq) {
      return { state, changed: false, applied: false };
    }
    const statuses = mapFromList(data && data.statuses);
    return { state: { statuses, seq }, changed: true, applied: true };
  }

  function applyTerminal(state, data) {
    const payload = data || {};
    const seq = payload.status_seq != null ? Number(payload.status_seq) : null;
    if (seq != null && seq < state.seq) {
      return { state, changed: false, applied: false, clearedAll: false };
    }
    const statuses = copyStatuses(state.statuses);
    let clearedAll = false;
    if (payload.termination) {
      // round_ended（completed / limit / all_failed / cancelled / error）
      Object.keys(statuses).forEach(key => { delete statuses[key]; });
      clearedAll = true;
    } else if (payload.persona_id) {
      delete statuses[payload.persona_id];
    }
    const nextSeq = seq != null ? Math.max(state.seq, seq) : state.seq;
    return {
      state: { statuses, seq: nextSeq },
      changed: true,
      applied: true,
      clearedAll,
    };
  }

  function applySnapshot(state, data) {
    const payload = data || {};
    const statuses = mapFromList(payload.member_statuses);
    if (payload.round_active === false) {
      Object.keys(statuses).forEach(key => { delete statuses[key]; });
    }
    return {
      state: { statuses, seq: Number(payload.status_seq) || 0 },
      changed: true,
      applied: true,
    };
  }

  function applySpeakingFallback(state, data) {
    const payload = data || {};
    const personaId = payload.persona_id;
    if (!personaId) return { state, changed: false, applied: false };
    const seq = payload.status_seq != null ? Number(payload.status_seq) : null;
    if (seq != null && seq < state.seq) {
      return { state, changed: false, applied: false };
    }
    const current = state.statuses[personaId];
    if (current && current.phase !== 'idle') {
      return { state, changed: false, applied: false };
    }
    const statuses = copyStatuses(state.statuses);
    statuses[personaId] = {
      persona_id: personaId,
      phase: 'running',
      tools: [],
      tool_count: 0,
    };
    return {
      state: {
        statuses,
        seq: seq != null ? Math.max(state.seq, seq) : state.seq,
      },
      changed: true,
      applied: true,
    };
  }

  function formatPhase(phase, tools, count) {
    if (phase === 'tool') {
      const names = Array.isArray(tools) ? tools.filter(Boolean) : [];
      const total = Number.isFinite(Number(count)) ? Number(count) : names.length;
      if (!names.length) return '正在使用工具';
      const label = names.join('、');
      return total > 1
        ? `正在使用工具 · ${label}（${total} 个）`
        : `正在使用工具 · ${label}`;
    }
    return PHASE_LABELS[phase] || PHASE_LABELS.idle;
  }

  function describeChange(prev, next, names) {
    const before = (prev && prev.statuses) || {};
    const after = (next && next.statuses) || {};
    const keys = Array.from(new Set(
      Object.keys(before).concat(Object.keys(after))
    ));
    for (const personaId of keys) {
      const a = JSON.stringify(before[personaId] || null);
      const b = JSON.stringify(after[personaId] || null);
      if (a === b) continue;
      const status = after[personaId];
      const phase = status ? status.phase : 'idle';
      const name = (names && names[personaId]) || personaId;
      return `${name} ${formatPhase(
        phase,
        status ? status.tools : [],
        status ? status.tool_count : 0,
      )}`;
    }
    return null;
  }

  window.AsterwyndGroupStatus = {
    PHASES,
    createStatusState,
    applyStatusEvent,
    applyTerminal,
    applySnapshot,
    applySpeakingFallback,
    formatPhase,
    describeChange,
  };
})();
