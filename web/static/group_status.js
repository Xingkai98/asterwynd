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

  function mergeTimeline(current, incoming) {
    // 按 room log seq 合并：重拉期间到达的新消息不丢；同 seq 以服务端条目为准。
    const bySeq = new Map();
    (Array.isArray(current) ? current : []).forEach(entry => {
      if (entry && entry.seq != null) bySeq.set(entry.seq, entry);
    });
    (Array.isArray(incoming) ? incoming : []).forEach(entry => {
      if (entry && entry.seq != null) bySeq.set(entry.seq, entry);
    });
    return Array.from(bySeq.values())
      .sort((a, b) => Number(a.seq) - Number(b.seq));
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

  // ---------------------------------------------------------------- 讨论链
  //
  // change group-unlimited-discussion（design Decision 7 的事件契约）：
  //   discussion_started      {room_id, chain_id, discussion_mode, members, round_index, limits}
  //   system_entry            {room_id, chain_id, seq, text}
  //   discussion_stop_requested {room_id, chain_id}
  //   discussion_ended        {room_id, chain_id, reason, rounds, rounds_started, turns,
  //                            elapsed_seconds, status_seq}
  //   round_ended             扩展 {chain_id, round_index, chain_continues}，termination 增 stopped。
  // 本文件只负责文案/可见性/链身份守卫的纯计算，DOM 与 WS 分发留在 group.js。

  const ROUND_END_LABELS = {
    limit: '本轮因达上限结束',
    cancelled: '本轮已中止',
    error: '本轮异常结束',
  };

  // 讨论链终态文案（与 web-ui spec delta 的状态文案表逐字对应）。
  const DISCUSSION_END_LABELS = {
    converged: '讨论已收敛',
    stopped: '讨论已停止',
    max_rounds: '讨论达安全上限',
    max_turns: '讨论达安全上限',
    max_seconds: '讨论达安全上限',
    all_failed: '讨论已中止（本轮无人发言，存在失败）',
    mode_changed: '讨论已结束（模式已变更）',
    cancelled: '讨论已中止',
    error: '讨论异常结束',
    round_limit: '讨论因本轮达上限结束',
    completed: '讨论已结束',
  };

  function isChainRoundEnd(data) {
    return Boolean(data) &&
      (data.chain_id != null || data.chain_continues != null);
  }

  function describeRoundEnd(data) {
    const payload = data || {};
    const termination = String(payload.termination || '');
    if (!isChainRoundEnd(payload)) {
      // single：既有四档文案逐字保持（completed / all_failed / 未知 → 本轮结束）。
      return ROUND_END_LABELS[termination] || '本轮结束';
    }
    // unlimited 链的停止出口：必须是「讨论已停止」，绝不显示「本轮结束」。
    if (termination === 'stopped') return '讨论已停止';
    // 链继续：显示下一轮序号（round_ended 的 round_index 是刚结束的轮）。
    if (payload.chain_continues === true) {
      const round = Number(payload.round_index);
      return Number.isFinite(round) && round > 0
        ? `讨论中（第 ${round + 1} 轮）`
        : '讨论继续中';
    }
    // 链即将结束：终态文案由紧随其后的 discussion_ended 给出（不抢文案）；
    // 取消/异常链的 teardown 投递是尽力而为，先给中止提示避免状态悬空。
    if (termination === 'cancelled') return '讨论已中止';
    if (termination === 'error') return '讨论异常结束';
    return null;
  }

  function describeDiscussionEnd(reason) {
    return DISCUSSION_END_LABELS[String(reason || '')] || null;
  }

  function shouldShowStop(snapshot) {
    const payload = snapshot || {};
    const room = payload.room || {};
    return Boolean(payload.round_active) && room.discussion_mode === 'unlimited';
  }

  function shouldApplyChainEvent(currentChainId, data) {
    const payload = data || {};
    // 不带 chain_id 的事件（single 模式 / 旧服务端 payload）一律兼容应用。
    if (payload.chain_id == null || payload.chain_id === '') return true;
    // 当前链未知（刚刷新/重连、错过 discussion_started）→ 接受并由事件认链；
    // 只有「已知当前链」与事件链不一致时才丢弃，防止迟到的旧链终态覆盖新链。
    if (currentChainId == null || currentChainId === '') return true;
    return String(currentChainId) === String(payload.chain_id);
  }

  // 讨论模式可用性：unlimited 仅在 everyone 应答模式可用。
  // 对话框内「应答模式」切换时即时调用（动态解禁/置灰），不是打开对话框时的静态快照。
  function unlimitedDiscussionAvailable(replyMode) {
    return replyMode === 'everyone';
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
    mergeTimeline,
    describeRoundEnd,
    describeDiscussionEnd,
    shouldShowStop,
    shouldApplyChainEvent,
    unlimitedDiscussionAvailable,
  };
})();
