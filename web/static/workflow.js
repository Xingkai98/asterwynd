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

  const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'budget_exceeded',
    'graph_recursion_exceeded'];
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
      return;
    }

    renderGraphTabs(tab, state);
    const entry = state.graphs.get(state.activeId) || firstGraph(state);
    if (!entry) return;
    state.activeId = entry.id;
    renderActiveGraph(tab, state, entry);
  }

  function firstGraph(state) {
    let found = null;
    state.graphs.forEach((entry) => { if (!found) found = entry; });
    return found;
  }

  function renderGraphTabs(tab, state) {
    const tabsEl = el('workflow-tabs');
    if (!tabsEl) return;
    tabsEl.hidden = state.graphs.size <= 1;
    tabsEl.textContent = '';
    state.graphs.forEach((entry) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'graph-tab';
      if (entry.id === state.activeId) button.classList.add('active');
      const status = (entry.snapshot && entry.snapshot.status) || 'pending';
      button.dataset.status = status;
      const dot = document.createElement('span');
      dot.className = 'graph-tab-dot';
      dot.style.background = G.nodeColor(status);
      button.appendChild(dot);
      const label = document.createElement('span');
      label.className = 'graph-tab-label';
      const goal = (entry.snapshot && entry.snapshot.goal) || entry.goal || '';
      label.textContent = goal ? truncate(goal, 24) : entry.id;
      button.appendChild(label);
      const badge = document.createElement('span');
      badge.className = 'graph-tab-status';
      badge.textContent = G.nodeLabel(status);
      button.appendChild(badge);
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

  function renderActiveGraph(tab, state, entry) {
    const snapshot = entry.snapshot;
    if (!snapshot) {
      renderMessage(tab, '等待 workflow 快照…');
      return;
    }

    // Q6/决策 9：超限只渲染告警条，**不**按 nodes.length 判断、不画图。
    const notice = G.graphNotice(snapshot);
    if (notice) {
      renderMessage(tab, notice.message, 'error');
      return;
    }

    const collapsed = G.collapseGraph(snapshot.nodes || [], snapshot.edges || [], {
      threshold: COLLAPSE_THRESHOLD,
    });
    const orientation = G.graphOrientation(window.innerWidth || 1024);
    const layout = G.layoutGraph(collapsed.nodes, collapsed.edges, {
      orientation,
      expandedGroups: entry.expandedGroups,
    });

    drawSvg(tab, entry, layout, orientation);
    renderSummary(tab, snapshot, collapsed);
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

  function renderSummary(tab, snapshot, collapsed) {
    const summaryEl = el('workflow-summary');
    if (!summaryEl) return;
    const nodes = snapshot.nodes || [];
    const counts = {};
    nodes.forEach((node) => {
      counts[node.status] = (counts[node.status] || 0) + 1;
    });
    const parts = [
      `${nodes.length} nodes`,
      `${(snapshot.edges || []).length} edges`,
    ];
    if (collapsed.collapsed) {
      parts.push(`${collapsed.groups.length} groups collapsed`);
    }
    Object.keys(counts).sort().forEach((status) => {
      parts.push(`${G.nodeLabel(status)} ${counts[status]}`);
    });
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

    const rect = svgEl('rect', {
      width: node.width,
      height: node.height,
      rx: 10,
      fill: '#16213e',
      stroke: node.color,
      'stroke-width': 2,
    });
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
    const extra = node.collapsed && node.itemCount !== null
      ? ` · ${node.itemCount} items`
      : (node.collapsed ? ` · ${node.memberCount} nodes` : '');
    statusText.textContent = `${node.label}${extra}`;
    group.appendChild(statusText);

    const title = svgEl('title');
    title.textContent = `${node.id} [${node.kind}] ${node.label}`
      + (node.summary ? `\n${truncate(node.summary, 200)}` : '');
    group.appendChild(title);

    group.addEventListener('click', () => toggleGroup(tab, entry, node));
    return group;
  }

  /**
   * 点击折叠组切换局部展开（D5）；非折叠节点点击无效。
   *
   * 注意：``node`` 是**布局后**的投影，带 ``collapsed`` 标记；展开时要把组长 id 交给
   * 折叠算法（``expandedGroups``）才能真的看到成员。
   */
  function toggleGroup(tab, entry, node) {
    if (!node.collapsed) return;
    const expanded = entry.expandedGroups || (entry.expandedGroups = new Set());
    if (expanded.has(node.id)) {
      expanded.delete(node.id);
    } else {
      expanded.add(node.id);
    }
    renderPanel(tab);
  }

  // --- 5.2 pinch 缩放 + pan 平移（pointer events） -----------------------

  function attachGestures(svg, host, view, applyViewBox) {
    const pointers = new Map();
    let lastCentroid = null;
    let lastDistance = null;

    host.addEventListener('pointerdown', (event) => {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 1) {
        lastCentroid = { x: event.clientX, y: event.clientY };
      }
      // capture 让手指移出元素后仍收得到 move；合成事件（测试）没有活跃 pointer，
      // 抛错不影响手势本身，故吞掉。
      try {
        if (host.setPointerCapture) host.setPointerCapture(event.pointerId);
      } catch (_error) { /* pointer 不活跃：忽略 */ }
    });

    host.addEventListener('pointermove', (event) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = Array.from(pointers.values());

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
      if (pointers.size < 2) lastDistance = null;
      const remaining = Array.from(pointers.values());
      lastCentroid = remaining.length ? remaining[0] : null;
      if (!pointers.size) lastCentroid = null;
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

  window.AsterwyndWorkflow = {
    createGraphState,
    handleWorkflowEvent,
    renderPanel,
    bindTab,
    hideTab,
    TERMINAL_STATUSES,
    MAX_TERMINAL_TABS,
    COLLAPSE_THRESHOLD,
  };
})();
