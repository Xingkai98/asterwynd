// web/static/workflow_transcript.js
// 节点详情抽屉的「对话」tab（change enhance-workflow-graph-ux，D4/D5/M3）。
//
// 三态 union 的渲染（single / candidates / none）——形态由**节点类型**决定，
// 不是特例兜底：
//
//   single     subagent / aggregate(llm) / 自动插层 → 单条 transcript
//   candidates foreach 容器 → N 个并行项清单，点某项再取该项的 transcript
//   none       route / aggregate(collect) / 未派发 → 该类型的自有信息
//
// 性能口径（对标 GitHub Actions 大日志工程）：**只做 UI 虚拟化，不做数据虚拟化**
// ——数据是接口一次取回的、本来就在内存，按 **50 行一组聚簇**、按簇增删 DOM，
// 而不是按行。现成可视化库在这个尺度上要么不支持可变行高、要么虚拟化破坏
// 文本选择，所以零依赖自研。
(function () {
  'use strict';

  const G = window.AsterwyndWorkflowGraph;
  if (!G) return;

  //: 一簇多少行（GitHub Actions 的实测结论：50 行是「一次 DOM 操作」与
  //: 「一次重排代价」之间的平衡点）。
  const CLUSTER_SIZE = 50;
  //: 折叠态一屏显示的簇数。其余簇只保留**占位高度**，滚动到附近才建 DOM。
  const VISIBLE_CLUSTERS = 3;

  //: 每个节点缓存一份结果：同一个节点反复切换 tab 不重复请求。
  const cache = new Map();
  //: 「暂停实时更新」的节点集合（D4：transcript 不跟着快照重排会打断阅读）。
  const paused = new Set();

  function nodeKey(ctx) {
    return `${ctx.workflowId}::${ctx.nodeId}`;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** 拉取一个节点的 transcript（**懒加载**：切到「对话」tab 才调）。 */
  async function fetchTranscript(ctx) {
    const key = nodeKey(ctx);
    if (cache.has(key)) return cache.get(key);
    if (!ctx.sessionId) {
      return {kind: 'none', message: '该会话未在本进程加载'};
    }
    const url = `/api/sessions/${encodeURIComponent(ctx.sessionId)}`
      + `/workflows/${encodeURIComponent(ctx.workflowId)}`
      + `/nodes/${encodeURIComponent(ctx.nodeId)}/transcript`;
    const response = await fetch(url, {headers: {Accept: 'application/json'}});
    if (response.status === 404) {
      // 内存口径的 session 校验：冷会话/进程重启后一律 404——降级为一句
      // 可读的话，而不是把 404 当异常抛到控制台。
      return {kind: 'none', message: '该会话未在本进程加载'};
    }
    if (!response.ok) {
      return {kind: 'none', message: `对话加载失败（HTTP ${response.status}）`};
    }
    const payload = await response.json();
    cache.set(key, payload);
    return payload;
  }

  /** 进入某个节点的「对话」tab 时调用（``renderDrawerConvo`` 的唯一入口）。 */
  async function render(host, ctx) {
    host.textContent = '';
    host.appendChild(el('div', 'drawer-empty', '加载中…'));
    let payload;
    try {
      payload = await fetchTranscript(ctx);
    } catch (error) {
      host.textContent = '';
      host.appendChild(el('div', 'drawer-empty', `对话加载失败：${error}`));
      return;
    }
    // 请求飞行期间用户可能已切走：只有内容还挂在 DOM 上时才覆盖。
    if (!host.isConnected) return;
    host.textContent = '';
    if (payload.kind === 'single') renderSingle(host, ctx, payload);
    else if (payload.kind === 'candidates') renderCandidates(host, ctx, payload);
    else renderNone(host, payload);
  }

  function renderNone(host, payload) {
    if (payload.verdict !== undefined && payload.node_kind === 'route') {
      // route 节点改为展示**命中标签 + 选中出口**（不是一句「无对话」了事）。
      const list = el('div', 'kv');
      list.appendChild(el('span', 'kv-key', '判定结果'));
      list.appendChild(el('span', null, payload.verdict || '（走 default）'));
      list.appendChild(el('span', 'kv-key', '命中出口'));
      list.appendChild(el('span', null,
        (payload.targets || []).length ? `→ ${payload.targets.join('、')}` : '—'));
      if (payload.raw) {
        list.appendChild(el('span', 'kv-key', '上游原文'));
        list.appendChild(el('span', null, G.truncateText(payload.raw, 400)));
      }
      host.appendChild(list);
      appendReason(host, payload);
      return;
    }
    host.appendChild(el('div', 'drawer-empty',
      payload.message || '该节点未执行，无对话。'));
    if (payload.summary) {
      host.appendChild(el('h3', null, '合并产出'));
      host.appendChild(el('div', 'drawer-text', payload.summary));
    }
    appendReason(host, payload);
  }

  /** G17：reason 的**全文**出口——scheduler 侧 reason 从不出现在 transcript 里，
   *  快照里又被截断到 400，所以这里是用户唯一能读到全文的地方。 */
  function appendReason(host, payload) {
    if (!payload.reason_full) return;
    host.appendChild(el('h3', null, '因由'));
    host.appendChild(el('div', 'drawer-text', payload.reason_full));
  }

  function renderCandidates(host, ctx, payload) {
    host.appendChild(el('div', 'drawer-empty',
      `该节点为 ${payload.total} 个并行项的容器，无单一对话。`));
    payload.candidates.forEach((candidate) => {
      const row = el('button', 'cand');
      row.type = 'button';
      row.dataset.index = String(candidate.index);
      row.appendChild(el('span', 'cand-idx', `#${candidate.index}`));
      const name = el('span', 'cand-name',
        candidate.task ? G.truncateText(candidate.task, 80) : candidate.label);
      if (candidate.reason) {
        // G10：失败项 summary 通常是空的——没有 reason 就是「3 个红点、
        // 点开每行空白」。
        name.appendChild(el('div', 'cand-sub', G.truncateText(candidate.reason, 80)));
      } else if (candidate.summary) {
        name.appendChild(el('div', 'cand-sub', G.truncateText(candidate.summary, 80)));
      }
      row.appendChild(name);
      const status = el('span', 'cand-status', G.nodeLabel(candidate.status));
      status.style.color = G.nodeColor(candidate.status);
      row.appendChild(status);
      row.addEventListener('click', () => {
        // 点某一项 → 按该项自己的 ``subagent_id`` 取它的 transcript
        // （**不混入**同容器其它项的 messages）。
        render(host, Object.assign({}, ctx, {
          nodeId: ctx.nodeId,
          subagentId: candidate.subagent_id,
          index: candidate.index,
        }));
      });
      host.appendChild(row);
    });
    if (payload.has_more) {
      host.appendChild(el('p', 'drawer-note',
        `仅显示前 ${payload.candidates.length} 项（共 ${payload.total} 项）。`));
    }
  }

  function renderSingle(host, ctx, payload) {
    host.appendChild(transcriptToolbar(ctx, payload));
    const body = el('div', 'transcript-body');
    host.appendChild(body);
    renderClusters(body, payload.messages || []);
    if (payload.truncated) {
      // ``truncated`` 的语义是 ``len(messages) > limit``（已剔除 tool 角色后）
      // ——文案不能写成「内容被截断」。
      host.appendChild(el('p', 'drawer-note', '只显示了最近的消息（更早的未加载）。'));
    }
  }

  /** D4 的暂停按钮：transcript 不跟着快照重排（会打断阅读）。 */
  function transcriptToolbar(ctx, payload) {
    const bar = el('div', 'transcript-bar');
    const key = nodeKey(ctx);
    const button = el('button', 'transcript-pause',
      paused.has(key) ? '继续实时更新' : '暂停实时更新');
    button.type = 'button';
    button.dataset.action = 'pause-transcript';
    button.addEventListener('click', () => {
      if (paused.has(key)) paused.delete(key);
      else paused.add(key);
      button.textContent = paused.has(key) ? '继续实时更新' : '暂停实时更新';
    });
    bar.appendChild(button);
    if (payload.content_limit) {
      bar.appendChild(el('span', 'drawer-note',
        `单条上限 ${payload.content_limit} 字符`));
    }
    return bar;
  }

  /**
   * 按 **50 行一簇**渲染（UI 虚拟化：按簇增删 DOM，不按行）。
   *
   * 一簇 = 若干条消息拼出来的行块。只有前 ``VISIBLE_CLUSTERS`` 簇立即建 DOM，
   * 其余簇先占位（保留高度，滚动到时再建），这样长 transcript 的首次渲染
   * 不会因为几千个 DOM 节点卡住主线程。
   */
  function renderClusters(body, messages) {
    const lines = [];
    messages.forEach((message) => {
      const role = String(message.role || '');
      const content = String(message.content || '');
      const parts = content.split('\n');
      const head = parts.length > 1 ? parts : [content];
      head.forEach((line, index) => {
        lines.push(index === 0 ? {role, text: line} : {role: null, text: line});
      });
    });
    if (!lines.length) {
      body.appendChild(el('div', 'drawer-empty', '（没有可显示的消息）'));
      return;
    }
    const clusters = [];
    for (let i = 0; i < lines.length; i += CLUSTER_SIZE) {
      clusters.push(lines.slice(i, i + CLUSTER_SIZE));
    }
    clusterLines.set(body, clusters);
    clusters.forEach((cluster, index) => {
      const placeholder = el('div', 'transcript-cluster');
      placeholder.dataset.cluster = String(index);
      if (index < VISIBLE_CLUSTERS) {
        paintCluster(placeholder, cluster);
      } else {
        // 占位高度：按簇内行数估一个高度，避免滚动条在加载时跳动。
        placeholder.style.minHeight = `${cluster.length * 20}px`;
      }
      body.appendChild(placeholder);
    });
    observeClusters(body, clusters);
  }

  function paintCluster(host, cluster) {
    if (host.dataset.painted) return;
    host.dataset.painted = '1';
    host.style.minHeight = '';
    host.textContent = '';
    cluster.forEach((line) => {
      if (line.role) host.appendChild(el('div', 'msg-role', line.role));
      host.appendChild(el('div', 'msg-text', line.text));
    });
  }

  //: 渲染体 → 原始行簇（占位簇没有 DOM，必须能从原始行数组取回来）。
  const clusterLines = new WeakMap();

  /** 滚到附近才把占位簇变成真 DOM（``IntersectionObserver`` 不可用时退化为
   *  一次全渲染——功能优先，性能是增强）。 */
  function observeClusters(body, clusters) {
    if (typeof IntersectionObserver === 'undefined') {
      body.querySelectorAll('.transcript-cluster').forEach((host) => {
        paintCluster(host, clusters[Number(host.dataset.cluster)] || []);
      });
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const index = Number(entry.target.dataset.cluster);
        paintCluster(entry.target, clusters[index] || []);
        observer.unobserve(entry.target);
      });
    }, {rootMargin: '200px'});
    body.querySelectorAll('.transcript-cluster').forEach(
      (cluster) => observer.observe(cluster));
  }

  window.AsterwyndWorkflowTranscript = {
    render,
    fetchTranscript,
    CLUSTER_SIZE,
    cache,
    paused,
  };
})();
