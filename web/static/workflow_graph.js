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

  //: 节点八档（与 scheduler 的终态集合对齐；budget_exceeded 是独立终态）。
  //: ``skipped``（D2b）是「route 条件判断没走这条」的**良性终态**——它与
  //: ``blocked``（被上游/预算连累）的区别正是本 change 的立项命题之一，所以配色
  //: 刻意选**冷灰蓝**、与 ``blocked`` 的黄拉开明度差（不只拉色相：灰度/色觉障碍
  //: 下也要分得开，WCAG 1.4.1 不得仅用颜色表达状态）。
  const NODE_COLORS = {
    pending: '#94a3b8',
    started: '#60a5fa',
    completed: '#4ade80',
    failed: '#f87171',
    cancelled: '#64748b',
    blocked: '#facc15',
    budget_exceeded: '#fb923c',
    skipped: '#7f8ea8',
  };
  const DEFAULT_NODE_COLOR = NODE_COLORS.pending;

  const NODE_LABELS = {
    pending: 'pending',
    started: 'running',
    completed: 'completed',
    failed: 'failed',
    cancelled: 'cancelled',
    blocked: 'blocked',
    budget_exceeded: '预算超限',
    skipped: '未选中',
  };

  //: G3（M2.6）的 ``queued`` 是**投影层**状态（「已派发、在等执行 slot」），
  //: scheduler 侧不写它。前端要单独给一档，否则排队项会显示成 running。
  const QUEUED_COLOR = '#3b82f6';
  const QUEUED_LABEL = '排队中';

  //: 状态的四重编码（D2）：色 + 角标 + 边框形状 + 状态词。
  //: **角标字形只用默认字体普遍覆盖的字符**——实测 ``⏸``（U+23F8）在多数系统
  //: 字体缺失，会渲染成豆腐块（□），所以预算档用 ``‖`` 而不是暂停符。
  //: 边框语汇沿用 Temporal：实线 = 已发生，虚线 = 未发生/非终局，双线 = 被中断。
  const STATUS_ENCODINGS = {
    pending: { badge: '', borderStyle: 'solid' },
    started: { badge: '', borderStyle: 'solid' },
    completed: { badge: '', borderStyle: 'solid' },
    failed: { badge: '✕', borderStyle: 'solid' },
    cancelled: { badge: '⊝', borderStyle: 'solid' },
    blocked: { badge: '⊘', borderStyle: 'dashed' },
    budget_exceeded: { badge: '‖', borderStyle: 'double' },
    skipped: { badge: '—', borderStyle: 'dashed' },
  };

  //: 边六档（第 6 档 ``satisfied`` 见 issue #207）。``opacity`` 与 ``width`` 是「强调度」：
  //: passed/active 醒目，inactive 退到背景；``satisfied`` 介于其间（依赖满足但无数据流）。
  const EDGE_STYLES = {
    inactive: { color: '#475569', opacity: 0.28, width: 1.4, dash: [] },
    ready: { color: '#94a3b8', opacity: 0.6, width: 1.8, dash: [] },
    active: { color: '#60a5fa', opacity: 0.95, width: 2.6, dash: [] },
    passed: { color: '#4ade80', opacity: 0.9, width: 2.2, dash: [] },
    // issue #207：依赖已满足、但产出**未被**下游读取（纯顺序/门控边）。
    // 与 passed 同色系以示「都起了作用」，靠**明度 + 线宽**（+ 无箭头，见
    // workflow.js 的 renderEdge）与 passed / inactive 区分。
    satisfied: { color: '#86efac', opacity: 0.55, width: 1.6, dash: [] },
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

  //: 图级状态走**独立词表**（D10）：``NODE_COLORS`` 是**节点**状态词表，有精确
  //: 相等契约测试；把图级状态（``running``/``declared``/``completed_with_failures``
  //: /``graph_recursion_exceeded``）塞进去会污染它，也会让 tab 圆点退化成兜底灰。
  const GRAPH_STATUS_COLORS = {
    declared: '#94a3b8',
    running: '#60a5fa',
    completed: '#4ade80',
    //: G26：跑完了但有节点失败——不能显示成绿的，否则用户根本不会去看哪里失败。
    completed_with_failures: '#fbbf24',
    //: workflow-terminal-honesty（#217）：图根本没跑起来。取**深琥珀**（比
    //: budget_exceeded 的橙 #fb923c 更暗、更褐），到每个既有档的 RGB 欧氏距离
    //: ≥ 100（既有最近的一对 completed_with_failures↔budget_exceeded 仅 51）。
    //: 复用 budget_exceeded 的橙会让「预算耗尽而停」与「结构性停」混淆。
    stalled: '#92400e',
    failed: '#f87171',
    cancelled: '#64748b',
    budget_exceeded: '#fb923c',
    graph_recursion_exceeded: '#f472b6',
  };
  const GRAPH_STATUS_LABELS = {
    declared: '已声明',
    running: 'running',
    completed: 'completed',
    completed_with_failures: '有失败',
    stalled: '停滞（无节点完成）',
    failed: 'failed',
    cancelled: 'cancelled',
    budget_exceeded: '预算超限',
    graph_recursion_exceeded: '图超限',
  };

  function nodeColor(status) {
    if (status === 'queued') return QUEUED_COLOR;
    return NODE_COLORS[status] || DEFAULT_NODE_COLOR;
  }

  function nodeLabel(status) {
    if (status === 'queued') return QUEUED_LABEL;
    return NODE_LABELS[status] || String(status || 'unknown');
  }

  function graphStatusColor(status) {
    return GRAPH_STATUS_COLORS[status] || DEFAULT_NODE_COLOR;
  }

  function graphStatusLabel(status) {
    return GRAPH_STATUS_LABELS[status] || String(status || 'unknown');
  }

  function graphStatusColors() {
    return Object.assign({}, GRAPH_STATUS_COLORS);
  }

  function graphStatusTexts() {
    return Object.assign({}, GRAPH_STATUS_TEXT);
  }

  function statusEncodings() {
    return JSON.parse(JSON.stringify(STATUS_ENCODINGS));
  }

  /** 节点状态的编码（色 + 角标 + 边框形状）；``queued`` 走投影态那一档。 */
  function statusEncoding(status) {
    if (status === 'queued') return { badge: '', borderStyle: 'solid' };
    return STATUS_ENCODINGS[status] || { badge: '', borderStyle: 'solid' };
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

  function channelNames() {
    return Object.keys(CHANNEL_DASH);
  }

  function kindGlyph(kind) {
    return KIND_GLYPHS[kind] || '?';
  }

  function kindGlyphs() {
    return Object.assign({}, KIND_GLYPHS);
  }

  // --- D1 图例（内容模型与词表同源，单测锁定不漂移） ----------------------

  //: 图级终态的**人话解释**（workflow-terminal-honesty D6）：图级状态与节点状态是
  //: 两套词表，图例必须能解释「这张图为什么停在这个终态」——尤其 `stalled`
  //: （图根本没跑起来）与 `completed`/`budget_exceeded` 的区分。
  const GRAPH_STATUS_TEXT = {
    declared: '已声明，尚未开跑',
    running: '正在跑',
    completed: '所有节点成功完成',
    completed_with_failures: '跑完了，但有节点失败',
    stalled: '图收敛时没有任何节点成功执行（互等 / 全被挡）',
    failed: '没有任何节点成功，且有节点失败',
    cancelled: '被取消',
    budget_exceeded: '预算耗尽而停',
    graph_recursion_exceeded: '图级闸门（步数/节点数/路由数）超限',
  };

  //: 每档状态的**人话解释**（D1：图例条目不是裸术语）。与 D2 的因果文案同源。
  const NODE_STATUS_TEXT = {
    pending: '等待上游完成',
    started: '正在执行',
    completed: '成功完成',
    failed: '自身执行失败',
    cancelled: '被取消，未跑完',
    blocked: '被上游或预算挡住，未执行',
    budget_exceeded: '预算耗尽主动停止',
    skipped: '条件判断没走这条分支，未选中（≠ 失败）',
  };
  const NODE_KIND_TEXT = {
    subagent: '子代理：一个节点跑一个 subagent',
    foreach: '并行展开：一个容器内并发跑 N 项',
    route: '条件分支：按标签二选一，不产生对话',
    aggregate: '聚合：把上游产出合并成一份',
  };
  const EDGE_STATUS_TEXT = {
    inactive: '无数据可传',
    ready: '上游已就绪，等待下游',
    active: '源或目标正在运行',
    passed: '数据已被下游读取',
    satisfied: '依赖已满足，但产出未被下游读取',
    blocked: '目标无法继续',
  };
  const CHANNEL_TEXT = {
    summary: 'summary / result_ref（实线）',
    result_ref: 'summary / result_ref（实线）',
    artifact: 'artifact（虚线）',
    bus: 'bus（点线）',
  };

  /** 去重后的 channel 列表（线型相同只留一个代表，保持 ``CHANNEL_DASH`` 的键序）。 */
  function uniqueChannels() {
    const seen = new Set();
    const out = [];
    Object.keys(CHANNEL_DASH).forEach((key) => {
      const signature = CHANNEL_DASH[key].join(',');
      if (seen.has(signature)) return;
      seen.add(signature);
      out.push(key);
    });
    return out;
  }

  /**
   * 图例的内容模型（D1）：**从词表同源生成**——改 ``NODE_COLORS`` 等词表时图例
   * 自动跟随，不会出现「图变了、图例没变」。返回结构直接喂渲染层。
   */
  function legendModel() {
    return {
      kinds: Object.keys(KIND_GLYPHS).map((key) => ({
        key,
        glyph: KIND_GLYPHS[key],
        label: key,
        text: NODE_KIND_TEXT[key] || '',
      })),
      statuses: Object.keys(NODE_COLORS).map((key) => ({
        key,
        color: NODE_COLORS[key],
        label: NODE_LABELS[key] || key,
        badge: (STATUS_ENCODINGS[key] || {}).badge || '',
        borderStyle: (STATUS_ENCODINGS[key] || {}).borderStyle || 'solid',
        text: NODE_STATUS_TEXT[key] || '',
      })),
      // 图级终态是**独立词表**（D10），单列一节——节点状态与图级状态混在一行
      // 会让用户以为 ``completed``（节点）与 ``completed``（图）是同一个东西。
      graphStatuses: Object.keys(GRAPH_STATUS_COLORS).map((key) => ({
        key,
        color: GRAPH_STATUS_COLORS[key],
        label: GRAPH_STATUS_LABELS[key] || key,
        text: GRAPH_STATUS_TEXT[key] || '',
      })),
      edges: Object.keys(EDGE_STYLES).map((key) => ({
        key,
        color: EDGE_STYLES[key].color,
        opacity: EDGE_STYLES[key].opacity,
        width: EDGE_STYLES[key].width,
        dash: EDGE_STYLES[key].dash.slice(),
        text: EDGE_STATUS_TEXT[key] || '',
      })),
      // channel 按**去重后的线型**出图例：summary 与 result_ref 画出来是同一条
      // 实线，各占一行只会让图例变长而没有信息量。
      channels: uniqueChannels().map((key) => ({
        key,
        dash: CHANNEL_DASH[key].slice(),
        text: CHANNEL_TEXT[key] || key,
      })),
    };
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
   * 把一个**快照原始节点**投影成渲染层读的字段（snake_case → camelCase + 派生
   * 颜色/状态词/角标）。
   *
   * **单一投影来源**：``layoutGraph`` 与渲染层的本地计时器（``tick``）都必须用它。
   * 曾出的 bug：``tick`` 图省事直接把快照原始节点喂给 ``nodeStatusText``，而后者
   * 读的是投影字段（``label`` 等），于是每秒一次的重绘把状态词覆写成 ``undefined``。
   */
  function projectNode(node) {
    const encoding = statusEncoding(node.status);
    return {
      id: node.id,
      kind: node.kind,
      status: node.status,
      summary: node.summary || '',
      reason: node.reason || '',
      runs: node.runs || 0,
      items: node.items === undefined ? null : node.items,
      targets: node.targets || [],
      collapsed: Boolean(node.collapsed),
      groupLeader: Boolean(node.groupLeader),
      memberCount: node.memberCount || 0,
      itemCount: node.itemCount === undefined ? null : node.itemCount,
      // foreach 的并行进度（G7/D5）：折叠态下由折叠算法补齐，展开态直接用节点自带值。
      itemsCompleted: node.items_completed === undefined ? null : node.items_completed,
      itemsFailed: node.items_failed === undefined ? null : node.items_failed,
      itemsRunning: node.items_running === undefined ? null : node.items_running,
      itemStates: node.item_states || null,
      color: nodeColor(node.status),
      label: nodeLabel(node.status),
      glyph: kindGlyph(node.kind),
      badge: encoding.badge,
      borderStyle: encoding.borderStyle,
    };
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
      return Object.assign(projectNode(node), {
        x: position.x,
        y: position.y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });

    // 并行边偏移（D7）：同一对 ``(from,to)`` 的多条边如果都画同一条三次贝塞尔，
    // 会在画布上**完全重合**——用户看到 1 条线，统计却说 3 条。这里先按
    // ``(from,to)`` 预扫出每条边的 ``k``（序号）与 ``n``（总数），再等距铺开
    // （igraph ``curve_multiple`` 的思路）。
    //
    // 分组键用 ``(from,to)`` 而**不是** ``(from,to,kind)``：同一对端点上控制边与
    // 数据边不会共存（route 的出边全被判为控制边），用两元组更简单、也不会因为
    // 未来新增 kind 而漏铺。``edgePath`` 是对外导出的 API，偏移走**可选参数**。
    const pairTotals = new Map();
    (edges || []).forEach((edge) => {
      const key = `${edge.from}->${edge.to}`;
      pairTotals.set(key, (pairTotals.get(key) || 0) + 1);
    });
    const pairSeen = new Map();

    const layoutEdges = (edges || []).map((edge) => {
      const from = placed.get(edge.from);
      const to = placed.get(edge.to);
      const style = edgeStyle(edge);
      const key = `${edge.from}->${edge.to}`;
      const index = pairSeen.get(key) || 0;
      pairSeen.set(key, index + 1);
      const offset = parallelEdgeOffset(index, pairTotals.get(key) || 1);
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
        offset,
        path: '',
      };
      if (from && to) item.path = edgePath(from, to, orientation, offset);
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

  //: 同一对节点多条边时的法向间距（px）。8–10 是「分得开、又不至于跑到别的节点上」
  //: 的区间；n 很大时总展宽会超界，所以另有 ``PARALLEL_EDGE_LIMIT`` 收敛。
  const PARALLEL_EDGE_DELTA = 9;
  //: 同对边数超过它就不再逐条铺开（总展宽太大，看起来像扇形），改为按上限收敛。
  const PARALLEL_EDGE_LIMIT = 8;

  /**
   * 端点之间的三次贝塞尔（水平布局从左出右入，纵向布局从上出下入）。
   *
   * ``offset`` 是**可选**的法向偏移（D7 的并行边铺开）：水平布局偏移 y、纵向偏移
   * x。默认 0 → 与 #190 的旧行为逐字一致（`edgePath` 是对外导出的 API）。
   */
  function edgePath(from, to, orientation, offset) {
    const shift = clampEdgeOffset(offset);
    if (orientation === 'vertical') {
      const sx = from.x + from.width / 2 + shift;
      const sy = from.y + from.height;
      const tx = to.x + to.width / 2 + shift;
      const ty = to.y;
      const bend = Math.max((ty - sy) / 2, 16);
      return `M ${sx} ${sy} C ${sx} ${sy + bend} ${tx} ${ty - bend} ${tx} ${ty}`;
    }
    const sx = from.x + from.width;
    const sy = from.y + from.height / 2 + shift;
    const tx = to.x;
    const ty = to.y + to.height / 2 + shift;
    const bend = Math.max((tx - sx) / 2, 16);
    return `M ${sx} ${sy} C ${sx + bend} ${sy} ${tx - bend} ${ty} ${tx} ${ty}`;
  }

  /** 偏移量收敛到有限值（防 NaN/undefined 漏进 SVG 路径变成 ``M NaN``）。 */
  function clampEdgeOffset(offset) {
    const value = Number(offset);
    if (!Number.isFinite(value)) return 0;
    const bound = (PARALLEL_EDGE_LIMIT - 1) / 2 * PARALLEL_EDGE_DELTA;
    return Math.max(-bound, Math.min(bound, value));
  }

  /** 同对 n 条边时第 k 条的偏移（对称铺开，和为 0）。 */
  function parallelEdgeOffset(index, total) {
    const count = Math.max(Math.trunc(Number(total)) || 1, 1);
    const position = Math.min(Math.max(Math.trunc(Number(index)) || 0, 0), count - 1);
    if (count <= 1) return 0;
    return clampEdgeOffset((position - (count - 1) / 2) * PARALLEL_EDGE_DELTA);
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

  /**
   * 折叠组聚合状态（D5）：failed 赢，其次运行中，其次受阻，全 completed 才 completed。
   *
   * 返回值必须落在**节点状态词表**内（``NODE_COLORS`` 的键），否则 ``nodeColor``
   * 会落到兜底灰：D5 口语里的「running」对应的状态名是 ``started``。
   */
  function groupStatus(statuses) {
    const list = (statuses || []).filter(Boolean);
    if (!list.length) return 'pending';
    if (list.indexOf('failed') !== -1) return 'failed';
    if (list.indexOf('started') !== -1) return 'started';
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
        if (!group || group.memberIds.length <= 1) {
          return Object.assign({}, node);
        }
        // ``groupLeader`` 与折叠与否无关：展开态也要保留，否则用户展开后无法再点回收起。
        if (expanded.has(group.id)) {
          return Object.assign({}, node, { groupLeader: true });
        }
        return Object.assign({}, node, {
          groupLeader: true,
          collapsed: true,
          memberCount: group.memberCount,
          itemCount: group.itemCount,
          // D5「折叠组聚合状态」：折叠后组长显示的是**整组**的状态，不是它自己的。
          status: group.status,
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

  // --- D2 异常态因果（「为什么是这个状态」） ------------------------------

  //: 图级停止原因（D2）：这几档是**更强的**停止原因，``blocked`` 的因果要优先引用
  //: 它们，而不是沿着边去猜「被哪个上游挡住」。
  const GRAPH_STOP_REASONS = {
    budget_exceeded: '流程因预算超限被停止，该节点没来得及执行',
    cancelled: '流程被取消，该节点没来得及执行',
    graph_recursion_exceeded: '流程因图超限被停止，该节点没来得及执行',
  };

  function truncateText(text, limit) {
    const value = String(text === undefined || text === null ? '' : text);
    if (!limit || value.length <= limit) return value;
    return `${value.slice(0, Math.max(limit - 1, 1))}…`;
  }

  function formatTokens(value) {
    const number = Number(value) || 0;
    if (number >= 1000) return `${(number / 1000).toFixed(1)}k`;
    return String(Math.round(number));
  }

  /**
   * 一句人话的「为什么是这个状态」（D2）。正常态返回 ``null``（不占位）。
   *
   * 签名**必须**收图级 ``status``/``diagnostics``（G12 的修正）：原签名只看单个
   * 节点，而「图级停止原因优先」这条规则在那种签名下**无法实现**。
   *
   * ``blocked`` 的扫描要**穿过 blocked 上游**：本调度器里上游 ``failed`` 时下游
   * 会被照常派发（``failed`` 在 ``TERMINAL_NODE_STATUSES`` 里），所以 ``blocked``
   * 的真正来源是收尾时整条链一起 blocked——只扫 ``failed``/``cancelled`` 在整条
   * 链上一无所获，会落到兜底句。也**不取** ``finished_at`` 最早的那个：最早只
   * 说明它先失败、不代表它是原因。
   */
  function explainNode(node, edges, nodesById, graphStatus, diagnostics) {
    if (!node) return null;
    const status = node.status;
    const byId = nodesById || {};
    const list = edges || [];
    const diag = diagnostics || {};

    if (status === 'failed') {
      const reason = node.reason || '';
      return reason
        ? `节点自身执行失败：${truncateText(reason, 160)}`
        : '节点自身执行失败（没有留下错误详情）';
    }

    if (status === 'skipped') {
      return '条件判断没走这条分支：它本来就不该跑（不是失败，也不是被挡住）';
    }

    if (status === 'cancelled') {
      return '流程被取消，该节点未执行完';
    }

    if (status === 'budget_exceeded') {
      const budget = diag.budget || {};
      const dimension = budget.exceeded_dimension || null;
      const dims = budget.dimensions || {};
      const numbers = dimension && dims[dimension]
        ? `（${dimension}：用掉 ${formatTokens(dims[dimension].used)} / 上限 ${formatTokens(dims[dimension].limit)}）`
        : '';
      const reason = node.reason ? `：${truncateText(node.reason, 80)}` : '';
      return `预算超限${numbers}后停止${reason}`;
    }

    if (status === 'blocked') {
      // 优先级 0（workflow-terminal-honesty Q4）：节点自身的**具体因由**。
      // 后端 D3 把真实成因（图级闸门名+上限 / 「入边互等」）写进了 ``node.reason``，
      // 但下面两条泛化规则会把它遮蔽——用户看到「流程因图超限被停止」而看不到
      // `max_routes` 与上限值，等于 #218 在用户可见层面没修。只有携带**具体信息**
      // 的 reason 才提权；纯兜底句仍走下面的泛化路径（那里更准确）。
      if (isSpecificNodeReason(node.reason)) return truncateText(node.reason, 160);
      // 优先级 1：图级停止原因——它比「沿边找上游」更准确。
      if (GRAPH_STOP_REASONS[graphStatus]) return GRAPH_STOP_REASONS[graphStatus];
      // 优先级 2：沿数据入边向上**穿透 blocked 上游**，收集全部未完成/失败的上游。
      const roots = blockingUpstreams(node.id, list, byId);
      if (roots.length) return `被上游 ${roots.join('、')} 挡住，未执行`;
      // 优先级 3：自身 reason 兜底。
      if (node.reason) return truncateText(node.reason, 160);
      return '流程结束前该节点一直未就绪';
    }

    return null;
  }

  //: 后端 ``_resolve_pending_status`` 的因由分档标记（workflow-terminal-honesty D3）。
  //: 这两个片段出现即说明 reason 携带了**具体成因**，不是无区分度的兜底句——
  //: 前端据此把它提到泛化文案之前（Q4）。
  const SPECIFIC_REASON_MARKERS = ['图级闸门', '入边互相等待'];

  /** 该 reason 是否携带具体成因（而非兜底句）。纯函数，便于测试。 */
  function isSpecificNodeReason(reason) {
    const value = String(reason || '');
    if (!value) return false;
    //: 兜底句本身没有信息量，不得提权（否则会遮掉更准确的图级/上游说明）。
    if (value === 'workflow ended before the node became ready') return false;
    return SPECIFIC_REASON_MARKERS.some((marker) => value.includes(marker));
  }

  //: 因果句里最多列几个上游 id（bounded：大图上一条链可能有几十个未完成上游）。
  const WHY_UPSTREAM_LIMIT = 5;

  /**
   * 收集「卡住这个节点」的全部上游：沿数据入边向上**穿透**，一路收集未完成的上游。
   *
   * 「穿透」是必需的（G12）：本调度器里上游 ``failed`` 时下游会被照常派发，
   * 所以 ``blocked`` 的真正来源是收尾时**整条链一起** blocked——只扫
   * ``failed``/``cancelled`` 会在整条链上一无所获，落到没回答问题的兜底句。
   */
  function blockingUpstreams(nodeId, edges, nodesById) {
    const found = [];
    const visited = new Set([nodeId]);
    const queue = [nodeId];
    while (queue.length) {
      const current = queue.shift();
      edges
        .filter((edge) => edge.to === current)
        .forEach((edge) => {
          if (visited.has(edge.from)) return;
          visited.add(edge.from);
          const upstream = nodesById[edge.from];
          if (!upstream) return;
          if (upstream.status === 'completed') return;  // 已完成的上游不解释任何事
          found.push(edge.from);
          queue.push(edge.from);  // 继续向上：它自己可能也只是被连累的中转
        });
    }
    return found;
  }

  // --- D6/D7 tab 元信息与统计 --------------------------------------------

  function nodeProgress(nodes) {
    const counts = { completed: 0, failed: 0, running: 0, total: 0 };
    (nodes || []).forEach((node) => {
      counts.total += 1;
      const status = node && node.status;
      if (status === 'completed') counts.completed += 1;
      else if (status === 'failed' || status === 'budget_exceeded') counts.failed += 1;
      else if (status === 'started' || status === 'queued') counts.running += 1;
    });
    return counts;
  }

  function progressLabel(progress) {
    if (!progress || !progress.total) return '';
    return `${progress.completed}/${progress.total}`;
  }

  /**
   * ``#N`` = 按图级 ``started_at`` 排序的秩（D6，**Q3 用户裁决定案选 A**）。
   *
   * 排序也按编号——「按时间编号 + 运行中排最前」的组合必然产生非单调序列
   * （长跑 wf1 + 快结 wf2/wf3 → tab 读作 ``#1 #3 #2``）。运行中改用徽标区分。
   *
   * ``_workflows`` 永不注销，WS 重连补发会把前端早已淘汰的图塞回来——按
   * ``started_at`` 现算秩能跨整页刷新稳定；拿 Map 插入下标当序号则做不到
   * （``pruneGraphs`` 会 delete 条目）。
   *
   * ``started_at == null``（``declared`` 态，D3 的哨兵统一）当 **unknown**，
   * 排到最后——绝不按 epoch 0 排到最前。
   */
  function rankGraphs(entries) {
    const list = (entries || []).map((entry, index) => ({
      entry,
      index,
      startedAt: entry && typeof entry.started_at === 'number' ? entry.started_at : null,
    }));
    list.sort((a, b) => {
      if (a.startedAt === null && b.startedAt === null) return a.index - b.index;
      if (a.startedAt === null) return 1;
      if (b.startedAt === null) return -1;
      if (a.startedAt !== b.startedAt) return a.startedAt - b.startedAt;
      return a.index - b.index;
    });
    return list.map((item, position) => Object.assign({}, item.entry, { rank: position + 1 }));
  }

  function formatElapsed(seconds) {
    const total = Math.max(Math.floor(Number(seconds) || 0), 0);
    if (total < 60) return `${total}s`;
    if (total < 3600) {
      const minutes = Math.floor(total / 60);
      return `${minutes}m${total % 60}s`;
    }
    return `${Math.floor(total / 3600)}h${Math.floor((total % 3600) / 60)}m`;
  }

  function formatAge(seconds) {
    const total = Math.max(Math.floor(Number(seconds) || 0), 0);
    if (total < 60) return `${total} 秒前`;
    if (total < 3600) return `${Math.floor(total / 60)} 分钟前`;
    if (total < 86400) return `${Math.floor(total / 3600)} 小时前`;
    return `${Math.floor(total / 86400)} 天前`;
  }

  /**
   * 多图 tab 的元信息（D6）。``now`` 由调用方传入（纯函数层不读时钟，便于测试）。
   *
   * ``M/N`` 由**前端从 snapshot.nodes 自算**（``progress`` 参数），不用快照的
   * ``total/completed/failed``——那是逻辑单元口径（foreach 容器按 N+1 计），
   * 且 running 帧根本不带（G6）。
   */
  function graphTabMeta(entry, rank, now, progress) {
    const snapshot = entry || {};
    const status = snapshot.status || 'pending';
    const startedAt = typeof snapshot.started_at === 'number' ? snapshot.started_at : null;
    const finishedAt = typeof snapshot.finished_at === 'number' ? snapshot.finished_at : null;
    const isRunning = GRAPH_STATUS_COLORS[status] && !isGraphTerminal(status);
    let relative = '';
    let duration = '';
    if (startedAt !== null) {
      if (isRunning || finishedAt === null) {
        duration = formatElapsed(now - startedAt);
        relative = `已跑 ${duration}`;
      } else {
        duration = formatElapsed(finishedAt - startedAt);
        relative = formatAge(now - finishedAt);
      }
    }
    return {
      rank,
      status,
      label: graphStatusLabel(status),
      relative,
      duration,
      progress: progressLabel(progress),
      title: snapshot.goal || snapshot.id || '',
    };
  }

  //: 图级终态集合（与 ``workflow.js`` 的 ``TERMINAL_STATUSES`` 和 scheduler 的
  //: ``_SNAPSHOT_TERMINAL_STATUSES`` 同义，这里按词表判）。三副本必须**集合相等**
  //: （契约测试锁定）——漏一个就会让该图在 tab 上被当成 running。
  function isGraphTerminal(status) {
    return status === 'completed' || status === 'completed_with_failures'
      || status === 'stalled' || status === 'failed' || status === 'cancelled'
      || status === 'budget_exceeded' || status === 'graph_recursion_exceeded';
  }

  //: 「对话」tab 的自动刷新间隔（秒）。design D4 要求**定死刷新节律**：既不是
  //: 「打开取一次、之后永不更新」（用户的抱怨会被当成已经处理完），也不是跟着
  //: 每个快照重排（会打断阅读）。只在节点**未到终态**时轮询——跑完了就没有新
  //: 内容，再轮询纯属浪费。
  const TRANSCRIPT_REFRESH_S = 10;

  /**
   * 「此刻要不要重取这条 transcript」（M3.8 的刷新节律，纯函数便于测试）。
   *
   * - 暂停 → 永不重取（用户正在读）；
   * - 节点已终态 → 不再重取（不会再有新消息）；
   * - 否则距上次取数达到 ``TRANSCRIPT_REFRESH_S`` 才重取。
   */
  function transcriptRefreshDue(node, options) {
    const opts = options || {};
    if (opts.paused) return false;
    if (!node || isTerminalNodeStatus(node.status)) return false;
    const last = typeof opts.lastFetchedAt === 'number' ? opts.lastFetchedAt : null;
    if (last === null) return true;
    const now = typeof opts.now === 'number' ? opts.now : 0;
    return now - last >= TRANSCRIPT_REFRESH_S;
  }

  /** 该节点状态是否已终态（不再有新内容）。 */
  function isTerminalNodeStatus(status) {
    return status === 'completed' || status === 'failed' || status === 'cancelled'
      || status === 'blocked' || status === 'budget_exceeded' || status === 'skipped';
  }

  /**
   * 统计行的边口径（D7）：报**实际绘制的路径数**，两个数字不等时才给可解释口径。
   *
   * 小图（<50 节点）不发生折叠去重，`collapsed.edges.length === snapshot.edges.length`
   * ——所以文案不能写死「含并行边/折叠合并」，否则在一致时也会胡说。
   */
  function edgeCountLabel(paths, rawEdges) {
    const drawn = Number(paths) || 0;
    const raw = Number(rawEdges) || 0;
    if (drawn === raw) return `${drawn} paths`;
    return `${drawn} paths（原始 ${raw} edges）`;
  }

  // --- 4.1/Q6 超限告警（不读 nodes.length，决策 9） -----------------------

  function graphNotice(snapshot) {
    if (!snapshot || snapshot.status !== 'graph_recursion_exceeded') return null;
    const diagnostics = snapshot.diagnostics || {};
    const limit = diagnostics.recursion_limit !== undefined && diagnostics.recursion_limit !== null
      ? diagnostics.recursion_limit
      : null;
    const reason = diagnostics.reason || 'graph_recursion_exceeded';
    const currentNodes = Array.isArray(diagnostics.current_nodes)
      ? diagnostics.current_nodes.slice()
      : [];
    const steps = diagnostics.steps !== undefined && diagnostics.steps !== null
      ? diagnostics.steps
      : null;
    // G14：``current_nodes``（超限那刻还就绪的节点）是「卡在哪个环」的直接答案，
    // ``steps`` 说明跑了多少 superstep——两者都不能丢。
    const parts = [`图超限，已停止执行（reason: ${reason}`];
    if (limit !== null) parts.push(`, limit: ${limit}`);
    if (steps !== null) parts.push(`, steps: ${steps}`);
    parts.push('）');
    if (currentNodes.length) parts.push(`；超限时仍就绪的节点：${currentNodes.join('、')}`);
    return {
      level: 'error',
      reason,
      limit,
      steps,
      current_nodes: currentNodes,
      message: parts.join(''),
    };
  }

  // --- 节点失败证据（change fix-issue-215） --------------------------------
  //
  // 七个状态取值与后端 ``web/session.py`` 的 ``FAILURE_EVIDENCE_STATES`` 一一对应。
  // 放在这里（而不是 workflow_transcript.js 的 DOM 代码里）是为了让「哪一态说什么话」
  // 能被 node+vm 纯函数测试锁住——否则前端这一层只能在浏览器 smoke 里验，成本高、
  // 覆盖也薄。
  const FAILURE_EVIDENCE_TEXTS = {
    present: '本 run 的执行记录里有失败步骤（下面是最近的几条）。',
    clean: '已检查，无失败记录。',
    running: '该 run 尚未结束，执行 trace 只会在终态写入——现在没有失败证据，不代表没有失败。',
    empty_trace: '该 run 的执行 trace 存在，但未执行任何步骤。',
    no_trace: '该 run 没有采集到执行 trace。',
    unavailable: '无法解析该 run 的记录，因此拿不到失败证据。',
    not_applicable: '该节点类型不产生 run，因此没有失败证据可言。',
  };

  /** 七态文案表（node+vm 测试经它取全量；也让后端的状态集合可被机械比对）。 */
  function failureEvidenceTexts() {
    return Object.assign({}, FAILURE_EVIDENCE_TEXTS);
  }

  /** 失败证据的标题（``state`` → 一句话）。
   *
   * 未知取值**必须**给出可读降级而不是空白：后端加一个新 state 而前端还没跟上时，
   * 显示空白会让用户以为「没问题」——那正是本 change 要消灭的误读。
   */
  function failureEvidenceText(state) {
    return FAILURE_EVIDENCE_TEXTS[state]
      || '失败证据状态未知（前端版本落后于后端）。';
  }

  /** 一条失败条目的单行摘要：``工具名 · 步序 · 错误类型`` + 文本首行。
   *
   * 文本取 ``observation``（工具结果）或 ``message``（LLM 错误）——两种条目的文本
   * 字段不同名，但都经 ``text_truncated`` 表达截断，这里统一按「本条文本」处理。
   */
  function failureItemSummary(item) {
    const parts = [];
    parts.push(item && item.tool_name ? item.tool_name : '（未知工具）');
    if (item && item.step !== undefined && item.step !== null) parts.push(`step ${item.step}`);
    if (item && item.error_type) parts.push(item.error_type);
    const head = [item && item.observation, item && item.message]
      .find((value) => typeof value === 'string' && value);
    if (head) {
      // 摘要只取**开头一小段**：它是「扫一眼知道是哪条」，不是正文出口。不加这个
      // 上限的话，一条没有换行的超长 observation 会让摘要本身无界——预览的 300
      // 字符上限就被绕过了（正文出口在下面的 <pre>）。
      const firstLine = head.split('\n')[0];
      parts.push(firstLine.length > 120 ? `${firstLine.slice(0, 120)}…` : firstLine);
    }
    const line = parts.join(' · ');
    return (item && item.text_truncated) ? `${line}（文本已截断）` : line;
  }

  /** 「任务」tab 的一行快照线索（Q6 方案 D）。
   *
   * 三态：``null``/``undefined`` = 没有数据 → **什么都不显示**（返回 ``null``，
   * 调用方据此跳过）；``0`` = 已检查、无失败；``N`` = N 条失败（工具失败 + LLM 错误）。
   * ``0`` 与「没有数据」在这里必须分开——把它们折叠成同一句会让用户重新落回
   * 「没显示 = 没事」的旧误读。
   */
  function failureCountHint(count) {
    if (count === null || count === undefined) return null;
    if (count === 0) return '已检查、无失败。';
    // 措辞必须覆盖**两种**失败：计数口径是「工具失败 + LLM 错误」
    // （agent/trace_recorder.py 的 count_failures）。只写「工具失败」会在
    // run 因 LLM 调用失败而红时把用户带去查工具——兄弟出口
    // （workflow_transcript.js 的候选行）用的是准确措辞，这里跟它一致。
    if (count === 1) return '⚠ 本 run 内 1 次工具/LLM 失败 →「对话」tab 查看';
    return `⚠ 本 run 内 ${count} 次工具/LLM 失败 →「对话」tab 查看`;
  }

  window.AsterwyndWorkflowGraph = {
    NODE_COLORS,
    EDGE_STYLES,
    CHANNEL_DASH,
    GRAPH_STATUS_COLORS,
    NODE_WIDTH,
    NODE_HEIGHT,
    MIN_ZOOM,
    MAX_ZOOM,
    PARALLEL_EDGE_DELTA,
    nodeColor,
    nodeLabel,
    nodeColors,
    edgeStyle,
    edgeStatusStyles,
    channelDash,
    channelNames,
    kindGlyph,
    projectNode,
    kindGlyphs,
    // --- enhance-workflow-graph-ux 新增 ---
    graphStatusColor,
    graphStatusLabel,
    graphStatusColors,
    statusEncodings,
    statusEncoding,
    legendModel,
    explainNode,
    isSpecificNodeReason,
    graphStatusTexts,
    nodeProgress,
    progressLabel,
    rankGraphs,
    graphTabMeta,
    edgeCountLabel,
    transcriptRefreshDue,
    isTerminalNodeStatus,
    TRANSCRIPT_REFRESH_S,
    formatElapsed,
    formatAge,
    truncateText,
    // --- fix-issue-215：失败证据的纯函数层 ---
    FAILURE_EVIDENCE_TEXTS,
    failureEvidenceTexts,
    failureEvidenceText,
    failureItemSummary,
    failureCountHint,
    parallelEdgeOffset,
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
    groupStatus,
    collapseGraph,
    graphNotice,
  };
})();
