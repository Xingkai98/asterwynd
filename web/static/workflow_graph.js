// web/static/workflow_graph.js
// Workflow 运行态流程图的**纯函数层**（change workflow-graph-visualization，D1/D5/D7）。
//
// 与 DOM 完全解耦：分层布局、状态→颜色/线型映射、折叠归类、缩放平移变换都在这里，
// 由 node + vm 单测覆盖（Q7 的验收路径）——CI 里没有浏览器也能真跑。渲染层
// （workflow.js）只负责把这层的输出画成 SVG。
//
// 数据来源是 scheduler 的 workflow_graph_snapshot()：
//   {workflow_id, spec_hash, goal, status, nodes[], edges[], timestamp}
//   node: {id, kind, status, runs, summary, started_at, finished_at, targets?, items?}
//   edge: {from, to, channel, required, reducer, kind, status}
(function () {
  'use strict';

  // --- 3.2 状态映射 -------------------------------------------------------

  //: 节点七档（与 scheduler 的终态集合对齐；budget_exceeded 是独立终态）。
  const NODE_COLORS = {
    pending: '#94a3b8',
    started: '#60a5fa',
    completed: '#4ade80',
    failed: '#f87171',
    cancelled: '#64748b',
    blocked: '#facc15',
    budget_exceeded: '#fb923c',
  };
  const DEFAULT_NODE_COLOR = NODE_COLORS.pending;

  const NODE_LABELS = {
    pending: 'pending',
    started: 'running',
    completed: 'completed',
    failed: 'failed',
    cancelled: 'cancelled',
    blocked: 'blocked',
    budget_exceeded: 'budget exceeded',
  };

  //: 边五档。``opacity`` 与 ``width`` 是「强调度」：passed/active 醒目，inactive 退到背景。
  const EDGE_STYLES = {
    inactive: { color: '#475569', opacity: 0.28, width: 1.4, dash: [] },
    ready: { color: '#94a3b8', opacity: 0.6, width: 1.8, dash: [] },
    active: { color: '#60a5fa', opacity: 0.95, width: 2.6, dash: [] },
    passed: { color: '#4ade80', opacity: 0.9, width: 2.2, dash: [] },
    blocked: { color: '#f87171', opacity: 0.75, width: 2.0, dash: [5, 4] },
  };
  const DEFAULT_EDGE_STYLE = EDGE_STYLES.inactive;

  //: channel 只决定线型（D3）：summary/result_ref 实线、artifact 虚线、bus 点线。
  const CHANNEL_DASH = {
    summary: [],
    result_ref: [],
    artifact: [7, 5],
    bus: [2, 4],
  };

  const KIND_GLYPHS = {
    subagent: 'S',
    aggregate: 'A',
    route: 'R',
    foreach: 'F',
  };

  function nodeColor(status) {
    return NODE_COLORS[status] || DEFAULT_NODE_COLOR;
  }

  function nodeLabel(status) {
    return NODE_LABELS[status] || String(status || 'unknown');
  }

  function nodeColors() {
    return Object.assign({}, NODE_COLORS);
  }

  function edgeStatusStyles() {
    return JSON.parse(JSON.stringify(EDGE_STYLES));
  }

  function edgeStyle(edge) {
    const base = EDGE_STYLES[(edge && edge.status) || ''] || DEFAULT_EDGE_STYLE;
    return Object.assign({}, base, { dash: channelDash(edge && edge.channel) });
  }

  function channelDash(channel) {
    const dash = CHANNEL_DASH[channel];
    return dash ? dash.slice() : [];
  }

  function kindGlyph(kind) {
    return KIND_GLYPHS[kind] || '?';
  }

  // --- 3.2/5.1 分层布局 ---------------------------------------------------

  const NODE_WIDTH = 168;
  const NODE_HEIGHT = 58;
  const LAYER_GAP_H = 96;   // 横向布局的层间距（x 方向）
  const LAYER_GAP_V = 84;   // 纵向布局的层间距（y 方向）
  const SIBLING_GAP_H = 28; // 横向布局的同层节点间距（y 方向）
  const SIBLING_GAP_V = 26; // 纵向布局的同层节点间距（x 方向）
  const CONTENT_PADDING = 32;

  /**
   * 把图按最长路径分层（layer 0 = 根/入口）。
   *
   * 环（route 回边）会让纯拓扑分层不收敛，所以先做一次 DFS 去掉回边，再在无环
   * 子图上做最长路径——保证「gate 一定在 work 下游」这类直觉关系成立。
   */
  function assignLayers(nodes, edges) {
    const ids = nodes.map((node) => node.id);
    const idSet = new Set(ids);
    const forward = new Map(ids.map((id) => [id, []]));
    const backEdges = new Set();
    const adjacency = new Map(ids.map((id) => [id, []]));

    (edges || []).forEach((edge, index) => {
      if (!idSet.has(edge.from) || !idSet.has(edge.to)) return;
      adjacency.get(edge.from).push({ to: edge.to, index });
    });

    // DFS 找回边（指向当前栈上的节点）。
    const state = new Map(); // 0=未访问 1=在栈 2=完成
    const stack = [];
    function dfs(nodeId) {
      state.set(nodeId, 1);
      stack.push(nodeId);
      for (const link of adjacency.get(nodeId) || []) {
        const mark = state.get(link.to) || 0;
        if (mark === 1) {
          backEdges.add(link.index);
        } else if (mark === 0) {
          dfs(link.to);
        }
      }
      stack.pop();
      state.set(nodeId, 2);
    }
    ids.forEach((id) => {
      if ((state.get(id) || 0) === 0) dfs(id);
    });

    const indegree = new Map(ids.map((id) => [id, 0]));
    (edges || []).forEach((edge, index) => {
      if (backEdges.has(index)) return;
      if (!idSet.has(edge.from) || !idSet.has(edge.to)) return;
      indegree.set(edge.to, indegree.get(edge.to) + 1);
      forward.get(edge.from).push(edge.to);
    });

    const layers = new Map(ids.map((id) => [id, 0]));
    // Kahn 拓扑序 + 最长路径松弛。
    const queue = ids.filter((id) => indegree.get(id) === 0);
    const seen = new Set();
    while (queue.length) {
      const id = queue.shift();
      if (seen.has(id)) continue;
      seen.add(id);
      for (const next of forward.get(id) || []) {
        layers.set(next, Math.max(layers.get(next), layers.get(id) + 1));
        indegree.set(next, indegree.get(next) - 1);
        if (indegree.get(next) === 0) queue.push(next);
      }
    }
    // 无环子图上不该有残留，但环里被断开的节点用「入边最大值」兜底收敛。
    for (let pass = 0; pass < 2; pass += 1) {
      (edges || []).forEach((edge, index) => {
        if (backEdges.has(index)) return;
        if (!idSet.has(edge.from) || !idSet.has(edge.to)) return;
        layers.set(edge.to, Math.max(layers.get(edge.to), layers.get(edge.from) + 1));
      });
    }

    const result = {};
    ids.forEach((id) => { result[id] = layers.get(id); });
    return result;
  }

  /**
   * 分层布局：把 nodes/edges 变成带坐标的 SVG 元素描述。
   *
   * 桌面（``horizontal``）层沿 +x 排布（左→右 DAG）；手机（``vertical``）层沿 +y
   * 排布（上→下 DAG）——同一份分层数据只换坐标轴方向（D7）。
   */
  function layoutGraph(nodes, edges, options) {
    const opts = options || {};
    const orientation = opts.orientation === 'vertical' ? 'vertical' : 'horizontal';
    if (!nodes || !nodes.length) {
      return { nodes: [], edges: [], width: 0, height: 0, orientation };
    }
    const layers = assignLayers(nodes, edges);
    const buckets = new Map();
    nodes.forEach((node) => {
      const layer = layers[node.id] || 0;
      if (!buckets.has(layer)) buckets.set(layer, []);
      buckets.get(layer).push(node);
    });

    const layerKeys = Array.from(buckets.keys()).sort((a, b) => a - b);
    // 同层内按原始顺序稳定排列，保证两次渲染的坐标一致（无动画过渡，靠稳定布局）。
    // ``placed`` 存**完整节点盒**（含 width/height）：``edgePath`` 依赖它算端点。
    const placed = new Map();
    layerKeys.forEach((layer) => {
      const group = buckets.get(layer);
      group.forEach((node, index) => {
        if (orientation === 'horizontal') {
          placed.set(node.id, {
            x: CONTENT_PADDING + layer * (NODE_WIDTH + LAYER_GAP_H),
            y: CONTENT_PADDING + index * (NODE_HEIGHT + SIBLING_GAP_H),
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
          });
        } else {
          placed.set(node.id, {
            x: CONTENT_PADDING + index * (NODE_WIDTH + SIBLING_GAP_V),
            y: CONTENT_PADDING + layer * (NODE_HEIGHT + LAYER_GAP_V),
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
          });
        }
      });
    });

    const layoutNodes = nodes.map((node) => {
      const position = placed.get(node.id);
      return {
        id: node.id,
        kind: node.kind,
        status: node.status,
        summary: node.summary || '',
        runs: node.runs || 0,
        items: node.items === undefined ? null : node.items,
        targets: node.targets || [],
        collapsed: Boolean(node.collapsed),
        memberCount: node.memberCount || 0,
        itemCount: node.itemCount === undefined ? null : node.itemCount,
        color: nodeColor(node.status),
        label: nodeLabel(node.status),
        glyph: kindGlyph(node.kind),
        x: position.x,
        y: position.y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      };
    });

    const layoutEdges = (edges || []).map((edge) => {
      const from = placed.get(edge.from);
      const to = placed.get(edge.to);
      const style = edgeStyle(edge);
      const item = {
        from: edge.from,
        to: edge.to,
        kind: edge.kind,
        status: edge.status,
        channel: edge.channel,
        color: style.color,
        opacity: style.opacity,
        width: style.width,
        dash: style.dash,
        path: '',
      };
      if (from && to) item.path = edgePath(from, to, orientation);
      return item;
    });

    let width = 0;
    let height = 0;
    layoutNodes.forEach((node) => {
      width = Math.max(width, node.x + node.width);
      height = Math.max(height, node.y + node.height);
    });

    return {
      nodes: layoutNodes,
      edges: layoutEdges,
      width: width + CONTENT_PADDING,
      height: height + CONTENT_PADDING,
      orientation,
    };
  }

  /** 端点之间的三次贝塞尔（水平布局从左出右入，纵向布局从上出下入）。 */
  function edgePath(from, to, orientation) {
    if (orientation === 'vertical') {
      const sx = from.x + from.width / 2;
      const sy = from.y + from.height;
      const tx = to.x + to.width / 2;
      const ty = to.y;
      const bend = Math.max((ty - sy) / 2, 16);
      return `M ${sx} ${sy} C ${sx} ${sy + bend} ${tx} ${ty - bend} ${tx} ${ty}`;
    }
    const sx = from.x + from.width;
    const sy = from.y + from.height / 2;
    const tx = to.x;
    const ty = to.y + to.height / 2;
    const bend = Math.max((tx - sx) / 2, 16);
    return `M ${sx} ${sy} C ${sx + bend} ${sy} ${tx - bend} ${ty} ${tx} ${ty}`;
  }

  // --- 5.1 跨端断点 -------------------------------------------------------

  /** 复用既有 720 主断点（D7）：>720 横向上→下... 即左→右，≤720 上→下。 */
  function graphOrientation(viewportWidth) {
    return Number(viewportWidth) > 720 ? 'horizontal' : 'vertical';
  }

  /** 手机端自动 fit 到屏宽：内容比视口宽时给出 <1 的 scale。 */
  function fitToWidth(content, viewportWidth) {
    const width = Math.max(Number(content && content.width) || 0, 1);
    const height = Math.max(Number(content && content.height) || 0, 1);
    const target = Math.max(Number(viewportWidth) || 0, 1);
    const scale = width > target ? target / width : 1;
    return { scale, width: width * scale, height: height * scale };
  }

  // --- 5.2 缩放平移 -------------------------------------------------------

  const MIN_ZOOM = 0.25;
  const MAX_ZOOM = 4;

  function clampZoom(value) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  }

  /**
   * viewBox 由 (zoom, pan) 推出；SVG 只换 viewBox，不改元素坐标（D7 的缩放平移实现）。
   *
   * 坐标语义：``panX``/``panY`` 是把内容平移的像素量（手指拖动方向）。内容右移
   * ``panX`` 等于视口左上角在内容坐标里左移，所以 viewBox 原点是 ``-panX``。
   */
  function viewBoxFor(state) {
    const zoom = clampZoom(Number(state.zoom) || 1);
    const panX = Number(state.panX) || 0;
    const panY = Number(state.panY) || 0;
    const width = Number(state.width) || 0;
    const height = Number(state.height) || 0;
    return `${round(-panX)} ${round(-panY)} ${round(width / zoom)} ${round(height / zoom)}`;
  }

  function applyPinch(state, factor, originX, originY) {
    const zoom = clampZoom((Number(state.zoom) || 1) * (Number(factor) || 1));
    return { zoom, panX: Number(state.panX) || 0, panY: Number(state.panY) || 0 };
  }

  function applyPan(state, deltaX, deltaY) {
    return {
      zoom: Number(state.zoom) || 1,
      panX: (Number(state.panX) || 0) + (Number(deltaX) || 0),
      panY: (Number(state.panY) || 0) + (Number(deltaY) || 0),
    };
  }

  function round(value) {
    return Math.round(value * 1000) / 1000;
  }

  // --- 4.1 规模分级 / 折叠 ------------------------------------------------

  const DEFAULT_COLLAPSE_THRESHOLD = 50;

  /** 折叠组判据（决策 8）：``kind == "foreach"`` 或 ``__auto_agg__`` 前缀。 */
  function isAutoNode(node) {
    return typeof node.id === 'string' && node.id.indexOf('__auto_agg__') === 0;
  }

  function isCollapsibleContainer(node) {
    return node.kind === 'foreach' || isAutoNode(node);
  }

  /** 折叠组聚合状态（D5）：failed 赢，其次 running，其次受阻，全 completed 才 completed。 */
  function groupStatus(statuses) {
    const list = (statuses || []).filter(Boolean);
    if (!list.length) return 'pending';
    if (list.indexOf('failed') !== -1) return 'failed';
    if (list.indexOf('started') !== -1) return 'running';
    if (list.some((s) => s === 'pending' || s === 'blocked' || s === 'budget_exceeded')) {
      return 'blocked';
    }
    if (list.every((s) => s === 'completed')) return 'completed';
    return list[0];
  }

  /**
   * 把图投影成折叠形态（D5）。折叠只是**视觉投影**：不改快照节点身份和状态。
   *
   * 分组规则：
   * - ``kind == "foreach"`` 的容器节点与其后继中的 auto 层节点合成一组（容器为组长）；
   * - 同属一个下游（数据出边集合相同）的 auto 层节点合成一组。
   *
   * 组内被隐藏的节点，其边改写成「组长 ↔ 外部端点」，保证折叠后流向仍完整。
   */
  function collapseGraph(nodes, edges, options) {
    const opts = options || {};
    const threshold = opts.threshold === undefined ? DEFAULT_COLLAPSE_THRESHOLD : opts.threshold;
    // 用户手动展开过的组（D5「点击展开局部」）：这些组的成员保持可见。
    const expanded = opts.expandedGroups instanceof Set
      ? opts.expandedGroups
      : new Set(opts.expandedGroups || []);
    const allNodes = nodes || [];
    const allEdges = edges || [];
    if (allNodes.length < threshold) {
      return { nodes: allNodes.slice(), edges: allEdges.slice(), groups: [], collapsed: false };
    }

    const byId = new Map(allNodes.map((node) => [node.id, node]));
    const groupOf = new Map(); // node id -> group id（组长 id）
    const groups = new Map();

    function ensureGroup(leaderId, kind) {
      if (!groups.has(leaderId)) {
        groups.set(leaderId, {
          id: leaderId,
          kind,
          memberIds: [],
          statuses: [],
          itemCount: null,
        });
      }
      return groups.get(leaderId);
    }

    allNodes.forEach((node) => {
      if (node.kind === 'foreach') {
        const group = ensureGroup(node.id, 'foreach');
        group.memberIds.push(node.id);
        group.statuses.push(node.status);
        group.itemCount = node.items === undefined ? null : node.items;
        groupOf.set(node.id, node.id);
      }
    });

    // auto 层节点：优先并进「把数据边打给它的 foreach 容器」组；否则按共同下游分组。
    const autoNodes = allNodes.filter(isAutoNode);
    const autoToLeader = new Map();
    autoNodes.forEach((node) => {
      const upstream = allEdges.filter((edge) => edge.to === node.id);
      const foreachUpstream = upstream
        .map((edge) => byId.get(edge.from))
        .find((candidate) => candidate && candidate.kind === 'foreach');
      if (foreachUpstream) {
        autoToLeader.set(node.id, foreachUpstream.id);
        return;
      }
      const successors = allEdges
        .filter((edge) => edge.from === node.id)
        .map((edge) => edge.to)
        .sort()
        .join('|');
      autoToLeader.set(node.id, `__auto_group__${successors || node.id}`);
    });

    autoNodes.forEach((node) => {
      const leaderId = autoToLeader.get(node.id);
      const group = ensureGroup(leaderId, 'auto');
      group.memberIds.push(node.id);
      group.statuses.push(node.status);
      groupOf.set(node.id, leaderId);
    });

    // 组长必须是可见节点：auto 组的组长不是真节点时，用组内第一个成员当代表。
    groups.forEach((group) => {
      if (!byId.has(group.id)) {
        group.id = group.memberIds[0];
        group.kind = 'auto';
      }
      group.status = groupStatus(group.statuses);
      group.memberCount = group.memberIds.length;
      group.memberIds.forEach((id) => groupOf.set(id, group.id));
    });

    // 隐藏除组长以外的成员；被用户手动展开的组不隐藏（D5 的局部展开）。
    const hidden = new Set();
    groups.forEach((group) => {
      if (expanded.has(group.id)) return;
      group.memberIds.forEach((id) => {
        if (id !== group.id) hidden.add(id);
      });
    });

    const visibleNodes = allNodes
      .filter((node) => !hidden.has(node.id))
      .map((node) => {
        const group = groups.get(node.id);
        if (!group || group.memberIds.length <= 1 || expanded.has(group.id)) {
          return Object.assign({}, node);
        }
        return Object.assign({}, node, {
          collapsed: true,
          memberCount: group.memberCount,
          itemCount: group.itemCount,
          status: node.status,
          groupStatus: group.status,
        });
      });

    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    const rewired = [];
    const seenPairs = new Set();
    allEdges.forEach((edge) => {
      const from = groupOf.has(edge.from) ? groupOf.get(edge.from) : edge.from;
      const to = groupOf.has(edge.to) ? groupOf.get(edge.to) : edge.to;
      if (from === to) return;
      if (!visibleIds.has(from) || !visibleIds.has(to)) return;
      const key = `${from}->${to}:${edge.kind}`;
      if (seenPairs.has(key)) return;
      seenPairs.add(key);
      rewired.push(Object.assign({}, edge, { from, to }));
    });

    return {
      nodes: visibleNodes,
      edges: rewired,
      groups: Array.from(groups.values()),
      collapsed: true,
    };
  }

  // --- 4.1/Q6 超限告警（不读 nodes.length，决策 9） -----------------------

  function graphNotice(snapshot) {
    if (!snapshot || snapshot.status !== 'graph_recursion_exceeded') return null;
    const diagnostics = snapshot.diagnostics || {};
    const limit = diagnostics.recursion_limit !== undefined && diagnostics.recursion_limit !== null
      ? diagnostics.recursion_limit
      : null;
    const reason = diagnostics.reason || 'graph_recursion_exceeded';
    const parts = [`图超限，已停止执行（reason: ${reason}`];
    if (limit !== null) parts.push(`, limit: ${limit}`);
    parts.push('）');
    return {
      level: 'error',
      reason,
      limit,
      message: parts.join(''),
    };
  }

  //: 声明期被拒（无 scheduler、无图）的提示——前端把 tool error 与 workflow error
  //: 分成两条路径（Q6），这条只负责后者；前者由工具返回的文本走 chat 消息渲染。
  function declarationRejectedNotice(errorText) {
    return {
      level: 'error',
      reason: 'workflow_declaration_rejected',
      message: `Workflow 声明被拒（未产生运行图）：${String(errorText || '').trim()}`,
    };
  }

  window.AsterwyndWorkflowGraph = {
    NODE_COLORS,
    EDGE_STYLES,
    CHANNEL_DASH,
    NODE_WIDTH,
    NODE_HEIGHT,
    MIN_ZOOM,
    MAX_ZOOM,
    nodeColor,
    nodeLabel,
    nodeColors,
    edgeStyle,
    edgeStatusStyles,
    channelDash,
    kindGlyph,
    assignLayers,
    layoutGraph,
    edgePath,
    graphOrientation,
    fitToWidth,
    clampZoom,
    viewBoxFor,
    applyPinch,
    applyPan,
    isAutoNode,
    isCollapsibleContainer,
    groupStatus,
    collapseGraph,
    graphNotice,
    declarationRejectedNotice,
  };
})();
