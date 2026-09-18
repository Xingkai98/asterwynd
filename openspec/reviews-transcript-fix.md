# 审阅报告：transcript 丢失 tool_calls 修复（issue #212 缺陷 A）

审阅对象：`54d0b2e`（`fix: transcript 投影丢弃 tool_calls 导致对话显示成空行`）
分支：`fix-transcript-tool-calls/2026-09-19`
审阅方式：零记忆独立审阅 + 逐条变异验证（M1–M4，每轮单独变异、每轮 `git checkout` 还原并复跑基线）
证据基线：审阅结束时工作区 `git status --porcelain` = 0 行、`git diff HEAD` = 0 行、`HEAD` = `54d0b2e`

## Verdict

**CHANGES_REQUESTED**

修复的正确性、回归保护和前端渲染都成立（M1–M4 四个变异全部被测试捕获，且症状复现精确），但**同一次提交在 `InspectSubagentTranscript` 工具路径上把模型侧上下文放大了 127 倍且没有任何截断**——而这条路径正是本提交自己声明的「截断由调用方做」契约里唯一没履约的调用方。这是一处新增的实质问题（严重度：中），修掉即可 PASS。

## 任务逐条核实

### 1. 正确性 —— 通过（附一处误伤面说明）

**症状是否真的解决**：是。`agent/subagent/manager.py:1068` 的 `**_project_tool_calls(msg)` 把 `tool_calls` 从 `Message` 投影进 `inspect_transcript` 的载荷；`web/session.py:738` 的 `_bounded_messages` 把 `tool_calls` 透传给 HTTP 接口；`web/static/workflow_transcript.js:346` 的 `toolCallBlock` 把它渲染成 `🔧 名字 + 参数`。三层齐全，无断链。

**字段类型核对**：`arguments` 是 JSON **字符串**，不是 dict。已核对全部生产构造点——`agent/openai_llm.py:113`、`agent/anthropic_llm.py:454`（`json.dumps(block["input"])`）、`agent/message.py:129`（`to_dict`/`from_dict` 往返）——全部是 `str`。前端 `prettyArgs`（`workflow_transcript.js:360`）先 `JSON.parse` 再美化、解析失败原样显示，与字符串口径一致。`_bounded_messages:761` 的 `str(call.get("arguments") or "")` 对该类型安全。

**会不会误伤「真该显示的空行」**：不会，抑制条件收得很窄。`workflow_transcript.js:313` 是 `calls.length && parts.length === 1 && !parts[0]`——只有当**整条消息内容恰好为空字符串**且**有工具调用**时才把空文本行替换为 `text: null`。影响面已逐条核对：

- `content` 为 `null`/`undefined`：`workflow_transcript.js:301` 的 `String(message.content || '')` 先归一成 `''`，进入同一判断，行为一致。
- 多行 `content`（`parts.length > 1`）：**不**进抑制分支，即使内容以 `\n` 结尾产生的尾随空行也照旧渲染，原行为不变。
- `content === ""` 且**无**工具调用：不满足 `calls.length`，仍渲染为空行——这是唯一可能被认作「误伤」的形态，但一条既无文字又无工具调用的 assistant 消息没有可展示信息，保留空行反而就是原 bug 的症状；且这种消息在 `agent/loop.py` 里不会产生（`loop.py:750` 的空 `content` 恒带 `tool_calls`；`loop.py:737` 的终轮恒带文字）。
- `role` 标签在两种形态下都保留（`workflow_transcript.js:376`），`roles == 2` 的断言证明了这一点。

### 2. bounded 契约 —— 不通过（见 Issues #1）

HTTP 路由侧**履约**：两条出口 `web/session.py:849`、`web/session.py:984` 都走 `_bounded_messages`，`arguments` 与 `content` 用同一个 `content_limit`（`web/session.py:755` vs `:761`），并把 `arguments_truncated` 标志透出给前端（`workflow_transcript.js:353`）。条数侧三个入口都被 `TRANSCRIPT_MAX_LIMIT = 200` 夹住（`web/session.py:841`、`:889`、`:977`）。**这半边是干净的。**

**但存在一条绕过路径**：`agent/tools/builtin/subagents.py:208` 的 `InspectSubagentTranscriptTool` 直接调 `manager.inspect_transcript(...)`，既不经过 `_bounded_messages`，其 `limit` 参数（`subagents.py:194`）也只有 `minimum: 1`、**没有 maximum**。实测放大倍数见 Issues #1。

### 3. 测试真实性（变异验证）—— 全部通过

四个变异逐个单独施加、逐个还原，每轮还原后复跑基线确认绿。详细结果见下节。**M1–M4 全部被捕获，无一条假保护。**

### 4. spec 对齐 —— 通过（增量，非违约）

`openspec/specs/web-ui/spec.md:733` 的两条约束逐条比对：

- 「SHALL 默认排除工具结果」：**未违反**。`include_tool_results` 默认 `False`，`manager.py:1053` 的 `[msg for msg in messages if msg.role != "tool"]` 仍然生效，`role == "tool"` 的结果消息依旧被整体剔除。新增的 `tool_calls` 挂在 **assistant 自己**的消息上，是「这个节点发起了什么调用」，不是「工具返回了什么」——两者是不同的信息。测试 `test_transcript_tool_results_still_excluded_by_default` 同时钉住了「无 `role=="tool"` 消息」和「`tool_calls` 可见」，方向正确。
- 「接口 SHALL bounded（条数上限 + 单条内容截断 + 候选集分页上限）」：三档都满足，且 `arguments` 走了同一套单条截断。

补 `tool_calls` 是**增量**：它没有放松任何既有默认，只是把原先被静默丢弃的字段补回。

### 5. 回归：`test_server.py` 资源版本号断言改正则 —— 合理，不削弱本意

`tests/web_tests/test_server.py:440-447` 把 6 条 `assert "/static/x.js?v=N" in index` 改成 `re.search(r'/static/x\.js\?v=\d+', index)`。

- **不削弱**：正则仍然要求「文件被引用」且「查询串格式是 `?v=<数字>`」；`?v=` 缺失、文件路径写错、版本号写成非数字，三种情况都会红。唯一的放松是具体数字，而数字不是这条断言的**语义**——它想抓的是「接线漏了」，不是「版本号是几」。
- **动机成立，且有事实支撑**：本次 bump 是必要的。`git log 7972df7..HEAD -- web/static/workflow_transcript.js` 显示该文件在 `7972df7` 引入 `?v=1` **之后**还被 `0e71e07`、`4aea153` 两度修改而未 bump；`workflow.js` 同期间被改 3 次、`workflow_graph.js` 被改 5 次，两者的 `?v=2` 也早已落后于内容。所以提交信息里「transcript.js 的版本号在本次之前就已经落后于文件内容」属实。既然前面三次修改都没改测试也没被测试拦住，说明钉死版本号的断言本就没有起到「逼你 bump」的作用，只制造了噪声。
- **建议（低）**：`index.html:161` 的 `markdown.js?v=6`、`chat.js?v=22` 等未动，属于本次无改动的资源，不动是对的。但 `test_server.py:419` 的 `asterwynd-web-wordmark.png?v=3` 仍是钉死写法，是全仓最后一处版本号硬编码；不阻塞，交给后续清理。

### 6. 范围 —— 通过

改动文件 7 个，全部落在缺陷 A 的完整性链路上，无夹带：

| 文件 | 是否必要 |
|---|---|
| `agent/subagent/manager.py` | 投影层（根因所在） |
| `web/session.py` | 路由层 bounded |
| `web/static/workflow_transcript.js` | 渲染层 |
| `web/static/index.html` | 静态资源 bump |
| `tests/web_tests/test_workflow_node_transcript.py` | 后端回归（新增） |
| `tests/web_tests/test_workflow_graph_browser.py` | 前端回归（新增） |
| `tests/web_tests/test_server.py` | 版本号断言配套调整 |

issue #212 的**缺陷 B**（`trace_digest` 虚假完成）本次未动，与「本次只修 A」的范围声明一致，不是夹带。

版本号 bump 的正确性已核实：本次真正改动的 `workflow_transcript.js` 从 `v=1 → v=2`（必要）；`workflow_graph.js` `v=2 → v=3`、`workflow.js` `v=2 → v=3` 属于**顺带补上历史欠账**（两文件在 `?v=2` 之后分别被改过 5 次和 3 次，见上），并非本次内容变更所必需，但方向正确、无副作用，接受。

## 变异验证结果

方法：每轮单独施加一个变异 → 跑相关测试 → 观察是否变红 → `git checkout -- <file>` 还原 → 复跑基线确认绿。四个变异均单独进行，未叠加。

| 变异 | 改了什么 | 期望 | 实际 | 是否捕获 |
|---|---|---|---|---|
| **M1** | `agent/subagent/manager.py` 删掉 `**_project_tool_calls(msg)`（投影层丢字段） | 后端回归必红 | `test_transcript_keeps_assistant_tool_calls` 红（`带 tool_calls 的 assistant 消息全部丢失`）；`test_transcript_tool_call_arguments_are_bounded` 红（`AssertionError: 带 tool_calls 的消息丢了`，`assert []`）。**2 failed** | ✅ 捕获（2 条测试） |
| **M2** | `web/session.py` 去掉 `arguments` 的 `[:content_limit]` 切片、`arguments_truncated` 恒 `False` | bounded 契约必红 | `test_transcript_tool_call_arguments_are_bounded` 红：`assert 5033 <= 40`（5033 是 5000 字符 `content` 的 JSON 串长度） | ✅ 捕获 |
| **M3** | `workflow_transcript.js` 去掉 `toolCallBlock` 渲染调用 | 前端回归必红 | 两条新浏览器测试都红：`wait_for_selector(".tool-call-block")` 超时 30s。**2 failed** | ✅ 捕获（2 条测试） |
| **M4** | 恢复原始 bug 的精确形态：`emitted[0] = {role, text: parts[0], calls}`（只调工具的轮次重新渲染空文本行） | 症状复现必红 | `test_convo_tab_renders_tool_calls_instead_of_blank_lines` 红：`仍渲染了 1 行空文本（正是用户看到的空 ASSISTANT）`，`assert 1 == 0` | ✅ 捕获（1 条测试） |

**M1 附带发现（非缺陷，但值得记录）**：M1 变异下浏览器回归测试 `test_convo_tab_renders_tool_calls_instead_of_blank_lines` **不**变红。原因是该测试用 `page.route("**/transcript*", ...)` 把 HTTP 响应整个桩掉（`test_workflow_graph_browser.py:790`），只验证前端渲染层，不经过后端投影。这是**刻意的分层**，不是漏保护——同一条根因由后端测试 `test_transcript_keeps_assistant_tool_calls` 兜住。两层各测各的，覆盖是完整的。

**M4 附带的判别力验证**：M4 变异下**只有**空行断言失败（`assert blanks == 0`），工具调用断言（`"Read" in body` 等）依然通过——说明新测试对「工具调用可见」和「空行消失」两个维度是**各自独立判别**的，不是一条断言顺带把另一条也带红。

**每轮还原后的基线**：M1 还原后 `test_workflow_node_transcript.py` 22 passed；M2 还原后 22 passed；M3/M4 还原后两条浏览器测试 + 整个 transcript 测试文件 24 passed。审阅结束时 `git status --porcelain` 与 `git diff HEAD` 均为 0 行。

## Issues

### #1 —— 中 —— `InspectSubagentTranscript` 工具路径新增 127× 上下文放大，且不受 `content_limit` 约束

**文件:行号**：`agent/tools/builtin/subagents.py:208`（调用方）、`agent/tools/builtin/subagents.py:194`（`limit` 无上限）、`agent/subagent/manager.py:62`（`_project_tool_calls` docstring 声明「截断由调用方按自己的 content 预算做」）、`web/session.py:738`（唯一履约的截断点）

**问题**：`_project_tool_calls` 的 docstring 把截断责任下放给调用方，但 `inspect_transcript` 的三个调用方里**只有两个**履约——`web/session.py:849` 和 `web/session.py:984` 走 `_bounded_messages`；第三个 `agent/tools/builtin/subagents.py:208` 直接返回 `json.dumps(result)`，**没有任何截断**，且其 `limit` 参数（`subagents.py:194`）只有 `minimum: 1`、没有 maximum。`arguments` 在 `manager.py` 层是原样 JSON 串（docstring 明说「不带截断」），于是模型侧拿到的就是未截断的全文。

修复前这条路径的放大是**隐性的**：`agent/loop.py:750` 的空 `content` 让只调工具轮次在工具输出里近乎无内容。补上 `tool_calls` 后，每个 Write/Edit 调用的完整正文都进了父 agent 的上下文。

**复现（实测，非推断）**：构造子 agent 连续 3 轮各发起一次 `Write`（`content` 各 20,000 字符），父 agent 用默认参数调 `InspectSubagentTranscriptTool(subagent_id, scope="recent_messages", limit=3)`：

| | 工具返回（进父 agent 上下文） |
|---|---|
| 修复前（`81bca96`） | **320 字符**（约 80 tokens） |
| 修复后（`54d0b2e`） | **40,504 字符**（约 10,126 tokens） |
| 修复后 + `limit=100` | **60,821 字符** |

放大 **127×**。`limit` 无上限意味着这个数字随 `limit` 线性增长，而工具 schema 不拦。

**为什么算「新增」而不是「既有」**：这条路径的 `content` 确实**本来就**没有截断（`extract_text(msg.content)` 同样不受限）。但对「只调工具、不写文字」的子 agent——也就是本提交自己论证的 AgentLoop **大多数**轮次形态——修复前该路径近乎空格，修复后才第一次出现大载荷。所以量级是本次引入的。

**建议（最小修复，二选一）**：
1. 在 `agent/tools/builtin/subagents.py:194` 给 `limit` 补 `"maximum": 50`（对齐 `TRANSCRIPT_MAX_LIMIT` 的量级），并在 `subagents.py:208` 处对每条 `arguments` 做与 `content` 同口径的截断 + 带 `arguments_truncated` 标志——即让工具路径也履约 docstring 的契约；或
2. 若判定工具路径应保持「模型自己控预算」的现状，则在 `_project_tool_calls` 的 docstring（`manager.py:62`）显式写明「`InspectSubagentTranscript` 调用方不做截断，模型侧载荷不受 bounded 约束」，并把这条差异记进 spec/known-debt，别让契约停留在只对两个调用方成立的表述上。

**不阻塞的理由**：HTTP 接口（spec 约束的那一侧）完全合规，前端不会因此变大。影响面仅限 LLM 自行调用的 `scope="recent_messages"` 路径。但考虑到本项目主线之一就是上下文管理，且这是本提交新引入的量级，仍按中处理。

### #2 —— 低 —— 浏览器测试 flake（既有，非本次引入）

**文件:行号**：`web/static/chat.js:1917`（`init()` 里 `await fetch('/api/slash-commands')` → `await fetch('/api/debug-status')`）、`web/static/chat.js:308`（`showHub()` → `showView('hub')`）、`web/static/chat.js:252`（`workflowViewEl.classList.toggle('active', ...)` 摘掉 `active`）、`tests/web_tests/test_workflow_graph_browser.py:115`（测试 helper `_push_workflow_event` 的派发时机）

**问题**：`init()` 是 async，在两次 `await fetch` 完成前，测试已经通过 `_push_workflow_event` 把 `workflow_started`/`workflow_snapshot` 派发完并让测试 tab 给 `#workflow-view` 加上了 `active`；随后 `init()` 的 `showHub()` → `showView('hub')` 把 `active` 摘掉，`#workflow-view` 变 `display:none`，其中的 `svg.workflow-svg` 被判为 hidden，`wait_for_selector` 超时 30s。

**失败形态**：`TimeoutError: waiting for locator("#workflow-canvas svg.workflow-svg") to be visible` / `63 × locator resolved to hidden <svg class="workflow-svg" ...>` —— DOM 已存在但不可见，正是 `active` 被摘的特征。

**实测（同一测试、逐个隔离运行、无并发争用）**：

| | `test_convo_tab_lazily_fetches_transcript` 8 次 |
|---|---|
| `master`（`81bca96`） | 4 failed / 4 passed |
| `fix`（`54d0b2e`） | 5 failed / 5 passed（n=8 时 5 failed 3 passed） |

两者在 n=8 上不可区分，**flake 是既有的**。判定为既有还有一条独立证据：触发竞态的四处代码（`chat.js` 的 `init`/`showView`/`showHub`、测试 helper `_push_workflow_event`）在 `54d0b2e` 中**零改动**。

同一机制还波及 `tests/web_tests/test_multi_session_browser.py`（该文件本次亦零改动），已由既有 issue #191 跟踪。

**未定性的一点**：本次新增的两条浏览器测试（`test_workflow_graph_browser.py:776`、`:819`）在隔离单跑与 `-k convo` 组合下均稳定通过，未观察到同一竞态。但它们的首行结构（`goto` → `wait_for_function` → `_start_workflow`）与既有 flake 测试**完全相同**，理论上共享同一竞态窗口。审阅未对这两条做 8 次以上的重复采样（时间预算留给了变异验证），故「新测试是否也会 flake」只能记为未覆盖，不下结论。

**建议**：不属本次修复范围，不在本 PR 处理。若要修，方向是让 `_push_workflow_event` 在派发前等待 `init()` 稳定（例如 `wait_for_selector(".tab-pane.active .user-input")`，即 `test_workflow_graph_browser.py:130` 那个已有的就绪信号），或让该 helper 在派发后重新置位 `#workflow-view` 的 `active`。跟踪到 issue #191。

### #3 —— 低 —— `workflow.js` / `workflow_graph.js` 的版本号 bump 属顺带补欠账，非本次必需

**文件:行号**：`web/static/index.html:162`（`workflow_graph.js?v=2 → v=3`）、`web/static/index.html:164`（`workflow.js?v=2 → v=3`）

**说明**：两个文件本次内容**未改动**，bump 是补历史欠账（`workflow_graph.js` 自 `?v=2` 后已被改 5 次、`workflow.js` 3 次）。方向正确、无副作用（bump 只会让客户端多拉一次静态资源），但不属于缺陷 A 的最小必要改动。接受，仅记录以便审阅口径完整。

## 未覆盖

诚实标注本次审阅**没有**核实到的部分：

1. **真实 LLM 端到端**：全部验证用桩 LLM（`_ToolCallingLLM` / `_HugeArgsLLM` / 脚本化 `_Huge`）。未用真实 provider 跑一次「30 条消息、10 次工具调用」的节点来复现用户原始场景。桩覆盖了字段形态与放大倍数，但不覆盖真实模型的 `arguments` 长度分布与多轮交错形态。
2. **手机端/PWA 实际缓存行为**：版本号 bump 的必要性由文件内容与版本号历史推定，未在真机或 PWA 上验证「bump 后旧 JS 确实被换掉」。
3. **新浏览器测试的 flake 率**：见 Issues #2 末段——未对 `test_workflow_graph_browser.py:776`/`:819` 做 ≥8 次重复采样，无法排除它们共享既有竞态窗口。
4. **全量 pytest 的干净复跑**：跑了一次全量（`--ignore=tests/web_tests/test_workflow_graph_browser.py`），结果 `2854 passed, 8 skipped, 2 failed, 1 error`，其中 3 条红全部落在 `tests/web_tests/test_multi_session_browser.py`（本次零改动，同属既有 issue #191 的 flake 家族，隔离复跑 3 次中 2 次全绿）。已知无关的既有失败 `tests/test_declarative_flow_engine.py::TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code` 未单独确认（该文件在本次全量中被 `--ignore` 之外的正常收集覆盖，未出现在失败列表里）。**未在无并发争用的环境下做第二次全量复跑**。
5. **`include_tool_results=True` 路径**：缺陷 A 的默认路径已覆盖，但显式打开工具结果时的载荷大小与截断行为未单独验证。
6. **issue #212 缺陷 B（`trace_digest`）**：按「本次只修 A」的范围声明，未审。

---

# R2 复审

审阅对象：`1635e42`（R1 修复 `1260a82` + 三条补测 `e8c7e16` / `102994f` / `1635e42`）
审阅方式：零记忆独立复审 + 独立复现（不复用仓库测试桩）+ 逐轮变异验证（M-R1a/b/c、c′、M5，每轮单独施加、每轮 `git checkout` 还原并复跑基线）
证据基线：审阅结束时工作区 `git status --porcelain` = 0 行、`git diff HEAD` = 0 行、`HEAD` = `1635e42`；四个源码/测试文件 md5 与本轮开始时逐一相同

## Verdict

**PASS**

R1 的「中」Issue（`InspectSubagentTranscript` 工具路径上下文放大）**已真正修好**，且经独立复现确认放大消除、`limit` 夹取在代码层生效、截断标志两个方向都不谎报。R1 的三条新测试逐个变异验证**全部是真保护**，无假保护、无变异存活。浏览器测试的就绪等待修复（`1635e42`）经反证确认真实有效。修复未引入新的实质问题；下方两条「低」记录均为可选改进，不阻塞。

## R1 Issue 逐条复核

### Issue #1（中）—— 已修好 ✅

**独立复现方法**（刻意不复用仓库测试的 `_HugeArgsLLM`，自己写一个「连续 3 轮各发一次 20KB `Write`」的脚本化 LLM，走完整的 `scheduler → AgentLoop → manager.inspect_transcript → 工具 execute` 链路）：

| `limit` | post-fix（HEAD） | pre-fix 模拟（`_bounded_arguments` 猴补为恒等） |
|---|---|---|
| 3 | 8,496 字符 | 40,564 字符 |
| 5（工具默认） | 12,719 字符 | 60,821 字符 |
| 100 | 12,807 字符 | 60,909 字符 |
| 200 | 12,807 字符 | 60,909 字符 |
| 100000 | 12,807 字符 | 60,909 字符 |

- **放大已消除**：修复后输出**不再随 `limit` 增长**（100 → 100000 三条完全同长，12,807 字符封顶）。修复前是线性增长（40K → 61K）。这与提交信息「修后实测 12,580 字符，limit=100 也仅 12,668」同量级，独立复现数字略高是因为我的 fixture 多了一轮 20KB 的**文字**收尾（`content` 不受 `TOOL_CALL_ARGUMENT_LIMIT` 管，见下「新发现」）。
- **注意 R1 报告里的 127× 无法用本次的 pre/post 比值复现，也不该复现**：R1 的 320 字符基线是缺陷 A 修复**之前**（`81bca96`，投影层根本不投影 `tool_calls`，所以工具路径近乎空格）。本次比的是「R1 修复前 vs 后」，两者都已有 `tool_calls`，所以比值是 4.8×（60,909 / 12,807），不是 127×。两个数字口径不同，不矛盾。已用 `git show 81bca96:agent/subagent/manager.py` 确认该提交里确实没有 `tool_calls` 投影，320 字符基线成立。

**`limit` 夹取在代码层生效（不只 schema）**：直接对 `InspectSubagentTranscriptTool.execute()` 打表，session 里预置 503 条消息（**必须真的超过上限**，否则「返回 ≤200」恒真）：

| 传入 | 返回条数 |
|---|---|
| 不传（默认） | 5 |
| 100000 | 200 |
| 201 | 200 |
| 200 | 200 |
| 100 | 100 |
| 0 | 1（夹到 minimum） |
| -5 | 1（夹到 minimum） |

夹取发生在 `agent/tools/builtin/subagents.py:218` 的 `min(max(int(requested) or 1, 1), self.MAX_TRANSCRIPT_LIMIT)`——**是代码**，不是 `_bounded_arguments` 那种靠 schema 提示。schema 的 `maximum: 200`（`subagents.py:197`）与代码层同值，两层一致。

**截断标志两个方向都正确（不谎报）**：

- 上游截过 + 本层预算更大 → 报 `True`：路由 `content_limit=8000 > TOOL_CALL_ARGUMENT_LIMIT=4000` 时，`arguments` 长度 4000、`arguments_truncated=True`。✅ 这正是 R1 担心的「谎报未截断」，已由 `web/session.py:767` 的 `bool(call.get("arguments_truncated")) or len(arguments) > content_limit` 取或挡住。
- 上游没截 + 本层截 → 报 `True`：`content_limit=10` 时长度 10、标志 `True`。✅
- HTTP 默认路径：长度 4000、标志 `True`。✅

### Issue #2（低，浏览器 flake）—— 处置合理 ✅

`1635e42` 只给**新增的两条**测试补就绪等待、不动既有 15 条。这个取舍成立，理由有三条独立证据：

1. **修复真实有效，且是这道竞态的正解**。反证：把新测试里的 `_wait_app_ready(page)` 去掉（**保留** `state="visible"`），单跑 6 次 → **2 failed / 4 passed**。留着则 6/6 全绿。说明 `state="visible"` 是冗余的、`_wait_app_ready` 才是真正的修复（它等 `chat.js` 异步 `init()` 落定，从根上避免 `showHub()` 事后摘掉 `active`）。
2. **flake 确属既有**。触发竞态的代码（`chat.js` 的 `init`/`showView`/`showHub`、helper `_push_workflow_event`）在本次提交里零改动；issue #191 是已存在的 open 跟踪项（标题即「浏览器测试偶发 flake」）。
3. **新测试已不再共享该竞态窗口**：新测试 A 单跑 6/6、新测试 B 单跑 6/6、全文件 20 条连跑 3 次皆 `20 passed`。

**保留意见（低，不阻塞）**：只修新增的两条，等于承认既有 15 条仍带同一缺陷。这在本 PR 范围内是对的（R1 也是这么建议的，issue #191 已跟踪），但值得在 PR 描述里显式引用 #191，避免这半个修复被读成「flake 已解决」。

### Issue #3（低，版本号 bump）—— 记录合理 ✅

已核对 `web/static/index.html:162,164`：`workflow_graph.js?v=2→v=3`、`workflow.js?v=2→v=3`，`workflow_transcript.js?v=1→v=2`。前两者本次内容未改，属顺带补历史欠账，方向正确、无副作用。R1 的判断维持。

## 变异验证结果（R1 三条新测试 + 前端）

方法同 R1：每轮单独施加一个变异 → 跑相关测试 → 观察是否变红 → `git checkout -- <file>` 还原 → 复跑基线确认绿。**每轮还原后 `git status --porcelain` 均为 0 行、基线均 `25 passed`。**

| 变异 | 改了什么 | 期望 | 实际 | 是否捕获 |
|---|---|---|---|---|
| **M-R1a** | `agent/subagent/manager.py:98` `_bounded_arguments(call.arguments)` → 不截断 | 生产者侧兜底必红 | `test_tool_call_arguments_bounded_even_without_route_limit` + `test_truncation_flag_composes_across_producer_and_route` 红（`assert 5033 <= 4000`）。**2 failed** | ✅ 捕获（2 条） |
| **M-R1b** | `web/session.py:767` 取或 → 只看本层长度 | 标志取或必红 | `test_truncation_flag_composes_across_producer_and_route` 红（`assert False is True`，文案「上游已截断但本层预算更宽——只看本层长度会谎报」）。**1 failed** | ✅ 捕获（1 条）——正是 `e8c7e16` 补的那个缺口 |
| **M-R1c** | `agent/tools/builtin/subagents.py:218` 去掉 `min(..., MAX_TRANSCRIPT_LIMIT)` 夹取 | limit 夹取必红 | `test_inspect_tool_clamps_limit_and_arguments` 红：`limit 未被夹取：拿到 304 条`，`assert 304 == 200` | ✅ 捕获 |
| **M-R1c′**（更弱的变体） | 同上，但夹到**错的**上限 `1000` | 应同样红 | 同上测试红。说明断言钉的是「夹到 200 这个值」，不是「夹过一下」 | ✅ 捕获 |
| **M5** | `web/static/workflow_transcript.js:353-355` 去掉 `（参数已截断）` 渲染 | 前端标志语义必红 | `test_convo_tab_survives_malformed_tool_arguments` 红（`assert "参数已截断" in body`）。**1 failed** | ✅ 捕获 |

**结论：5 个变异全部被捕获，无一条假保护，无变异存活。**

`102994f` 的补测尤其关键：`102994f` 之前的断言是 `len(payload["messages"]) <= TRANSCRIPT_MAX_LIMIT`，而当时 fixture 只产出个位数消息 → 该断言恒真，M-R1c 会**存活**。改成 `== TRANSCRIPT_MAX_LIMIT` 并补 300 条 padding 之后才真正可判——本次 M-R1c 与 M-R1c′ 均红，证明这个缺口确已补上。

## 新发现

### N1 —— 低 —— 两个 4000 常量**只被单向弱锁**，注释的「同值」承诺没有机械保障

**文件:行号**：`agent/subagent/manager.py:62-64`（`TOOL_CALL_ARGUMENT_LIMIT = 4000`，注释声称与 `TRANSCRIPT_CONTENT_LIMIT` 同值）、`web/session.py:728`（`TRANSCRIPT_CONTENT_LIMIT = 4000`）、`tests/web_tests/test_workflow_node_transcript.py:622`（只锁了 200 那一对）

**核实结果**（逐一实测改常量再跑测试）：

| 改哪一处 | 结果 | 判定 |
|---|---|---|
| `manager.TOOL_CALL_ARGUMENT_LIMIT` 4000 → 9999 | 2 failed | 被**间接**捕获 |
| `manager.TOOL_CALL_ARGUMENT_LIMIT` 4000 → **4001** | **25 passed** | ❌ 漏 |
| `manager.TOOL_CALL_ARGUMENT_LIMIT` 4000 → **4500** | **25 passed** | ❌ 漏 |
| `manager.TOOL_CALL_ARGUMENT_LIMIT` 4000 → 1000 | 25 passed | ❌ 漏（放宽方向安全，但没锁住） |
| `tool.MAX_TRANSCRIPT_LIMIT` 200 → 999 | 1 failed | ✅ 被 `:622` 直接锁定 |
| `web.TRANSCRIPT_CONTENT_LIMIT` 4000 → 9999 | **全量 web 测试 274 passed，0 failed** | ❌ **完全漏** |

三点事实：

1. **测试文件里根本没有 `TRANSCRIPT_CONTENT_LIMIT`**（`grep` 命中 0 处）。提交信息说「测试锁定了一致」——那锁定的是 `MAX_TRANSCRIPT_LIMIT == TRANSCRIPT_MAX_LIMIT`（200 那一对，`tests/...:622`），**不是** `TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT`（4000 那一对）。4000 这一对**没有任何断言**，`grep -S` 全历史也从未存在过。
2. 4000 对上 manager 侧「改了就红」的那两档（≥5033）是**数值巧合**：`_HugeArgsLLM` 的 arguments 恰好是 5033 字符，超过它才看得出来。`4500` 这种「其实已经漂移、但没跨过 fixture 长度」的改动完全不报，`1000` 这种更不报。这是**侥幸兜底**，不是契约锁定。
3. web 侧完全无保护：把 `TRANSCRIPT_CONTENT_LIMIT` 改成 9999，全量测试 274 条全绿。若真漂移，路由层会比生产者宽，`arguments_truncated` 的取或逻辑仍正确（不会谎报），但 `content` 截断口径就与模型面不一致了，且注释里「同一个概念不该有两个数」的话会变成假话。

**严重度定低**：不产生错误行为——两个数**当前**同值，取或逻辑在两侧不等时也仍然正确（不谎报），只是放大/截断口径不一致。**建议（可选，不阻塞）**：在 `test_inspect_tool_clamps_limit_and_arguments` 里把 `:622` 的那行扩成两条：

```python
assert InspectSubagentTranscriptTool.MAX_TRANSCRIPT_LIMIT == TRANSCRIPT_MAX_LIMIT
assert TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT   # 补这一条
```

一行断言即可把 manager↔web 的 4000 口径钉死，消除「注释写死、机制不锁」的漂移面。

### N2 —— 低 —— 工具路径的 `content` 仍不受限（**既有**，非本次引入）

**文件:行号**：`agent/tools/builtin/subagents.py:219-226`（工具直接 `json.dumps(result)`）、`agent/subagent/manager.py:1091`（`extract_text(msg.content)` 不带截断）

**实测**：子 agent 最后一轮输出 30,000 字符文字（非工具调用）时，`InspectSubagentTranscriptTool` 返回 **34,507 字符**，其中 30,000 来自 `content`——`arguments` 已被兜在 4000，但 `content` 没有。

**判定为既有**：已用 `git show 54d0b2e^:agent/tools/builtin/subagents.py` 确认，缺陷 A 修复**之前**该工具路径就直接 `json.dumps` 且对 `content` 无截断，`extract_text` 同样不受限。本次修复没有让它变糟，也没有义务修它（R1 Issue #1 明确只针对 `arguments` 的量级，且 `content` 的放大不是本提交引入的）。

**严重度低、非本次阻塞**：但它与 N1 是同一个「模型面不受 bounded 约束」的根，建议合并记入 known-debt 或后续 change，而不是留在两处注释的口径缝里。注意它也让本次修复后的上限不是「12.8K 封顶」而是「随子 agent 文字输出线性增长」——我的复现里 12,807 字符 vs 提交里的 12,580 差异就来自这一项。

## 未覆盖

诚实标注 R2 **没有**核实到的部分：

1. **真实 LLM 端到端**：与 R1 相同——全部验证用桩 LLM（脚本化大 `Write` / `_HugeArgsLLM`）。未用真实 provider 跑一次 30 条消息、10 次工具调用的节点。两轮审阅都停在桩层面，这是本次修复遗留的最大验证缺口。
2. **手机端/PWA 实际缓存行为**：版本号 bump 的有效性仍只由文件内容与版本历史推定，未在真机验证。
3. **`include_tool_results=True` 路径**：仍未单独验证其载荷大小与截断行为（R1 未覆盖项 5 沿用）。
4. **既有 15 条浏览器测试的 flake 率**：只定性确认它们仍带同一竞态（issue #191），未测其失败率；本轮全文件连跑 3 次恰好 3 次全绿，不足以反证 flake 不存在（R1 实测其 n=8 约半数失败）。
5. **`test_declarative_flow_engine.py::TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code`**：按任务说明属 master 同样红的既有失败，本轮全量（`--ignore` 两个 flake 文件）未出现该失败，未单独复跑确认。
6. **`tests/web_tests/test_reconnect_pending_interaction_browser.py::test_streaming_delta_after_reconnect_lands_in_live_dom`**：本轮全量跑出现 1 次失败，隔离重跑 4 次全绿、该文件本次零改动，判为同族高负载 flake；但**未在 base commit 上做对照复跑**，故「既有」这一判定证据强度弱于 R1 对 #191 的实测。
