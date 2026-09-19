// web/static/workflow.js
// Workflow 运行态流程图视图（change workflow-graph-visualization，D1/D2/D5/D7）。
//
// 纯渲染层：布局/状态映射/折叠归类全部来自 ``workflow_graph.js``（与 DOM 解耦，
// node 单测覆盖），这里只负责
//   1. 监听 ``workflow_started`` / ``workflow_snapshot`` 事件（每 tab 一份状态）；
//   2. 多图 tab（workflow_id → 图状态 map，Q2/Q9）；
//   3. 零依赖 SVG 自绘 + 分层布局 + 折叠 + pinch/pan；
//   4. 终态保留策略与 tab 上限淘汰（最近 5 张终态 + 全部 running）。
(function () {
  'use strict';

  const G = window.AsterwyndWorkflowGraph;
  if (!G) return;

  //: 图级终态（D9(d)）：**三个副本必须同步**——这里是 ``pruneGraphs`` 的消费方，
  //: 另两份是 scheduler 的 ``_SNAPSHOT_TERMINAL_STATUSES`` 与 ``workflow_graph.js``
  //: 的 ``isGraphTerminal()``。任一漏加 ``completed_with_failures``，一张「跑完了但
  //: 有节点失败」的图就会被当成 running：永远排 tab 最前、计时器一直跳、每次重连都
  //: 补发、永不进淘汰池（tab 无限增长）——而这恰是最需要用户看到的那张图。
  //: ``stalled``（零节点完成）同理：它同样需要用户看到。
  const TERMINAL_STATUSES = ['completed', 'completed_with_failures', 'stalled', 'failed',
    'cancelled', 'budget_exceeded', 'graph_recursion_exceeded'];
  const MAX_TERMINAL_TABS = 5;   // Q9：与重连补发同口径
  const COLLAPSE_THRESHOLD = 50; // D5：<50 全展开

  // 视图是**全局单例**（与 plan-document / planning 面板同构）：DOM 只有一份，
  // 渲染的是「当前 active tab」的图状态。per-tab 的数据在 tab.graphState 上。
  let activeTab = null;

  function el(id) {
    return document.getElementById(id);
  }

  /** chat.js 切换 active tab 时调用：换渲染源并重绘。 */
  function bindTab(tab) {
    activeTab = tab;
    renderPanel(tab);
  }

  function currentTab() {
    return activeTab;
  }

  /** 每个 tab 一份图面板状态：workflow_id → snapshot + 视图状态。 */
  function createGraphState() {
    return {
      graphs: new Map(),   // workflow_id -> {snapshot, expandedGroups:Set, view}
      activeId: null,
      follow: true,        // 新图/事件自动切到最新；用户手动选图后置 false
      drawer: null,        // M3：当前打开的节点详情（null = 抽屉关着）
      drawerTab: 'task',
      localStart: new Map(), // workflow_id -> 首次见到它的本地时刻（无 started_at 时兜底计时）
    };
  }

  function defaultView() {
    return { zoom: 1, panX: 0, panY: 0 };
  }

  // --- 事件入口（chat.js 调用） ------------------------------------------

  /**
   * 处理一条 workflow 事件。返回 true 表示该事件被本视图消费。
   *
   * ``workflow_started`` 只负责「开一张新图 / 切到它」（Q2）；图状态一律来自
   * ``workflow_snapshot``（带 workflow_id 路由）。
   */
  function handleWorkflowEvent(tab, event) {
    const state = tab.graphState || (tab.graphState = createGraphState());
    const data = (event && event.data) || {};
    const workflowId = data.workflow_id;
    if (!workflowId) return false;

    switch (event.type) {
      case 'workflow_started': {
        const entry = ensureGraph(state, workflowId, data);
        entry.started = data;
        if (state.follow) state.activeId = workflowId;
        showTab();
        // spec Scenario「workflow 启动自动显示图」：事件一到就自动切到 Workflow 视图
        // （只在事件所属 tab 就是当前活跃 tab 时才切，不抢用户的焦点）。
        if (tab === activeTab && typeof tab.onWorkflowStarted === 'function') {
          tab.onWorkflowStarted();
        }
        renderPanel(tab);
        return true;
      }
      case 'workflow_snapshot': {
        const entry = ensureGraph(state, workflowId, data);
        entry.snapshot = data;
        entry.expandedGroups = entry.expandedGroups || new Set();
        pruneGraphs(state);
        if (state.follow || !state.activeId) state.activeId = workflowId;
        showTab();
        renderPanel(tab);
        return true;
      }
      default:
        return false;
    }
  }

  /** 有图之后才显示 Workflow 入口（无图的会话理论上也不该看到一个空 tab）。 */
  function showTab() {
    const button = el('workflow-tab');
    if (button) button.hidden = false;
  }

  function hideTab() {
    const button = el('workflow-tab');
    if (button) button.hidden = true;
  }

  function ensureGraph(state, workflowId, data) {
    let entry = state.graphs.get(workflowId);
    if (!entry) {
      entry = {
        id: workflowId,
        snapshot: null,
        started: null,
        expandedGroups: new Set(),
        view: defaultView(),
        specHash: data.spec_hash || null,
        goal: data.goal || '',
      };
      state.graphs.set(workflowId, entry);
    }
    return entry;
  }

  /** Q9：终态 tab 上限 5 张，超出的按「最早终态先淘汰」。running 图永不淘汰。 */
  function pruneGraphs(state) {
    const terminal = [];
    state.graphs.forEach((entry) => {
      const status = entry.snapshot && entry.snapshot.status;
      if (TERMINAL_STATUSES.indexOf(status) !== -1) terminal.push(entry);
    });
    while (terminal.length > MAX_TERMINAL_TABS) {
      const evicted = terminal.shift();
      state.graphs.delete(evicted.id);
      if (state.activeId === evicted.id) state.activeId = null;
    }
  }

  // --- 面板渲染 -----------------------------------------------------------

  function renderPanel(tab) {
    if (!tab || tab !== activeTab) return;
    const state = tab.graphState;
    const canvas = el('workflow-canvas');
    if (!canvas) return;
    if (!state || !state.graphs.size) {
      canvas.textContent = '';
      const empty = document.createElement('div');
      empty.className = 'workflow-empty';
      empty.textContent = '模型启动 workflow 后自动显示流程图。';
      canvas.appendChild(empty);
      const summary = el('workflow-summary');
      if (summary) summary.textContent = '';
      const tabs = el('workflow-tabs');
      if (tabs) { tabs.textContent = ''; tabs.hidden = true; }
      hideLegend();
      hideActions();
      hideNotice();
      closeDrawer(state);
      return;
    }

    renderLegend(state);
    renderGraphTabs(tab, state);
    const entry = state.graphs.get(state.activeId) || firstGraph(state);
    if (!entry) return;
    state.activeId = entry.id;
    renderActiveGraph(tab, state, entry);
    renderDrawer(state, entry);
  }

  function firstGraph(state) {
    let found = null;
    state.graphs.forEach((entry) => { if (!found) found = entry; });
    return found;
  }

  /** D6：按 ``started_at`` 现算秩（Q3 = A）——不能用 Map 插入下标，因为
   *  ``pruneGraphs`` 会 delete 条目、WS 重连还会把淘汰过的图塞回来。 */
  function rankedEntries(state) {
    const entries = [];
    state.graphs.forEach((entry) => entries.push(entry));
    const ranked = G.rankGraphs(entries.map((entry) => Object.assign(
      {id: entry.id},
      (entry.snapshot || {}),
      {started_at: snapshotStartedAt(entry)},
    )));
    const rankById = new Map(ranked.map((item) => [item.id, item.rank]));
    return {entries, rankById};
  }

  /** 快照的 ``started_at``；``null`` 时退回「前端第一次见到它的时刻」。
   *
   * 退回值是必要的：``declared`` 态的图没有 ``started_at``（D3 的哨兵统一成
   * ``null``），但用户已经在 tab 上看到它了——没有时刻就没有相对时间可显示。 */
  function snapshotStartedAt(entry) {
    const snapshot = entry.snapshot || entry.started || {};
    if (typeof snapshot.started_at === 'number') return snapshot.started_at;
    return entry.localStart === undefined ? null : entry.localStart;
  }

  function renderGraphTabs(tab, state) {
    const tabsEl = el('workflow-tabs');
    if (!tabsEl) return;
    tabsEl.hidden = state.graphs.size <= 1;
    tabsEl.textContent = '';
    const {entries, rankById} = rankedEntries(state);
    const now = Date.now() / 1000;
    // Q3 = A：**空间顺序也按编号**（不再「运行中排最前」）——「按时间编号 + 按状态
    // 重排」必然产生非单调序列（长跑 wf1 + 快结 wf2/wf3 → tab 读作 `#1 #3 #2`）。
    const ordered = entries.slice().sort(
      (a, b) => (rankById.get(a.id) || 0) - (rankById.get(b.id) || 0));
    ordered.forEach((entry) => {
      const snapshot = entry.snapshot || {};
      const status = snapshot.status || 'declared';
      const meta = G.graphTabMeta(
        Object.assign({}, snapshot, {started_at: snapshotStartedAt(entry)}),
        rankById.get(entry.id), now, G.nodeProgress(snapshot.nodes || []),
      );
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'graph-tab';
      if (entry.id === state.activeId) button.classList.add('active');
      button.dataset.status = status;
      button.dataset.workflowId = entry.id;
      button.title = [
        meta.title || entry.id,
        entry.id,
        meta.duration ? `耗时 ${meta.duration}` : '',
      ].filter(Boolean).join('\n');

      const row = document.createElement('span');
      row.className = 'graph-tab-row';
      const dot = document.createElement('span');
      dot.className = 'graph-tab-dot';
      dot.style.background = G.graphStatusColor(status);
      row.appendChild(dot);
      const label = document.createElement('span');
      label.className = 'graph-tab-label';
      const goal = snapshot.goal || entry.goal || '';
      label.textContent = `#${meta.rank} ${goal ? truncate(goal, 20) : entry.id}`;
      row.appendChild(label);
      // 运行中的图用**徽标**区分，不靠位置（Q3 = A）。
      if (isRunning(status)) {
        const live = document.createElement('span');
        live.className = 'graph-tab-live';
        live.textContent = '●';
        live.title = '运行中';
        row.appendChild(live);
      }
      button.appendChild(row);

      const sub = document.createElement('span');
      sub.className = 'graph-tab-sub';
      sub.textContent = [meta.label, meta.relative, meta.duration, meta.progress]
        .filter(Boolean).join(' · ');
      button.appendChild(sub);

      button.addEventListener('click', () => {
        state.activeId = entry.id;
        state.follow = false;
        renderPanel(tab);
      });
      const close = document.createElement('span');
      close.className = 'graph-tab-close';
      close.textContent = '×';
      close.title = '关闭这张图';
      close.addEventListener('click', (event) => {
        event.stopPropagation();
        state.graphs.delete(entry.id);
        if (state.activeId === entry.id) {
          state.activeId = null;
          state.follow = true;
        }
        renderPanel(tab);
      });
      button.appendChild(close);
      tabsEl.appendChild(button);
    });
  }

  /**
   * 只刷新已存在 tab 的副行文本（D6 的「已跑 Xs 实时跳秒」）。
   *
   * **不重建 DOM**：每秒一次 ``renderGraphTabs`` 会不断替换按钮节点，打断用户
   * 的点击与焦点（与节点只用文本重绘同理）。这里按 ``data-workflow-id`` 找回
   * 每个 tab，用同一个 ``graphTabMeta`` 重算副行——口径与首渲染**同源**。
   */
  function refreshTabMeta(state, now) {
    if (!state) return;
    const tabsEl = el('workflow-tabs');
    if (!tabsEl) return;
    const {entries, rankById} = rankedEntries(state);
    const byId = new Map(entries.map((entry) => [entry.id, entry]));
    tabsEl.querySelectorAll('.graph-tab[data-workflow-id]').forEach((button) => {
      const entry = byId.get(button.dataset.workflowId);
      const sub = button.querySelector('.graph-tab-sub');
      if (!entry || !sub) return;
      const snapshot = entry.snapshot || {};
      const meta = G.graphTabMeta(
        Object.assign({}, snapshot, {started_at: snapshotStartedAt(entry)}),
        rankById.get(entry.id), now, G.nodeProgress(snapshot.nodes || []),
      );
      sub.textContent = [meta.label, meta.relative, meta.duration, meta.progress]
        .filter(Boolean).join(' · ');
    });
  }

  function isRunning(status) {
    return status !== 'declared' && TERMINAL_STATUSES.indexOf(status) === -1;
  }

  // --- D1 图例条 ----------------------------------------------------------

  /** 图例只建一次 DOM（内容与词表同源），之后只切 class 与展开态。 */
  function renderLegend(state) {
    const legend = el('workflow-legend');
    if (!legend) return;
    legend.hidden = false;
    const body = el('legend-body');
    if (body && !body.childElementCount) {
      const model = G.legendModel();
      body.appendChild(legendRow('节点', model.kinds.map(legendKindItem)));
      body.appendChild(legendRow('节点状态', model.statuses.map(legendStatusItem)));
      // 图级终态单列一节（workflow-terminal-honesty D6）：`stalled`（图根本没跑起来）
      // 必须与 `completed` / `budget_exceeded` 在用户眼里可分辨。
      body.appendChild(legendRow('图状态', model.graphStatuses.map(legendGraphStatusItem)));
      body.appendChild(legendRow('边', model.edges.map(legendEdgeItem)));
      body.appendChild(legendRow('线型', model.channels.map(legendChannelItem)));
      // D1：桌面（>720px）默认**展开**，手机默认折叠成一行「图例 ▾」——默认态由
      // 断点决定，之后完全交给用户（同一份 DOM、同一个 class 语义）。
      legend.classList.toggle('collapsed', (window.innerWidth || 1024) <= 720);
      const toggle = el('legend-toggle');
      toggle.setAttribute('aria-expanded', String(!legend.classList.contains('collapsed')));
      toggle.addEventListener('click', () => {
        legend.classList.toggle('collapsed');
        toggle.setAttribute('aria-expanded', String(!legend.classList.contains('collapsed')));
      });
    }
  }

  function legendRow(label, items) {
    const row = document.createElement('div');
    row.className = 'legend-row';
    const name = document.createElement('span');
    name.className = 'legend-label';
    name.textContent = label;
    row.appendChild(name);
    items.forEach((item) => row.appendChild(item));
    return row;
  }

  function legendItem(swatch, label, explanation) {
    const item = document.createElement('span');
    item.className = 'legend-item';
    item.appendChild(swatch);
    const text = document.createElement('span');
    text.textContent = label;
    item.appendChild(text);
    if (explanation) {
      const expl = document.createElement('span');
      expl.className = 'legend-expl';
      expl.textContent = explanation;
      item.appendChild(expl);
    }
    return item;
  }

  function legendKindItem(entry) {
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch legend-swatch-kind';
    swatch.textContent = entry.glyph;
    return legendItem(swatch, entry.label, entry.text);
  }

  function legendStatusItem(entry) {
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch';
    swatch.style.background = entry.color;
    swatch.style.borderStyle = entry.borderStyle === 'solid' ? 'solid' : entry.borderStyle;
    return legendItem(swatch, `${entry.label}${entry.badge ? ` ${entry.badge}` : ''}`, entry.text);
  }

  /** 图级终态的图例项：圆点（与 tab 上的图级圆点同形），带人话解释。 */
  function legendGraphStatusItem(entry) {
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch legend-swatch-dot';
    swatch.style.background = entry.color;
    return legendItem(swatch, entry.label, entry.text);
  }

  function legendEdgeItem(entry) {
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch legend-swatch-line';
    swatch.style.background = entry.color;
    swatch.style.opacity = String(entry.opacity);
    swatch.style.height = `${entry.width}px`;
    if (entry.dash && entry.dash.length) {
      swatch.style.background = `repeating-linear-gradient(90deg, ${entry.color} 0 ${entry.dash[0]}px, transparent ${entry.dash[0]}px ${entry.dash[0] + entry.dash[1]}px)`;
    }
    return legendItem(swatch, entry.label || entry.key, entry.text);
  }

  function legendChannelItem(entry) {
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch legend-swatch-line';
    swatch.style.background = '#94a3b8';
    if (entry.dash && entry.dash.length) {
      swatch.style.background = `repeating-linear-gradient(90deg, #94a3b8 0 ${entry.dash[0]}px, transparent ${entry.dash[0]}px ${entry.dash[0] + entry.dash[1]}px)`;
    }
    return legendItem(swatch, entry.text || entry.key, '');
  }

  function hideLegend() {
    const legend = el('workflow-legend');
    if (legend) legend.hidden = true;
  }

  function renderActiveGraph(tab, state, entry) {
    const snapshot = entry.snapshot;
    if (!snapshot) {
      renderMessage(tab, '等待 workflow 快照…');
      hideNotice();
      hideActions();
      return;
    }

    // G14/D10：超限时**仍然画图**——命中就 `renderMessage + return` 会让用户失去
    // 整幅画面，看不到哪些节点已完成、卡在哪个环。告警条改叠在画布上方。
    renderNotice(snapshot);
    renderActions(tab, state, entry);

    entry.expandedGroups = entry.expandedGroups || new Set();
    const collapsed = G.collapseGraph(snapshot.nodes || [], snapshot.edges || [], {
      threshold: COLLAPSE_THRESHOLD,
      expandedGroups: entry.expandedGroups,
    });
    // 抽屉要用**折叠投影**里的节点（``groupLeader``/``collapsed``/聚合状态都只
    // 在这一层存在——快照的原始节点没有这些）。
    entry.projectedNodes = collapsed.nodes;
    const orientation = G.graphOrientation(window.innerWidth || 1024);
    const layout = G.layoutGraph(collapsed.nodes, collapsed.edges, { orientation });

    drawSvg(tab, entry, layout, orientation);
    renderSummary(tab, snapshot, collapsed, entry);
  }

  /** 抽屉里的节点 = 折叠投影里的那个（带上 ``groupLeader`` 等投影层字段）。 */
  function projectedNode(entry, nodeId) {
    const projected = (entry.projectedNodes || []).find((node) => node.id === nodeId);
    if (projected) return projected;
    return nodesById((entry && entry.snapshot) || {})[nodeId];
  }

  function renderMessage(tab, text, level) {
    const host = el('workflow-canvas');
    if (!host) return;
    host.textContent = '';
    const box = document.createElement('div');
    box.className = level === 'error' ? 'graph-notice error' : 'graph-notice';
    box.textContent = text;
    host.appendChild(box);
  }

  function renderNotice(snapshot) {
    const host = el('workflow-notice');
    if (!host) return;
    const notice = G.graphNotice(snapshot);
    if (!notice) {
      hideNotice();
      return;
    }
    host.hidden = false;
    host.textContent = notice.message;
    host.className = 'workflow-notice error';
  }

  function hideNotice() {
    const host = el('workflow-notice');
    if (host) { host.hidden = true; host.textContent = ''; }
  }

  /** 运行态工具栏（G8 陈旧度 + G18 停止）。 */
  function renderActions(tab, state, entry) {
    const host = el('workflow-actions');
    const stop = el('workflow-stop');
    const freshness = el('workflow-freshness');
    if (!host) return;
    host.hidden = false;
    const snapshot = entry.snapshot || {};
    const age = typeof snapshot.timestamp === 'number'
      ? Date.now() / 1000 - snapshot.timestamp
      : null;
    if (freshness) {
      // G8：图卡住时用户要能区分「慢」与「死」。
      freshness.textContent = age === null ? '' : `最后更新于 ${G.formatAge(age)}`;
    }
    if (stop) {
      // G18：只有**运行中**的图能停。``declared`` 态没有在跑的东西。
      const running = isRunning(snapshot.status || 'declared');
      stop.hidden = !running;
      stop.dataset.workflowId = entry.id;
    }
  }

  function hideActions() {
    const host = el('workflow-actions');
    if (host) host.hidden = true;
  }

  // --- G4/G8 本地计时器（独立于快照） -------------------------------------

  //: 快照只在迁移点到达，两个迁移点之间没有任何重绘事件——没有这个本地计时器，
  //: 节点 elapsed 与「最后更新于 N 秒前」在 A→B 之间就是死的。
  const TICK_INTERVAL_MS = 1000;
  let tickHandle = null;

  function startTicker() {
    if (tickHandle !== null) return;
    tickHandle = window.setInterval(tick, TICK_INTERVAL_MS);
  }

  function stopTicker() {
    if (tickHandle === null) return;
    window.clearInterval(tickHandle);
    tickHandle = null;
  }

  /** 只改**文本节点**，不重建 SVG：每秒一次的全量重绘会打断阅读与手势。 */
  function tick() {
    const tab = activeTab;
    const state = tab && tab.graphState;
    const entry = state && state.graphs.get(state.activeId);
    if (!entry) return;
    const snapshot = entry.snapshot || {};
    const now = Date.now() / 1000;
    const freshness = el('workflow-freshness');
    if (freshness && typeof snapshot.timestamp === 'number') {
      freshness.textContent = `最后更新于 ${G.formatAge(now - snapshot.timestamp)}`;
    }
    // D6：运行中 tab 的「已跑 Xs」也要**实时跳秒**——它跟节点 elapsed 同源，
    // 都靠这个本地计时器，因为快照只在迁移点到达、两帧之间没有重绘事件。
    // 实测曾出现：图跑了 3 分钟，tab 仍写「已跑 5s」，与同屏「最后更新于 19 秒前」
    // 自相矛盾。只改**文本**、不重建 tab DOM（每秒重建会打断点击与焦点）。
    refreshTabMeta(state, now);
    const host = el('workflow-canvas');
    if (!host) return;
    const nodes = nodesById(snapshot);
    host.querySelectorAll('.workflow-node').forEach((group) => {
      const raw = nodes[group.dataset.nodeId];
      const text = group.querySelector('[data-role="status"]');
      if (!raw || !text) return;
      // 折叠组长显示整组聚合状态，计时没有意义（组内成员各自在跑）。
      if (raw.collapsed) return;
      const startedAt = typeof raw.started_at === 'number' ? raw.started_at : null;
      const finishedAt = typeof raw.finished_at === 'number' ? raw.finished_at : null;
      let elapsed = '';
      if (startedAt !== null) {
        // 终态**冻结**为 ``finished_at - started_at``（不再跳秒）。
        elapsed = G.formatElapsed(finishedAt !== null ? finishedAt - startedAt : now - startedAt);
      }
      // **必须走投影层**：``nodeStatusText`` 读的是投影字段（``label``/
      // ``itemsCompleted`` 等），直接喂快照原始节点会把状态词覆写成
      // ``undefined``（曾出的 bug：手机端所有节点每秒变一次 undefined）。
      const node = Object.assign(G.projectNode(raw), { elapsedText: elapsed });
      text.textContent = nodeStatusText(node);
    });
  }

  function renderSummary(tab, snapshot, collapsed, entry) {
    const summaryEl = el('workflow-summary');
    if (!summaryEl) return;
    const nodes = snapshot.nodes || [];
    const counts = {};
    nodes.forEach((node) => {
      counts[node.status] = (counts[node.status] || 0) + 1;
    });
    // D7：报**实际绘制的路径数**，两个数字不等时才给可解释口径——小图（<50 节点）
    // 不发生折叠去重，此时 ``collapsed.edges.length === snapshot.edges.length``，
    // 写死「含并行边/折叠合并」就会在一致时胡说。
    const raw = (snapshot.edges || []).length;
    const parts = [
      `${nodes.length} nodes`,
      G.edgeCountLabel(collapsed.edges.length, raw),
    ];
    if (collapsed.collapsed) {
      parts.push(`${collapsed.groups.length} groups collapsed`);
    }
    Object.keys(counts).sort().forEach((status) => {
      parts.push(`${G.nodeLabel(status)} ${counts[status]}`);
    });
    if (entry && entry.snapshot && typeof entry.snapshot.budget === 'object'
        && entry.snapshot.budget && entry.snapshot.budget.exceeded) {
      parts.push('预算已超限');
    }
    summaryEl.textContent = parts.join(' · ');
  }

  // --- SVG 自绘 -----------------------------------------------------------

  function drawSvg(tab, entry, layout, orientation) {
    const host = el('workflow-canvas');
    if (!host) return;
    host.textContent = '';

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'workflow-svg');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.appendChild(arrowDefs());

    const contentWidth = Math.max(layout.width, 1);
    const contentHeight = Math.max(layout.height, 1);
    const fitted = G.fitToWidth({ width: contentWidth, height: contentHeight },
      host.clientWidth || 720);
    const view = entry.view;
    view.width = contentWidth;
    view.height = contentHeight;
    if (view.zoom === 1 && view.panX === 0 && view.panY === 0 && fitted.scale < 1) {
      view.zoom = fitted.scale;
    }

    const applyViewBox = () => {
      svg.setAttribute('viewBox', G.viewBoxFor({
        zoom: view.zoom,
        panX: view.panX,
        panY: view.panY,
        width: host.clientWidth || contentWidth,
        height: Math.max(host.clientHeight || contentHeight, 200),
      }));
    };

    const edgeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    edgeLayer.setAttribute('class', 'workflow-edges');
    layout.edges.forEach((edge) => edgeLayer.appendChild(renderEdge(edge)));
    svg.appendChild(edgeLayer);

    const nodeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    nodeLayer.setAttribute('class', 'workflow-nodes');
    layout.nodes.forEach((node) => {
      nodeLayer.appendChild(renderNode(node, tab, entry));
    });
    svg.appendChild(nodeLayer);

    host.appendChild(svg);
    applyViewBox();
    attachGestures(svg, host, view, applyViewBox);
    attachSvgWheel(svg, view, applyViewBox);
  }

  /** 箭头 marker（数据边实心、控制边空心——控制边不传数据，语义上要能一眼分开）。 */
  function arrowDefs() {
    const defs = svgEl('defs');
    [['workflow-arrow-active', '#4ade80', true],
     ['workflow-arrow-control', '#60a5fa', false]].forEach(([id, color, filled]) => {
      const marker = svgEl('marker', {
        id, viewBox: '0 0 10 10', refX: 9, refY: 5,
        markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse',
      });
      marker.appendChild(svgEl('path', {
        d: 'M 0 0 L 10 5 L 0 10 z',
        fill: filled ? color : 'none',
        stroke: color,
        'stroke-width': filled ? 0 : 1.6,
      }));
      defs.appendChild(marker);
    });
    return defs;
  }

  function renderEdge(edge) {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'workflow-edge');
    group.dataset.from = edge.from;
    group.dataset.to = edge.to;
    group.dataset.status = edge.status;
    if (edge.kind === 'control') group.classList.add('control');

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', edge.path);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', edge.color);
    path.setAttribute('stroke-width', String(edge.width));
    path.setAttribute('stroke-opacity', String(edge.opacity));
    if (edge.dash && edge.dash.length) {
      path.setAttribute('stroke-dasharray', edge.dash.join(' '));
    }
    if (edge.kind === 'control') {
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('marker-end', 'url(#workflow-arrow-control)');
    } else if (edge.status === 'passed' || edge.status === 'active') {
      path.setAttribute('marker-end', 'url(#workflow-arrow-active)');
    }
    group.appendChild(path);
    return group;
  }

  const NS = 'http://www.w3.org/2000/svg';

  function svgEl(name, attrs) {
    const el = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach((key) => el.setAttribute(key, String(attrs[key])));
    return el;
  }

  function renderNode(node, tab, entry) {
    const group = svgEl('g', { class: 'workflow-node', transform: `translate(${node.x}, ${node.y})` });
    group.dataset.nodeId = node.id;
    group.dataset.status = node.status;
    if (node.collapsed) group.classList.add('collapsed');
    if (node.groupLeader) group.classList.add('group-leader');

    const rect = svgEl('rect', {
      width: node.width,
      height: node.height,
      rx: 10,
      fill: '#16213e',
      stroke: node.color,
      'stroke-width': node.status === 'budget_exceeded' ? 3.4 : 2,
    });
    // 边框形状是第二重编码（D2）：实线 = 已发生，虚线 = 未发生/非终局，
    // 双线 = 被中断。不靠颜色单独承载语义（Airflow 的 failed/upstream_failed
    // 在绿色盲下 ΔE≈0.4 近乎同色，其 AIP-38 因此立规不得仅用颜色表达状态）。
    applyNodeBorder(rect, node.borderStyle);
    group.appendChild(rect);

    // 左侧状态色带：色盲可辨的第二重编码（不只靠颜色）。
    group.appendChild(svgEl('rect', {
      width: 6, height: node.height, rx: 3, fill: node.color,
    }));

    const glyph = svgEl('text', { x: 18, y: 24, class: 'node-glyph', fill: node.color });
    glyph.textContent = node.glyph;
    group.appendChild(glyph);

    const idText = svgEl('text', { x: 38, y: 24, class: 'node-id' });
    idText.textContent = truncate(node.id, 18);
    group.appendChild(idText);

    const statusText = svgEl('text', { x: 18, y: 44, class: 'node-status', fill: node.color });
    statusText.dataset.role = 'status';
    statusText.textContent = nodeStatusText(node);
    // 异常态状态词加粗（第三重编码）。
    if (node.badge) statusText.setAttribute('font-weight', '700');
    group.appendChild(statusText);

    appendNodeBadge(group, node);
    appendForeachBar(group, node);
    appendNodeWhy(group, entry, node);

    const title = svgEl('title');
    title.textContent = nodeTitle(entry, node);
    group.appendChild(title);

    // D4 点击语义拆分（Q2 = B）：点节点**一律开详情**；折叠组的展开/收起收进
    // 详情抽屉（抽屉里给 ``groupLeader`` 一个「展开成员」动作）。不在节点上画
    // 独立控件——那个控件只服务 ≥50 节点的大图，而手机上节点实显仅 27–36px，
    // 「44px 触控目标」在 SVG 坐标里是假的（且 TAP_SLOP=4 后 setPointerCapture
    // 会吃掉 click）。
    group.addEventListener('click', () => openDrawer(tab, entry, node.id));
    return group;
  }

  function applyNodeBorder(rect, borderStyle) {
    if (borderStyle === 'dashed') {
      rect.setAttribute('stroke-dasharray', '6 4');
    } else if (borderStyle === 'double') {
      rect.setAttribute('stroke-dasharray', 'none');
      rect.setAttribute('stroke-width', '3.4');
    }
  }

  /** 状态词/计数行（D5：foreach 容器**常显**「完成 M/N」）。 */
  function nodeStatusText(node) {
    if (node.kind === 'foreach') {
      const done = node.itemsCompleted;
      const total = node.itemCount !== null ? node.itemCount : node.items;
      if (typeof done === 'number' && typeof total === 'number' && total > 0) {
        const failed = node.itemsFailed ? ` · 失败 ${node.itemsFailed}` : '';
        return `完成 ${done}/${total}${failed}`;
      }
      if (typeof total === 'number' && total > 0) {
        // 计数还没到（容器未派发）时退化为项数（D5 口径）。
        return `${node.label} · ${total} 项`;
      }
      return node.label;
    }
    const elapsed = nodeElapsed(node);
    const extra = node.collapsed && node.memberCount
      ? ` · ${node.memberCount} nodes` : '';
    return `${node.label}${extra}${elapsed ? ` · ${elapsed}` : ''}`;
  }

  /** G4：节点 elapsed。运行中的值由**本地计时器**（``tick``）逐秒写入布局投影，
   *  因为快照只在迁移点到达、两帧之间没有重绘事件；终态由 ``tick`` 冻结。 */
  function nodeElapsed(node) {
    return node.elapsedText || '';
  }

  function appendNodeBadge(group, node) {
    if (!node.badge) return;
    group.appendChild(svgEl('circle', {
      cx: node.width, cy: 0, r: 9,
      fill: '#16213e', stroke: node.color, 'stroke-width': 1.4,
    }));
    const text = svgEl('text', {
      x: node.width, y: 3.5, 'text-anchor': 'middle',
      fill: node.color, 'font-size': 10, 'font-weight': 700,
    });
    text.textContent = node.badge;
    group.appendChild(text);
  }

  /** D5.2 迷你堆叠条：N ≤ 20 画 N 个小格，N > 20 退化为按比例宽条。
   *  对标 Dagster 的分区健康条（传范围，不传 N 个状态）。 */
  function appendForeachBar(group, node) {
    if (node.kind !== 'foreach') return;
    const total = node.itemCount !== null && node.itemCount !== undefined
      ? node.itemCount : node.items;
    if (!total) return;
    const states = node.itemStates;
    const width = node.width - 36;
    const y = node.height - 8;
    const segment = (offset, w, color) => svgEl('rect', {
      x: 18 + offset, y, width: Math.max(w, 0.5), height: 3, rx: 1.5, fill: color,
    });
    if (Array.isArray(states) && states.length === total && total <= 20) {
      const gap = 2;
      const each = Math.max((width - gap * (total - 1)) / total, 1.5);
      states.forEach((state, index) => {
        group.appendChild(segment(index * (each + gap), each, itemStateColor(state)));
      });
      return;
    }
    const done = typeof node.itemsCompleted === 'number' ? node.itemsCompleted : 0;
    const failed = typeof node.itemsFailed === 'number' ? node.itemsFailed : 0;
    group.appendChild(segment(0, width, '#3a4460'));
    group.appendChild(segment(0, width * failed / total, G.nodeColor('failed')));
    group.appendChild(segment(0, width * done / total, G.nodeColor('completed')));
  }

  function itemStateColor(state) {
    const encoding = G.statusEncoding(state);
    return encoding && state !== 'pending' ? G.nodeColor(state) : '#3a4460';
  }

  /** D2 的 ``why`` 小字：**只在异常态**出现（正常态不占位），画在节点盒外、
   *  不参与布局计算。 */
  function appendNodeWhy(group, entry, node) {
    const snapshot = (entry && entry.snapshot) || {};
    // 折叠态的组长显示的是整组聚合状态，它的因由由组内成员决定——逐成员解释会
    // 让一行小字变成一段话，所以折叠态不画 why（展开后自然看得到）。
    if (node.collapsed) return;
    const why = G.explainNode(node, snapshot.edges || [], nodesById(snapshot),
      snapshot.status, snapshot.diagnostics || {});
    if (!why) return;
    const text = svgEl('text', { x: 2, y: node.height + 12, class: 'node-why' });
    text.textContent = truncate(why, 34);
    group.appendChild(text);
    text.appendChild(svgEl('title')).textContent = why;
  }

  function nodesById(snapshot) {
    const map = {};
    (snapshot.nodes || []).forEach((node) => { map[node.id] = node; });
    return map;
  }

  /** ``<svg:title>`` 在移动端触屏上不显示——所以它只是桌面端的补充，真正的
   *  摘要出口是详情抽屉（Context 里记录的**功能性缺失**）。 */
  function nodeTitle(entry, node) {
    const snapshot = (entry && entry.snapshot) || {};
    const why = node.collapsed ? null : G.explainNode(node, snapshot.edges || [],
      nodesById(snapshot), snapshot.status, snapshot.diagnostics || {});
    return [`${node.id} [${node.kind}] ${node.label}`, why || '',
      node.task ? truncate(node.task, 200) : '',
      node.summary ? truncate(node.summary, 200) : ''].filter(Boolean).join('\n');
  }

  /**
   * 折叠组展开/收起（D5）——**Q2 = B**：这个动作现在只由详情抽屉触发，
   * 不再由「点节点」承担（点击语义已拆分给「开详情」）。
   */
  function toggleGroup(tab, entry, nodeId) {
    const expanded = entry.expandedGroups || (entry.expandedGroups = new Set());
    if (expanded.has(nodeId)) {
      expanded.delete(nodeId);
    } else {
      expanded.add(nodeId);
    }
    renderPanel(tab);
  }

  // --- 5.2 pinch 缩放 + pan 平移（pointer events） -----------------------

  //: 判定「这是拖动而不是点击」的位移阈值（px）。低于它不 capture、不平移，
  //: 让节点自己的 click（折叠组展开，D5）能正常收到事件。
  const TAP_SLOP = 4;

  function attachGestures(svg, host, view, applyViewBox) {
    const pointers = new Map();
    //: 已经 setPointerCapture 过的 pointerId。按**指针**记而不是一个布尔位：
    //: 双指 pinch 时第一根手指可能已经进入拖动、第二根才落下，两者状态不同步。
    const captured = new Set();
    let lastCentroid = null;
    let lastDistance = null;
    let dragOrigin = null;

    const capture = (pointerId) => {
      if (captured.has(pointerId)) return;
      captured.add(pointerId);
      // capture 让手指移出元素后仍收得到 move；合成事件（测试）没有活跃
      // pointer，抛错不影响手势本身，故吞掉。
      try {
        if (host.setPointerCapture) host.setPointerCapture(pointerId);
      } catch (_error) { /* pointer 不活跃：忽略 */ }
    };

    host.addEventListener('pointerdown', (event) => {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 1) {
        lastCentroid = { x: event.clientX, y: event.clientY };
        dragOrigin = { x: event.clientX, y: event.clientY };
      } else {
        // 第二根手指落下 = pinch，不再是「点击」——双指手势不产生 click，
        // 立刻 capture 不会吃掉节点的点击，还能保住移出元素后的 move 事件。
        capture(event.pointerId);
      }
      // 单指按下时**不能**立刻 capture：pointer capture 会把随后的 click 一并
      // 重定向到 host，节点上的 click（折叠组展开，D5）就永远收不到。单指的
      // capture 推迟到位移超过阈值、确定是拖动而不是点击时（见 pointermove）。
    });

    host.addEventListener('pointermove', (event) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = Array.from(pointers.values());

      if (!captured.has(event.pointerId)) {
        if (!dragOrigin) dragOrigin = { x: event.clientX, y: event.clientY };
        const far = points.length >= 2
          ? distanceOf(points[0], points[1]) > TAP_SLOP
          : Math.abs(event.clientX - dragOrigin.x) > TAP_SLOP
            || Math.abs(event.clientY - dragOrigin.y) > TAP_SLOP;
        if (!far) return; // 还在「点击」范围内：不动图、不 capture
        capture(event.pointerId);
      }

      if (points.length >= 2) {
        const centroid = centroidOf(points);
        const distance = distanceOf(points[0], points[1]);
        if (lastDistance !== null && distance > 0) {
          const next = G.applyPinch(view, distance / lastDistance, centroid.x, centroid.y);
          Object.assign(view, next);
        }
        lastDistance = distance;
        lastCentroid = centroid;
        applyViewBox();
        return;
      }

      if (lastCentroid) {
        const dx = event.clientX - lastCentroid.x;
        const dy = event.clientY - lastCentroid.y;
        if (dx || dy) {
          Object.assign(view, G.applyPan(view, dx, dy));
          lastCentroid = { x: event.clientX, y: event.clientY };
          applyViewBox();
        }
      }
    });

    const release = (event) => {
      pointers.delete(event.pointerId);
      captured.delete(event.pointerId);
      if (pointers.size < 2) lastDistance = null;
      const remaining = Array.from(pointers.values());
      lastCentroid = remaining.length ? remaining[0] : null;
      if (!pointers.size) {
        lastCentroid = null;
        dragOrigin = null;
      }
    };
    host.addEventListener('pointerup', release);
    host.addEventListener('pointercancel', release);
    host.addEventListener('pointerleave', release);
  }

  function attachSvgWheel(svg, view, applyViewBox) {
    // 桌面滚轮：ctrl/⌘ + 滚轮缩放，与触摸 pinch 走同一套 viewBox 变换。
    svg.addEventListener('wheel', (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
      Object.assign(view, G.applyPinch(view, factor, event.clientX, event.clientY));
      applyViewBox();
    }, { passive: false });
  }

  function centroidOf(points) {
    const total = points.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }),
      { x: 0, y: 0 });
    return { x: total.x / points.length, y: total.y / points.length };
  }

  function distanceOf(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function truncate(text, limit) {
    const value = String(text || '');
    return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
  }

  // --- D4 节点详情抽屉 ----------------------------------------------------

  /** 抽屉的关闭语义（Escape / 遮罩 / × 三处共用）。 */
  function closeDrawer(state) {
    // 抽屉关了就别再轮询 transcript（否则会对一个不存在的面板持续发请求）。
    if (window.AsterwyndWorkflowTranscript
        && window.AsterwyndWorkflowTranscript.stopAutoRefresh) {
      window.AsterwyndWorkflowTranscript.stopAutoRefresh();
    }
    const drawer = el('workflow-drawer');
    const scrim = el('workflow-scrim');
    if (drawer) drawer.classList.remove('open');
    if (scrim) scrim.classList.remove('open');
    if (state) state.drawer = null;
    // 关闭后焦点回到触发它的节点（D4 的无障碍要求）。
    const openNode = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest('.workflow-node') : null;
    if (openNode && typeof openNode.blur === 'function') openNode.blur();
  }

  function openDrawer(tab, entry, nodeId) {
    const state = tab && tab.graphState;
    if (!state) return;
    state.drawer = {entry, nodeId};
    state.drawerTab = 'task';
    const drawer = el('workflow-drawer');
    const scrim = el('workflow-scrim');
    if (drawer) {
      drawer.hidden = false;
      drawer.classList.add('open');
    }
    if (scrim) {
      scrim.hidden = false;
      scrim.classList.add('open');
    }
    // focus trap：打开的瞬间把焦点移进抽屉，键盘用户不会落在画布上。
    const close = el('drawer-close');
    if (close && typeof close.focus === 'function') close.focus();
    renderDrawer(state, entry);
  }

  function renderDrawer(state, entry) {
    const current = state && state.drawer;
    const drawer = el('workflow-drawer');
    if (!drawer || !current) return;
    if (current.entry !== entry) return;
    const node = projectedNode(entry, current.nodeId);
    if (!node) {
      closeDrawer(state);
      return;
    }
    const kindEl = el('drawer-kind');
    const idEl = el('drawer-id');
    const badgeEl = el('drawer-badge');
    const statusEl = el('drawer-status');
    if (idEl) idEl.textContent = node.id;
    if (kindEl) kindEl.textContent = node.kind;
    if (badgeEl) {
      badgeEl.textContent = G.statusEncoding(node.status).badge || '●';
      badgeEl.style.color = G.nodeColor(node.status);
    }
    if (statusEl) {
      statusEl.textContent = G.nodeLabel(node.status);
      statusEl.style.color = G.nodeColor(node.status);
    }
    document.querySelectorAll('.drawer-tab').forEach((button) => {
      const active = button.dataset.tab === state.drawerTab;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    const body = el('drawer-body');
    if (!body) return;
    body.textContent = '';
    if (state.drawerTab === 'task') renderDrawerTask(body, state, entry, node);
    else if (state.drawerTab === 'output') renderDrawerOutput(body, node);
    else renderDrawerConvo(body, state, entry, node);
  }

  function drawerWhy(entry, node) {
    const snapshot = (entry && entry.snapshot) || {};
    return G.explainNode(node, snapshot.edges || [], nodesById(snapshot),
      snapshot.status, snapshot.diagnostics || {});
  }

  function kvRow(body, key, value) {
    const k = document.createElement('span');
    k.className = 'kv-key';
    k.textContent = key;
    const v = document.createElement('span');
    v.textContent = value;
    body.appendChild(k);
    body.appendChild(v);
  }

  function renderDrawerTask(body, state, entry, node) {
    const snapshot = (entry && entry.snapshot) || {};
    void state;
    const list = document.createElement('div');
    list.className = 'kv';
    kvRow(list, '状态', G.nodeLabel(node.status));
    kvRow(list, '类型', node.kind);
    const startedAt = typeof node.started_at === 'number' ? node.started_at : null;
    const finishedAt = typeof node.finished_at === 'number' ? node.finished_at : null;
    kvRow(list, '耗时', startedAt === null ? '—'
      : G.formatElapsed((finishedAt === null ? Date.now() / 1000 : finishedAt) - startedAt));
    kvRow(list, 'runs', String(node.runs || 0));
    body.appendChild(list);

    const why = drawerWhy(entry, node);
    if (why) {
      const box = document.createElement('div');
      box.className = 'drawer-why';
      box.textContent = why;
      body.appendChild(box);
    }

    // Q2 = B：折叠组的展开/收起是抽屉里的动作，不在节点上画独立控件。
    if (node.groupLeader) {
      const expanded = entry.expandedGroups && entry.expandedGroups.has(node.id);
      const action = document.createElement('button');
      action.type = 'button';
      action.className = 'drawer-action';
      action.dataset.action = 'toggle-group';
      action.textContent = expanded ? '收起成员' : '展开成员';
      action.addEventListener('click', () => {
        toggleGroup(activeTab, entry, node.id);
      });
      body.appendChild(action);
    }

    appendSection(body, '任务', node.task || '—');

    // G15：route 的判定诊断——既有实现在图正常完成时一个字都不显示。
    if (node.kind === 'route') {
      appendSection(body, '判定结果', node.targets && node.targets.length
        ? `命中出口：→ ${node.targets.join('、')}` : '未命中任何出口（走 default）');
      const misses = (snapshot.diagnostics || {}).route_ref_misses;
      if (misses) {
        appendSection(body, '判定诊断', formatRouteMisses(misses));
      }
    }
    if (node.kind === 'foreach' && typeof node.items === 'number') {
      appendSection(body, '并行项', `${node.items} 项`);
    }
  }

  function formatRouteMisses(misses) {
    if (Array.isArray(misses)) return misses.map((item) => String(item)).join('\n');
    if (typeof misses === 'object') {
      return Object.keys(misses).map((key) => `${key}: ${misses[key]}`).join('\n');
    }
    return String(misses);
  }

  function appendSection(body, title, text) {
    const heading = document.createElement('h3');
    heading.textContent = title;
    body.appendChild(heading);
    const content = document.createElement('div');
    content.className = 'drawer-text';
    content.textContent = text;
    body.appendChild(content);
  }

  function renderDrawerOutput(body, node) {
    appendSection(body, 'summary', node.summary ? truncate(node.summary, 2000) : '（无产出）');
    if (node.summary && node.summary.length >= 400) {
      const note = document.createElement('p');
      note.className = 'drawer-note';
      note.textContent = '快照里的 summary 已截断到 400 字符；全文见「对话」tab。';
      body.appendChild(note);
    }
    appendSection(body, 'result_ref', node.result_ref || '—');
  }

  function renderDrawerConvo(body, state, entry, node) {
    const pane = document.createElement('div');
    pane.className = 'drawer-convo';
    body.appendChild(pane);
    if (!window.AsterwyndWorkflowTranscript) {
      pane.textContent = '该会话未在本进程加载对话内容。';
      return;
    }
    // 懒加载（D4）：切到「对话」tab 才发请求、才建 DOM。
    // ``node`` 一并交给它：刷新节律要判「这个节点是不是还在跑」（纯函数
    // ``transcriptRefreshDue`` 需要 status）。
    window.AsterwyndWorkflowTranscript.render(pane, {
      sessionId: activeTab ? activeTab.sessionId : null,
      workflowId: entry.id,
      nodeId: node.id,
      node,
    });
  }

  function bindDrawerChrome() {
    const drawer = el('workflow-drawer');
    if (!drawer || drawer.dataset.bound) return;
    drawer.dataset.bound = '1';
    const close = el('drawer-close');
    if (close) close.addEventListener('click', () => closeDrawer(activeTab && activeTab.graphState));
    const scrim = el('workflow-scrim');
    if (scrim) scrim.addEventListener('click', () => closeDrawer(activeTab && activeTab.graphState));
    drawer.querySelectorAll('.drawer-tab').forEach((button) => {
      button.addEventListener('click', () => {
        const state = activeTab && activeTab.graphState;
        if (!state) return;
        state.drawerTab = button.dataset.tab;
        renderPanel(activeTab);
      });
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      const state = activeTab && activeTab.graphState;
      if (state && state.drawer) closeDrawer(state);
    });
  }

  // --- G18 停止运行中的图（WS ``cancel_workflow``） -----------------------

  function bindStopButton() {
    const stop = el('workflow-stop');
    if (!stop || stop.dataset.bound) return;
    stop.dataset.bound = '1';
    stop.addEventListener('click', () => {
      const state = activeTab && activeTab.graphState;
      const entry = state && state.graphs.get(state.activeId);
      if (!entry) return;
      const label = (entry.snapshot && entry.snapshot.goal) || entry.id;
      // 二次确认：取消**不可逆**（``_cancelled``/``_accepting`` 全仓无复位点），
      // 所以文案必须说清「已跑的 run 会写 checkpoint，但工作流本身不能续」。
      const ok = window.confirm(
        `确定要停止「${truncate(label, 40)}」吗？\n\n`
        + '停止不可撤销：已完成的节点结果会保留并写下 checkpoint，'
        + '但这次 workflow 本身无法继续。');
      if (!ok) return;
      if (typeof window.AsterwyndWorkflowStop === 'function') {
        window.AsterwyndWorkflowStop(entry.id);
      }
    });
  }

  function init() {
    bindDrawerChrome();
    bindStopButton();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.AsterwyndWorkflow = {
    createGraphState,
    handleWorkflowEvent,
    renderPanel,
    bindTab,
    hideTab,
    closeDrawer,
    startTicker,
    stopTicker,
    TERMINAL_STATUSES,
    MAX_TERMINAL_TABS,
    COLLAPSE_THRESHOLD,
  };
})();
