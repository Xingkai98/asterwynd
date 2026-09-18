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
