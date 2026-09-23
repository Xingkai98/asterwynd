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
  //: 上次取数时刻（节点 key → epoch 秒），刷新节律的判据。
  const fetchedAt = new Map();
  //: 「暂停实时更新」的节点集合（D4：transcript 不跟着快照重排会打断阅读）。
  const paused = new Set();
  //: 当前在跑的刷新定时器（切节点/关抽屉要停掉，否则会对已关闭的面板发请求）。
  let refreshHandle = null;
  let refreshCtx = null;

  /** 缓存键：**必须带上 subagentId**，否则候选项下钻会覆盖容器那一格缓存
   *  （审阅发现的连带问题）——下钻后再点回容器，拿到的是上一个单项的内容。 */
  function nodeKey(ctx) {
    return `${ctx.workflowId}::${ctx.nodeId}::${ctx.subagentId || ''}`;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** 拉取一个节点的 transcript（**懒加载**：切到「对话」tab 才调）。
   *
   * ``force`` 为真时绕过缓存（刷新节律到点后的重取）；否则命中缓存直接返回，
   * 所以同一个节点反复切 tab 不会重复请求。
   */
  async function fetchTranscript(ctx) {
    const key = nodeKey(ctx);
    if (!ctx.force && cache.has(key)) return cache.get(key);
    if (!ctx.sessionId) {
      return {kind: 'none', message: '该会话未在本进程加载'};
    }
    const url = `/api/sessions/${encodeURIComponent(ctx.sessionId)}`
      + `/workflows/${encodeURIComponent(ctx.workflowId)}`
      + `/nodes/${encodeURIComponent(ctx.nodeId)}/transcript`
      // 候选项下钻：指名要**哪一项**的 transcript。foreach 容器在 manager 里是
      // N 条同 (workflow_id, node_id) 的 session，不指名就只能拿到容器形态。
      + (ctx.subagentId
        ? `?subagent_id=${encodeURIComponent(ctx.subagentId)}`
          + (ctx.runId ? `&run_id=${encodeURIComponent(ctx.runId)}` : '')
        : '');
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
    fetchedAt.set(key, Date.now() / 1000);
    return payload;
  }

  /** 进入某个节点的「对话」tab 时调用（``renderDrawerConvo`` 的唯一入口）。
   *
   * ``ctx.node``（快照里的节点投影）用于判刷新节律——没有它就不排自动刷新，
   * 只取一次。
   */
  async function render(host, ctx) {
    stopAutoRefresh();
    refreshCtx = ctx;
    await paint(host, ctx, {loading: true});
    scheduleAutoRefresh(host, ctx);
  }

  async function paint(host, ctx, options) {
    const opts = options || {};
    if (opts.loading) {
      host.textContent = '';
      host.appendChild(el('div', 'drawer-empty', '加载中…'));
    }
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
    host.appendChild(toolbar(ctx, payload));
    appendBackLink(host, ctx);
    // 失败证据（change fix-issue-215）：三形态共用一个挂载点，``payload`` 缺这个键
    // （老载荷 / 降级路径）时静默跳过。放在消息体**之前**——用户先知道「这个 run
    // 里有失败」，再往下读对话。
    appendFailureEvidence(host, payload);
    if (payload.kind === 'single') renderSingle(host, ctx, payload);
    // ``ctx`` 供单项视图回显「第几项」（有的话）——见 renderSingle 的 title 行。
    else if (payload.kind === 'candidates') renderCandidates(host, ctx, payload);
    else renderNone(host, payload);
  }

  /** 对话区工具条：暂停按钮（D4）+ 取数溯源。**三种形态都有**——暂停按钮不是
   *  single 专属：候选列表同样会随刷新重排。 */
  function toolbar(ctx, payload) {
    const key = nodeKey(ctx);
    const bar = el('div', 'transcript-bar');
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
    const stamp = fetchedAt.get(key);
    if (typeof stamp === 'number') {
      bar.appendChild(el('span', 'drawer-note',
        `最后更新于 ${G.formatAge(Date.now() / 1000 - stamp)}`));
    } else if (payload.content_limit) {
      bar.appendChild(el('span', 'drawer-note',
        `单条上限 ${payload.content_limit} 字符`));
    }
    return bar;
  }

  /**
   * 按**定死的节律**重取（M3.8）：每 ``TRANSCRIPT_REFRESH_S`` 秒问一次纯函数
   * ``transcriptRefreshDue``，该不该重取由它说了算（暂停 / 已终态 / 未到点都不取）。
   *
   * 这就是 design 里那个「刷新节律定死」的落地：既不是「打开取一次、之后永不
   * 更新」（用户会以为已经处理完），也不是跟着每个快照重排（打断阅读）。
   */
  function scheduleAutoRefresh(host, ctx) {
    stopAutoRefresh();
    refreshCtx = ctx;
    refreshHandle = window.setInterval(() => {
      const current = refreshCtx;
      if (!current || !host.isConnected) {
        stopAutoRefresh();
        return;
      }
      // 下钻到某一项时判**那一项**的状态（`itemNode`），否则容器还在跑就会不断
      // 重取，把单项视图换回候选列表。
      const due = G.transcriptRefreshDue(current.itemNode || current.node, {
        paused: paused.has(nodeKey(current)),
        lastFetchedAt: fetchedAt.get(nodeKey(current)),
        now: Date.now() / 1000,
      });
      if (!due) return;
      paint(host, Object.assign({}, current, {force: true}));
    }, G.TRANSCRIPT_REFRESH_S * 1000);
  }

  function stopAutoRefresh() {
    if (refreshHandle === null) return;
    window.clearInterval(refreshHandle);
    refreshHandle = null;
    refreshCtx = null;
  }

  /** 单项视图的「返回容器」入口（下钻后没有它就回不去了）。 */
  function appendBackLink(host, ctx) {
    if (!ctx.subagentId || !ctx.parentCtx) return;
    const back = el('button', 'transcript-back', '← 返回并行项列表');
    back.type = 'button';
    back.dataset.action = 'transcript-back';
    back.addEventListener('click', () => {
      render(host, ctx.parentCtx);
    });
    host.appendChild(back);
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

  /** 失败证据区（change fix-issue-215 D6：证据主体在「对话」tab）。
   *
   * 七态各显示**自己**的一句文案——「clean 显示、其它不显示」会退化成
   * 「不显示 = 没事」，那正是本 change 要消灭的误读（OTel ``Unset`` 的教训）。
   * 条目按「工具名 · 步序 · 错误类型 + 文本首行」逐条列出，文本用既有 note 模式
   * 标注截断——预览短上限不等于正文就这么短（issue #213 的同一类坑）。
   */
  function appendFailureEvidence(host, payload) {
    const evidence = payload && payload.failure_evidence;
    if (!evidence || !evidence.state) return;
    const isPresent = evidence.state === 'present';
    if (evidence.state === 'not_applicable' && !isPresent) {
      // 结构上不产生的节点（route/collect）说这句话是噪音——它们的详情自有一句
      // 「不产生对话」。其余**所有**取值都必须显示，否则又回到「不显示 = 没事」。
      host.appendChild(el('div', 'drawer-note', G.failureEvidenceText(evidence.state)));
      return;
    }
    host.appendChild(el('h3', null, '失败证据'));
    host.appendChild(el('div', 'drawer-text', G.failureEvidenceText(evidence.state)));
    (evidence.items || []).forEach((item) => {
      const row = el('div', 'failure-item');
      row.appendChild(el('div', 'failure-summary', G.failureItemSummary(item)));
      const text = item.observation || item.message;
      if (text) {
        row.appendChild(el('pre', 'failure-text', G.truncateText(text, 300)));
        if (item.text_truncated || text.length > 300) {
          row.appendChild(el('span', 'drawer-note', '预览已截断，全文见本条记录。'));
        }
      }
      host.appendChild(row);
    });
    if (evidence.truncated) {
      host.appendChild(el('p', 'drawer-note',
        `共 ${evidence.total} 条，只显示了最近 ${(evidence.items || []).length} 条。`));
    }
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
      row.dataset.subagentId = candidate.subagent_id || '';
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
      // 失败线索（change fix-issue-215 Q5）：容器一次渲染 N 项，所以候选行只给
      // **计数**，不给证据正文（正文在下钻后的「对话」视图里，避免响应放大）。
      const evidence = candidate.failure_evidence;
      if (evidence && evidence.total > 0) {
        name.appendChild(el('div', 'cand-sub cand-failure',
          `⚠ ${evidence.total} 条工具/LLM 失败（点进去看）`));
      }
      row.appendChild(name);
      const status = el('span', 'cand-status', G.nodeLabel(candidate.status));
      status.style.color = G.nodeColor(candidate.status);
      row.appendChild(status);
      row.addEventListener('click', () => {
        // 点某一项 → 按该项自己的 ``subagent_id`` 取它的 transcript
        // （**不混入**同容器其它项的 messages）。``node`` 换成该项的投影：刷新
        // 节律要判「**这一项**还在不在跑」，拿容器的状态会判错，10s 后把单项
        // 视图换回候选列表。
        render(host, Object.assign({}, ctx, {
          subagentId: candidate.subagent_id,
          runId: candidate.run_id,
          index: candidate.index,
          itemNode: {id: String(candidate.index), status: candidate.status},
          // 留一份容器 ctx 供「返回」用。
          parentCtx: ctx.subagentId ? ctx.parentCtx : ctx,
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
    // 单项下钻时标明「这是第几项」——否则用户分不清自己在看容器还是某一项
    // （两者的消息长得一样，只有身份不同）。
    if (typeof ctx.index === 'number') {
      host.appendChild(el('div', 'transcript-item-note',
        `第 ${ctx.index} 项` + (payload.task ? `：${G.truncateText(payload.task, 120)}` : '')));
    }
    const body = el('div', 'transcript-body');
    host.appendChild(body);
    renderClusters(body, payload.messages || []);
    if (payload.truncated) {
      // ``truncated`` 的语义是 ``len(messages) > limit``（已剔除 tool 角色后）
      // ——文案不能写成「内容被截断」。
      host.appendChild(el('p', 'drawer-note', '只显示了最近的消息（更早的未加载）。'));
    }
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
      const calls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
      const parts = content.split('\n');
      const emitted = [];
      parts.forEach((line, index) => {
        emitted.push(index === 0
          ? {role, text: line, calls}
          : {role: null, text: line});
      });
      // 模型只发起工具调用、不输出文字的轮次（AgentLoop 的大多数轮次）content
      // 是空字符串——上面会产出一行**空文本**，那正是用户看到的一串空 ASSISTANT。
      // 有调用时不再渲染那行空文本，改由工具调用块承担这一轮的内容。
      if (calls.length && parts.length === 1 && !parts[0]) {
        emitted[0] = {role, text: null, calls};
      }
      // 单条内容被截断（issue #213）：截断处是**裸切**，读起来是通顺的，用户看不出
      // 内容断了——必须在末尾如实标注，否则「正文看着完整、其实是残的」。
      if (message.content_truncated && emitted.length) {
        emitted[emitted.length - 1].note = '（内容已截断）';
      }
      lines.push(...emitted);
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

  /** 一条工具调用：``🔧 名字`` + 参数（与主 chat 的 ``addToolCallBlock`` 同口径）。

  一个 assistant 轮次可以并发发起多个调用，逐个列出才看得出那一轮到底干了什么
  ——那是「这个节点为什么慢/为什么错」最直接的证据。
  */
  function toolCallBlock(call) {
    const block = el('div', 'tool-call-block');
    block.appendChild(el('span', 'tool-name', `🔧 ${call.name || ''}`));
    const args = String(call.arguments || '');
    if (args) {
      block.appendChild(el('pre', null, prettyArgs(args)));
    }
    if (call.arguments_truncated) {
      block.appendChild(el('span', 'drawer-note', '（参数已截断）'));
    }
    return block;
  }

  /** ``arguments`` 是 JSON 字符串；解析失败就原样显示（工具调用可能被流式截断）。 */
  function prettyArgs(args) {
    try {
      const parsed = JSON.parse(args);
      return JSON.stringify(parsed, null, 2);
    } catch (error) {
      return args;
    }
  }

  function paintCluster(host, cluster) {
    if (host.dataset.painted) return;
    host.dataset.painted = '1';
    host.style.minHeight = '';
    host.textContent = '';
    cluster.forEach((line) => {
      if (line.role) host.appendChild(el('div', 'msg-role', line.role));
      // ``text === null``：该轮只有工具调用，不渲染空文本行。
      if (line.text !== null) host.appendChild(el('div', 'msg-text', line.text));
      (line.calls || []).forEach((call) => host.appendChild(toolCallBlock(call)));
      if (line.note) host.appendChild(el('span', 'drawer-note', line.note));
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
    stopAutoRefresh,
    CLUSTER_SIZE,
    cache,
    paused,
    fetchedAt,
  };
})();
