/**
 * AsterwyndToolRows —— 对话区与工作流抽屉共用的工具执行行渲染层。
 *
 * 设计口径（change ``harness-style-web-transcript`` D2/D3/D4/D8，含 grill 订正）：
 *
 * - **纯函数层**（``firstLine`` / ``truncate`` / ``compactJson`` / ``toolTitle`` /
 *   ``summarizeToolCall`` / ``summarizeToolResult`` / ``formatCharMeta`` /
 *   ``formatBodyText``）不碰 DOM，由 node + ``vm`` 直接单测
 *   （``tests/web_tests/test_transcript_js.py``）。摘要生成是字符串语义，源码字符串
 *   断言测不到、Playwright 断言只能看到最终渲染，所以单独抽一层锁死。
 * - **DOM 层**（``createToolRow`` / ``updateToolRow``）只接受调用方注入的 ``document``，
 *   模块加载时不读全局 DOM（否则 node harness 起不来）。
 * - 折叠态**只渲染一行**：``[caret] [title] · [summary] [meta]``；参数与结果全文只在
 *   展开时才可见。这是「不被工具输出刷屏」的根本机制——不是把 5000 字符换成
 *   1200 字符预览（旧实现 ``chat.js`` 的做法）。
 * - 展开体是头部按钮的**兄弟节点**（不是子节点）：点展开体里的文本不会误触折叠。
 * - 失败**不自动展开**；失败信号落在折叠行上（错误色 + 行尾 meta），但**结构化结果
 *   （Bash/TaskOutput 的单行 JSON）保留参数摘要**——命令才是第一定位符，把
 *   ``{"exit_code": 1, "stdout": …`` 顶到行上等于把命令删掉（grill Q2/R-B）。
 * - 文件名刻意不含 "transcript" 字样：既有浏览器测试用通配 glob 拦截后端 transcript
 *   接口，名字里带该片段的静态资源会被那个 glob 一起命中并被喂成 JSON
 *   （实测把工作流抽屉的整条渲染打断）。
 *
 * 命名空间风格与 ``AsterwyndMarkdown`` / ``AsterwyndWorkflow`` 一致。
 */
(function () {
  'use strict';

  /** 折叠行摘要的字符预算。行宽有限，超出交给 CSS 的 ellipsis 兜底。 */
  var SUMMARY_LIMIT = 80;
  /** 失败首行的字符预算（比摘要宽：错误文案的区分度全在前半段）。 */
  var ERROR_LIMIT = 120;
  /** 展开正文（参数与结果）的硬上限，防止单次超大载荷把 DOM 撑爆。 */
  var BODY_LIMIT = 200000;
  var BODY_TRUNCATED_NOTE = '（正文超出展示上限，已截断）';
  /** 行内唯一 id 的递增序号，用于 `aria-controls` 关联头按钮与兄弟展开体。 */
  var rowSeq = 0;

  // 工具名 → 折叠行标题。与参考实现的 `tool.title.*` 同口径：短动词、镜像线名。
  // 未列出的工具回落到线名本身（MCP / 插件工具）。
  var TOOL_TITLES = {
    Read: 'Read',
    ReadDoc: 'Read',
    ListFiles: 'List',
    Find: 'Find',
    Grep: 'Grep',
    SymbolSearch: 'Symbols',
    RepoMap: 'Repo map',
    Bash: 'Bash',
    Write: 'Write',
    Edit: 'Edit',
    WebFetch: 'Fetch',
    WebSearch: 'Search',
    TodoWrite: 'Todo',
    UpdatePlan: 'Plan',
    ExitPlanMode: 'Plan',
    AskUserQuestion: 'Ask',
    ActivateSkill: 'Skill',
    TaskOutput: 'Task',
    TaskStop: 'Task',
    BrowserNavigate: 'Browse',
    BrowserGetContent: 'Browse',
    BrowserScreenshot: 'Browse',
    BrowserScroll: 'Browse',
    BrowserListTabs: 'Browse',
    BrowserSwitchTab: 'Browse',
    BrowserCloseTab: 'Browse',
    InspectGitDiff: 'Diff',
    LspDiagnostics: 'Diagnostics',
    LspDefinition: 'Definition',
    LspReferences: 'References',
    LspHover: 'Hover',
    LspDocumentSymbols: 'Symbols',
    LspWorkspaceSymbols: 'Symbols',
    SaveMemory: 'Memory',
    RecallMemory: 'Memory',
    SearchMemory: 'Memory',
    ResolveMemoryConflict: 'Memory',
    CreateSubagent: 'Subagent',
    RunSubagent: 'Subagent',
    ResumeSubagent: 'Subagent',
    CancelSubagentRun: 'Subagent',
    GetSubagentRun: 'Subagent',
    ListSubagents: 'Subagent',
    InspectSubagentTranscript: 'Subagent',
    RunWorkflow: 'Workflow',
    StartWorkflow: 'Workflow',
    DeclareWorkflow: 'Workflow',
    GetWorkflow: 'Workflow',
    CancelWorkflow: 'Workflow',
    DryRunWorkflow: 'Workflow',
    ReadWorkflowResult: 'Workflow',
    GetWorkflowAsset: 'Workflow',
    SaveWorkflowAsset: 'Workflow',
    RunWorkflowAsset: 'Workflow',
    ListWorkflowAssets: 'Workflow',
    PublishBusMessage: 'Bus',
    ReadBus: 'Bus',
    EnterWorktree: 'Worktree',
    ExitWorktree: 'Worktree',
  };

  // 每个工具「最能定位这次调用」的参数字段，按顺序取第一个非空字符串。
  // 通用回落是「参数对象里第一个非空字符串值」，再不行才是压缩后的 JSON。
  var SUMMARY_KEYS = {
    Read: ['path', 'file_path', 'url'],
    ReadDoc: ['path', 'file_path'],
    Write: ['path', 'file_path'],
    Edit: ['path', 'file_path'],
    ListFiles: ['path', 'directory', 'pattern'],
    Find: ['query', 'pattern', 'path'],
    Grep: ['pattern', 'query'],
    SymbolSearch: ['query', 'pattern'],
    RepoMap: ['path'],
    Bash: ['cmd', 'command', 'description'],
    WebFetch: ['url', 'uri'],
    WebSearch: ['query', 'queries'],
    AskUserQuestion: ['question', 'title', 'prompt'],
    ActivateSkill: ['name', 'skill'],
    TaskOutput: ['task_id', 'id'],
    TaskStop: ['task_id', 'id'],
  };

  // 失败特征。**一律锚定行首**：结果文本可能包含任意内容（例如 Grep 命中的源码行），
  // 未锚定的模式会把「成功的搜索」标成失败。前缀集对齐后端自己的 canonical 错误通道
  // （`agent/loop.py::_text_prefix_guess`：`[Error` / `Error` / `[Permission denied`
  // / `[MCP tool error`，加上 `[Approval denied` / `[Approval unavailable` /
  // `[Approval required`）——不对齐就会让「审批被拒」「权限拒绝」这些最常见的失败在
  // 折叠行上显示为成功（grill R-A）。
  var FAILURE_PATTERNS = [
    /^\[exit\s+(\d+)\]/i,
    /^\[timeout\b/i,
    /^\[oom\b/i,
    /^\[error\b/i,
    /^\[permission\s+denied\b/i,
    /^\[approval\s+denied\b/i,
    /^\[approval\s+unavailable\b/i,
    /^\[approval\s+required\b/i,
    /^\[mcp\s+tool\s+error\b/i,
    // 浏览器族（`agent/tools/builtin/browser_*.py`、`agent/browser/session.py`）走的是
    // 方括号自有文案；后端 `_text_prefix_guess` 也没覆盖它们——漏掉会让「浏览器能力
    // 不可用 / URL 被拒」显示成成功。
    /^\[browser\s+error\b/i,
    /^\[browser\s+not\s+available\b/i,
    /^\[url\s+denied\b/i,
    /^traceback\b/i,
    /^exit\s+code\s*[:=]?\s*(\d+)/i,
    /^exit\s+status\s*[:=]?\s*(\d+)/i,
    /^command\s+failed\b/i,
  ];
  // 裸文本前缀单独处理：`Error: …` 与「工具返回文件/命令内容」无法从首行区分——读一个
  // 首行正好写着 `Error:` 的文件不是失败。规则：裸前缀只在**结果整体就是一行**时判失败
  // （后端的工具失败文案是单行消息，而文件内容/命令输出通常是多行）。方括号前缀与
  // `Traceback` 是无歧义标记，不受此限。
  var BARE_FAILURE_PATTERN = /^error\b/i;
  var ZERO_CODE_PATTERNS = [
    /^\[exit\s+0\]/i,
    /^exit\s+code\s*[:=]?\s*0\b/i,
    /^exit\s+status\s*[:=]?\s*0\b/i,
  ];

  // 后台任务结果的形态（`agent/loop.py::_format_task_output`）：**多行**、不是 JSON 信封——
  //   [Task <id>]
  //   status: failed
  //   exit_code: 1
  //   stdout: …
  // `status ∈ running|completed|failed|timeout|killed|orphaned`（`agent/background.py`）。
  // 首行 `[Task …]` 是**门**（锚定它才不会把「某文件第 3 行写着 status: failed」误判），
  // 之后在有限行内找 status / exit_code。`\s` 或 `]` 紧跟才是任务头（`[Task-ish]` 不算）。
  var TASK_HEADER_RE = /^\[task(?:\s[^\]]*)?\]/i;
  var TASK_STATUS_RE = /^status:\s*([a-z_]+)\s*$/i;
  var TASK_EXIT_RE = /^exit_code:\s*(-?\d+)\s*$/i;
  var TASK_STDOUT_RE = /^stdout:/i;
  var TASK_FAILURE_STATUSES = { failed: 1, timeout: 1, orphaned: 1, killed: 1, error: 1 };
  var TASK_SCAN_LINES = 40;

  /** 取首个非空行（摘要只吃一行，多行结果的第一行才是有信息量的定位符）。 */
  function firstLine(text) {
    if (text === null || text === undefined) return '';
    var value = String(text);
    var index = value.indexOf('\n');
    return (index === -1 ? value : value.slice(0, index)).trim();
  }

  /**
   * 取首个**非空**行。失败判定与结构化解析用它而不是 ``firstLine``：结果可能以一个空行
   * 开头（工具输出常见），此时 ``firstLine`` 拿到空串会漏判失败。
   */
  function firstContentLine(text) {
    if (text === null || text === undefined) return '';
    var lines = String(text).split('\n');
    for (var i = 0; i < lines.length; i += 1) {
      var line = lines[i].trim();
      if (line !== '') return line;
    }
    return '';
  }

  /** 折叠摘要的规范化：空白折叠成单空格 + 超长截断。 */
  function truncate(text, limit) {
    if (text === null || text === undefined) return '';
    var value = String(text).replace(/\s+/g, ' ').trim();
    var max = typeof limit === 'number' && limit > 0 ? limit : SUMMARY_LIMIT;
    if (value.length <= max) return value;
    return value.slice(0, Math.max(1, max - 1)) + '…';
  }

  /** 参数对象压缩成一行文本；任何类型意外都降级成字符串而不是抛异常。 */
  function compactJson(value, limit) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return truncate(value, limit);
    try {
      var encoded = JSON.stringify(value);
      if (encoded === undefined) return truncate(String(value), limit);
      return truncate(encoded, limit);
    } catch (error) {
      return truncate(String(value), limit);
    }
  }

  /** 折叠行标题：已知工具用短动词，未知工具回落线名本身。 */
  function toolTitle(name) {
    var key = name === null || name === undefined ? '' : String(name);
    if (TOOL_TITLES[key]) return TOOL_TITLES[key];
    if (key === '') return '工具';
    return key;
  }

  function parseArguments(args) {
    if (args === null || args === undefined) return null;
    if (typeof args === 'string') {
      var text = args.trim();
      if (text === '') return null;
      try {
        return JSON.parse(text);
      } catch (error) {
        return text;
      }
    }
    return args;
  }

  function pickString(source, keys) {
    if (!source || typeof source !== 'object') return '';
    for (var i = 0; i < keys.length; i += 1) {
      var value = source[keys[i]];
      if (typeof value === 'string' && value.trim() !== '') return value;
    }
    return '';
  }

  function firstStringValue(source) {
    if (!source || typeof source !== 'object') return '';
    var keys = Object.keys(source);
    for (var i = 0; i < keys.length; i += 1) {
      var value = source[keys[i]];
      if (typeof value === 'string' && value.trim() !== '') return value;
    }
    return '';
  }

  /**
   * 待办清单的行摘要：``create`` 显示任务内容，``update`` 显示 ``#id → status``，
   * 其余显示操作名。这个工具的参数字段对「这次调用干了什么」的表达力最强，
   * 通用回落会产出难以阅读的 JSON。
   */
  function summarizeTodo(args) {
    if (!args || typeof args !== 'object') return '';
    var operation = typeof args.operation === 'string' ? args.operation : '';
    if (operation === 'create') return firstLine(args.content || '');
    if (operation === 'update') {
      var parts = [];
      if (args.id !== undefined && args.id !== null && args.id !== '') parts.push('#' + String(args.id));
      if (typeof args.status === 'string' && args.status !== '') parts.push(args.status);
      var note = firstLine(args.note || '');
      if (note) parts.push(note);
      return parts.join(' → ');
    }
    return operation;
  }

  /**
   * 折叠行摘要：按工具族挑「最能定位这次调用」的字段，全都取不到才回落到压缩 JSON。
   * 任何情况下都返回字符串（事件字段可能缺失、可能是解析失败的原始文本）。
   */
  function summarizeToolCall(name, args) {
    var key = name === null || name === undefined ? '' : String(name);
    var parsed = parseArguments(args);
    if (parsed === null) return '';
    if (key === 'TodoWrite') {
      var todo = summarizeTodo(parsed);
      if (todo) return truncate(todo, SUMMARY_LIMIT);
    }
    if (typeof parsed === 'string') return truncate(firstLine(parsed), SUMMARY_LIMIT);
    if (typeof parsed !== 'object') return truncate(String(parsed), SUMMARY_LIMIT);

    var keys = SUMMARY_KEYS[key] || [];
    if (key === 'Grep' || key === 'Find' || key === 'SymbolSearch') {
      // 搜索类光有 pattern 定位不到「搜哪儿」，路径一起给。
      var pattern = pickString(parsed, ['pattern', 'query']);
      var scope = pickString(parsed, ['path', 'directory']);
      if (pattern && scope) return truncate(pattern + ' · ' + scope, SUMMARY_LIMIT);
    }
    var picked = pickString(parsed, keys);
    if (picked) return truncate(firstLine(picked), SUMMARY_LIMIT);

    var fallback = firstStringValue(parsed);
    if (fallback) return truncate(firstLine(fallback), SUMMARY_LIMIT);

    return compactJson(parsed, SUMMARY_LIMIT);
  }

  /**
   * 结构化结果识别：``Bash`` / ``TaskOutput`` 等的 ``result`` 是单行 JSON 信封
   * （``SandboxResult.to_json()``），失败信息在 ``exit_code`` / ``timed_out`` 字段里，
   * 不是行首前缀。识别出来才能既判失败、又保留参数摘要。
   *
   * @returns {?{code: string}} ``null`` = 不是结构化失败。
   */
  function structuredFailure(line) {
    if (line.charAt(0) !== '{') return null;
    var parsed;
    try {
      parsed = JSON.parse(line);
    } catch (error) {
      return null;
    }
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.exit_code === 'number' && parsed.exit_code !== 0) {
      return { code: 'exit ' + parsed.exit_code };
    }
    if (parsed.timed_out === true) return { code: 'timeout' };
    if (parsed.oom_killed === true) return { code: 'oom' };
    if (typeof parsed.status === 'string' && /^(failed|error|cancelled|killed)$/i.test(parsed.status)) {
      return { code: parsed.status.toLowerCase() };
    }
    return null;
  }

  /**
   * 后台任务结果（`TaskOutput`）的失败识别。**不是** JSON 信封，是多行 `key: value`。
   *
   * @returns {?{code: string}} ``null`` = 不是失败的 task 结果。
   */
  function taskFailure(text) {
    var source = text === null || text === undefined ? '' : String(text);
    if (!TASK_HEADER_RE.test(firstLine(source))) return null;
    var lines = source.split('\n');
    var limit = Math.min(lines.length, TASK_SCAN_LINES);
    var status = '';
    var exitCode = null;
    for (var i = 1; i < limit; i += 1) {
      var line = lines[i].trim();
      // `stdout:` 之后是**命令输出正文**，不是元数据——`_format_task_output` 把 stdout
      // 直接拼在同一行之后，其内容可以再带换行。必须在此收尾，否则一条「成功但恰好
      // 打印了 `status: failed`」的后台命令会被标成失败行。
      if (TASK_STDOUT_RE.test(line)) break;
      var match = TASK_STATUS_RE.exec(line);
      if (match) {
        status = match[1].toLowerCase();
        continue;
      }
      match = TASK_EXIT_RE.exec(line);
      if (match) exitCode = parseInt(match[1], 10);
    }
    if (status && TASK_FAILURE_STATUSES[status]) return { code: status };
    // `completed` + 非零退出码同样是失败（退出码是结果数据，不是异常）。
    if (exitCode !== null && exitCode !== 0) return { code: 'exit ' + exitCode };
    return null;
  }

  /**
   * 结果态判定。返回 ``{state, summary, code, structured}``：
   *
   * - ``state``：``ok`` / ``error``；
   * - ``summary``：失败且结果**可读**（非 JSON 信封）时的失败首行；结构化失败为空
   *   （调用方保留参数摘要，把 ``code`` 放行尾 meta）；
   * - ``code``：``exit 1`` / ``timeout`` 这类短因由；
   * - ``structured``：结果是否为**结构化信封**（`Bash` 的单行 JSON，或 `TaskOutput` 的
   *   多行 ``[Task <id>]`` + ``status:/exit_code:``）——这类结果的失败因由是字段而非
   *   可读首行，调用方应保留参数摘要、把 ``code`` 放行尾。
   *
   * ``Bash`` 把非零退出码当**结果数据**返回而不是异常，所以不能只看有没有抛错——
   * 必须从文本/JSON 里认出失败，否则「命令失败了」只有展开才看得见。
   *
   * @param {string} name 保留参数位（签名与 ``summarizeToolCall`` 对称、便于将来按工具
   *   分叉判定）；**当前实现不按工具分叉**，失败判定对全部工具一致。
   * @param {*} result 结果全文（``tool_result.result``）。
   */
  function summarizeToolResult(name, result) {
    var text = result === null || result === undefined ? '' : String(result);
    if (text.trim() === '') return { state: 'ok', summary: '', code: '', structured: false };
    var line = firstContentLine(text);
    if (line === '') return { state: 'ok', summary: '', code: '', structured: false };

    // 等待后台任务的**包装前缀**：`_wait_task_output` 超时返回
    // `"[Task <id> timeout] [Task <id>]\nstatus: running\n…"`——任务可能仍在跑，但这次
    // 调用确实没拿到结果，折叠行要如实标出来。
    if (/^\[task\s+[^\]]*\btimeout\b\]/i.test(line)) {
      return { state: 'error', summary: '', code: 'timeout', structured: true };
    }

    var structured = structuredFailure(line);
    if (structured) {
      return { state: 'error', summary: '', code: structured.code, structured: true };
    }
    var task = taskFailure(text);
    if (task) {
      return { state: 'error', summary: '', code: task.code, structured: true };
    }

    var zero = false;
    for (var z = 0; z < ZERO_CODE_PATTERNS.length; z += 1) {
      if (ZERO_CODE_PATTERNS[z].test(line)) zero = true;
    }
    if (zero) return { state: 'ok', summary: '', code: '', structured: false };

    for (var i = 0; i < FAILURE_PATTERNS.length; i += 1) {
      var match = FAILURE_PATTERNS[i].exec(line);
      if (!match) continue;
      // 带捕获组的退出码形态：只有非 0 才算失败。
      if (match.length > 1 && match[1] !== undefined && String(match[1]) === '0') continue;
      var code = match.length > 1 && match[1] !== undefined ? 'exit ' + String(match[1]) : '';
      return { state: 'error', summary: truncate(line, ERROR_LIMIT), code: code, structured: false };
    }
    // 裸 `Error: …` 前缀：只在结果整体就是一行时判失败（见 BARE_FAILURE_PATTERN 的说明）。
    if (BARE_FAILURE_PATTERN.test(line) && text.trim().indexOf('\n') === -1) {
      return { state: 'error', summary: truncate(line, ERROR_LIMIT), code: '', structured: false };
    }
    return { state: 'ok', summary: '', code: '', structured: false };
  }

  /** 行尾元数据：``1.5k 字符 · 30 行``。行数为 1 时不占篇幅。 */
  function formatCharMeta(charCount, lineCount) {
    var chars = typeof charCount === 'number' && isFinite(charCount) ? charCount : 0;
    var lines = typeof lineCount === 'number' && isFinite(lineCount) ? lineCount : 0;
    if (chars <= 0) return '空';
    var text;
    if (chars < 1000) text = chars + ' 字符';
    else if (chars < 1000000) text = (chars / 1000).toFixed(1) + 'k 字符';
    else text = (chars / 1000000).toFixed(1) + 'M 字符';
    if (lines > 1) text += ' · ' + lines + ' 行';
    return text;
  }

  /** 展开正文的截断（返回 ``{text, truncated}``）。 */
  function formatBodyText(text, limit) {
    var value = text === null || text === undefined ? '' : String(text);
    var max = typeof limit === 'number' && limit > 0 ? limit : BODY_LIMIT;
    if (value.length <= max) return { text: value, truncated: false };
    return { text: value.slice(0, max), truncated: true };
  }

  /**
   * 参数对象 → 展开态的缩进 JSON（同样受 ``BODY_LIMIT`` 约束）。
   *
   * @param {*} args 原始参数（对象 / JSON 字符串 / 解析失败的原文）。
   * @param {number=} limit 展示上限，缺省 ``BODY_LIMIT``。可注入是为了让上限本身
   *   可被单测（真上限 200000 字符没法走命令行传给 node harness）。
   */
  function prettyArgs(args, limit) {
    var parsed = parseArguments(args);
    if (parsed === null) return '';
    var text;
    if (typeof parsed === 'string') {
      text = parsed.trim();
    } else {
      try {
        text = JSON.stringify(parsed, null, 2);
      } catch (error) {
        text = String(parsed);
      }
    }
    if (!text) return '';
    var formatted = formatBodyText(text, limit);
    return formatted.truncated ? formatted.text + '\n\n… ' + BODY_TRUNCATED_NOTE : text;
  }

  function setText(node, text) {
    if (node) node.textContent = text === null || text === undefined ? '' : String(text);
  }

  function appendSection(doc, body, label, className) {
    var section = doc.createElement('div');
    section.className = 'tool-row-section';
    var labelEl = doc.createElement('span');
    labelEl.className = 'tool-row-label';
    labelEl.textContent = label;
    var pre = doc.createElement('pre');
    pre.className = className;
    section.appendChild(labelEl);
    section.appendChild(pre);
    body.appendChild(section);
    return pre;
  }

  /**
   * 建一行工具执行。**默认折叠**：body 带 ``hidden``，参数与结果全文都不在折叠态的
   * 可见内容里。头部是 ``<button>``（原生键盘可达、自带 aria 语义），body 是它的
   * **兄弟节点**，所以在 body 里点选文本不会触发折叠切换。
   *
   * @param {Document} doc 调用方注入的 document（模块不读全局 DOM，便于 node 单测）。
   * @param {object} spec ``{name, args, title, summary, state, meta, note}``。
   *   ``note`` 渲染在**头部行**（可见），不是折叠 body 内——提示藏进 hidden 子树
   *   等于没有提示（grill Q3）。
   */
  function createToolRow(doc, spec) {
    var options = spec || {};
    var row = doc.createElement('div');
    row.className = 'tool-call-block tool-row';
    row.dataset.state = options.state || 'ok';
    row.dataset.tool = options.name || '';

    var head = doc.createElement('button');
    head.type = 'button';
    head.className = 'tool-row-head';
    head.setAttribute('aria-expanded', 'false');

    var caret = doc.createElement('span');
    caret.className = 'tool-row-caret';
    caret.setAttribute('aria-hidden', 'true');

    var title = doc.createElement('span');
    title.className = 'tool-row-title tool-name';
    title.textContent = options.title || toolTitle(options.name);

    var sep = doc.createElement('span');
    sep.className = 'tool-row-sep';
    sep.setAttribute('aria-hidden', 'true');

    var summary = doc.createElement('span');
    summary.className = 'tool-row-summary';
    summary.textContent = options.summary || '';

    var meta = doc.createElement('span');
    meta.className = 'tool-row-meta';
    meta.textContent = options.meta || '';

    var note = doc.createElement('span');
    note.className = 'tool-row-note';
    note.textContent = options.note || '';
    note.hidden = !options.note;

    head.appendChild(caret);
    head.appendChild(title);
    if (summary.textContent) head.appendChild(sep);
    head.appendChild(summary);
    head.appendChild(note);
    head.appendChild(meta);

    var body = doc.createElement('div');
    body.className = 'tool-row-body';
    body.hidden = true;

    // 头按钮与展开体是**兄弟节点**，没有 DOM 包含关系；`aria-controls` 是两者之间唯一
    // 的程序化关联（读屏用户据此知道这个按钮控制哪块内容）。
    rowSeq += 1;
    body.id = 'tool-row-body-' + rowSeq;
    head.setAttribute('aria-controls', body.id);

    var argsPre = null;
    if (options.args !== undefined && options.args !== null) {
      var pretty = prettyArgs(options.args);
      if (pretty) {
        argsPre = appendSection(doc, body, '参数', 'tool-row-args');
        argsPre.textContent = pretty;
      }
    }

    row.appendChild(head);
    row.appendChild(body);

    row.__summaryEl = summary;
    row.__metaEl = meta;
    row.__noteEl = note;
    row.__argsPre = argsPre;
    row.__resultPre = null;
    row.__code = '';

    head.addEventListener('click', function () {
      // 展开切换**不滚动**：滚动会把用户正在读的位置顶走（既有安全护栏的意图）。
      var expanded = head.getAttribute('aria-expanded') === 'true';
      head.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      body.hidden = expanded;
    });

    return row;
  }

  /**
   * 把 ``tool_result`` 补进 ``tool_call`` 建出的那一行：更新状态、行尾元数据、
   * 失败时的折叠行表现，并把结果全文写进**已折叠**的 body。
   *
   * 结果全文写进 DOM 但 body 是 ``hidden``：展开是纯可见性切换，不需要二次触发事件，
   * 也不会让折叠态的**可见**文本变长（L2 的量化判据看的是可见文本）。
   *
   * @returns {HTMLElement} 传入的 ``row``。
   */
  function updateToolRow(doc, row, spec) {
    var options = spec || {};
    var display = options.display || null;
    var result = options.result === null || options.result === undefined ? '' : String(options.result);
    var verdict = summarizeToolResult(options.name, result);

    row.dataset.state = options.state || verdict.state;
    row.__code = verdict.code || '';

    var body = row.querySelector('.tool-row-body');
    if (body) {
      var resultPre = row.__resultPre;
      if (!resultPre) {
        resultPre = appendSection(doc, body, '结果', 'tool-row-result');
        row.__resultPre = resultPre;
      }
      var formatted = formatBodyText(result, BODY_LIMIT);
      resultPre.textContent = formatted.truncated
        ? formatted.text + '\n\n… ' + BODY_TRUNCATED_NOTE
        : formatted.text;
      if (verdict.state === 'error') resultPre.dataset.error = 'true';
    }

    // 失败信号：可读的失败首行顶到摘要上；结构化失败（Bash 的单行 JSON / TaskOutput 的
    // 多行 key:value）保留参数摘要——把 `{"exit_code": 1, "stdout": …` 顶上去等于把命令
    // 删掉（grill Q2/R-B）。
    if (verdict.state === 'error' && verdict.summary) {
      setText(row.__summaryEl, verdict.summary);
    }

    var charCount = display && typeof display.char_count === 'number' ? display.char_count : result.length;
    var lineCount = display && typeof display.line_count === 'number'
      ? display.line_count
      : (result === '' ? 0 : result.split('\n').length);
    var meta = formatCharMeta(charCount, lineCount);
    if (verdict.state === 'error') meta = (verdict.code ? verdict.code + ' · ' : '失败 · ') + meta;
    setText(row.__metaEl, meta);
    return row;
  }

  window.AsterwyndToolRows = {
    SUMMARY_LIMIT: SUMMARY_LIMIT,
    ERROR_LIMIT: ERROR_LIMIT,
    BODY_LIMIT: BODY_LIMIT,
    BODY_TRUNCATED_NOTE: BODY_TRUNCATED_NOTE,
    TOOL_TITLES: TOOL_TITLES,
    firstLine: firstLine,
    truncate: truncate,
    compactJson: compactJson,
    toolTitle: toolTitle,
    summarizeToolCall: summarizeToolCall,
    summarizeToolResult: summarizeToolResult,
    taskFailure: taskFailure,
    formatCharMeta: formatCharMeta,
    formatBodyText: formatBodyText,
    prettyArgs: prettyArgs,
    createToolRow: createToolRow,
    updateToolRow: updateToolRow,
  };
})();
