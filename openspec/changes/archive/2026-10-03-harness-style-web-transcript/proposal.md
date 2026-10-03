# Proposal: Web 对话区改为 harness 式 transcript（正文成文 + 工具执行单行折叠）

- 关联 issue：[#289](https://github.com/Xingkai98/asterwynd/issues/289)（实现期本机到 `github.com:443` 不可达，见 `## Impact Analysis` 的 process 小节；建 issue 曾列为 `(post-merge)` 任务，网络恢复后已建号并回填）。
- 前置能力：`render-markdown-in-chat-surfaces`（assistant 正文 markdown 渲染）、`add-tool-result-display-controls`（工具结果 display policy）、`add-streaming-agent-output`（增量渲染），三者均已合入归档。

## Change Type

- primary: feature
- secondary: [refactor]

## Why

当前 Web 对话区是「聊天泡泡」形态，工具执行会把整段结果糊在时间线上，长任务下无法阅读。三个已实测的具体问题：

| 编号 | 现象 | 证据 |
|------|------|------|
| G1 | 工具结果的 **collapsed 预览（1200 字符）直接铺在对话流里**，不是折叠 | `web/static/chat.js:948-951`：`body.textContent = display.collapsed ? display.preview : fullResult`；阈值 `agent/tool_result_display.py:14` `DEFAULT_PREVIEW_CHARS = 1200` |
| G2 | 工具名与参数**默认全展开**，`<pre>` 直接进时间线 | `chat.js:909-920` `addToolCallBlock` 无条件 append `<pre>` of `JSON.stringify(args, null, 2)` |
| G3 | 重连后工具输出被渲染成 **user 泡泡**（更刷屏） | `chat.js:741` `const role = message.role === 'assistant' ? 'assistant' : 'user'`，把 `session_history` 里 `role: "tool"` 的消息折成 user |

用户诉求（本次会话原话）：**「现在 web 界面还是对话的泡泡那种形式……主要就是对话展示出来，其余工具执行都默认只展示一行隐藏，可以展开，这样不会被各种内容刷屏。」**

## What Changes

1. **对话正文成文**：user / assistant / system / error 四类消息保留 `.message` 语义类名，但去掉气泡视觉（无圆角底色、不左右对齐、不 85% 宽），改为**单列定宽文档流**。user 轮是整列宽的输入块（左侧强调条 + `你` 微标签），assistant 正文无底色无边框。
2. **工具执行降为一行**：每次工具调用在对话流里占**一行** `▸ Bash · pytest -q · 1.2k 字符`，默认折叠；点击展开才渲染 参数 / 结果 全文。折叠态**不再输出任何结果预览文本**（G1 的根治）。
3. **调用与结果合成一行**：`tool_call` 先建行（`data-state="running"`，行尾有进行中标记），配对的 `tool_result` 到齐后原地补全（`ok` / `error`），不新增第二块。失败时**不自动展开**：可读的失败首行顶到折叠摘要（错误色），**结构化结果（Bash 的单行 JSON 信封）保留参数摘要**、失败因由进行尾 meta。
4. **新增共享渲染模块 `web/static/tool_rows.js`**（`window.AsterwyndToolRows`）：纯函数（工具行摘要、结果态判定、截断）+ DOM 构建，供 `chat.js` 与 `workflow_transcript.js` 共用；工作流抽屉「对话」tab 从手搓 `.tool-call-block` 改为同一行组件，消除两处口径漂移。
5. **重连历史保真**：`renderHistory` 把 `role: "tool"` 渲染为折叠工具行（而非 user 泡泡），并靠 `session_history` 新增的 `tool_call_id` / `tool_calls`（仅 id+name）投影**拿回真工具名与参数摘要**。
6. **思考链同款一行**：`.message-reasoning` 由整块带框折叠区改为同款单行 `▸ 思考过程 · 1.2k 字`，保留既有类名与 `aria-expanded` 语义（浏览器测试直接依赖）。
7. **配对健壮性**：`done` / `error` 到达时收尾未配对行（标记为异常并清空队列），`session_history` 与 `/clear` 清空队列；避免僵尸行认领下一轮结果。
8. **不必变的**：WebSocket 事件契约（**不新增字段**）、tool result display policy 阈值、`agent/` 下任何代码。

## Capabilities

### Modified Capabilities

- `web-ui`: 对话区展示契约从「聊天气泡 + 工具结果预览块」改为「正文文档流 + 工具执行单行折叠」；新增 `window.AsterwyndToolRows` 为对话区与工作流抽屉的**唯一**工具行渲染口径；`session_history` 载荷增补 `tool_call_id` / `tool_calls` 投影。

## Dependencies

- 无新增运行时依赖（纯静态资源 + 一处历史载荷投影，零构建步骤）。
- 复用既有事件契约（`tool_call` / `tool_result` / `session_history` / `assistant_delta` / `reasoning_delta`）。

## 验收

| 级别 | 判据 | 证据归属 |
|------|------|----------|
| L0 | 单行折叠：一次含工具的 run 结束后，对话区**每个工具调用恰好一个可见行**，`.tool-row-body` 处于 `hidden` | 浏览器测试（`window.AsterwyndChatTest.dispatch` 派发合成事件） |
| L1 | 展开可用：点击该行后 参数 / 结果 全文出现，再次点击收起；`aria-expanded` 同步；展开体内点击不折叠 | 同上 |
| L2 | 不刷屏量化：含 20 个工具调用 + 每个 5000 字符结果的 run，折叠态对话区**可见文本 < 1200 字符**，且**每个摘要 ≤ 90 字符**（结构断言，逐行定位） | 同上。对照现状：旧实现 = 20 × `display.preview`(1200) ≈ **24000 字符** |
| L3 | 重连不退化：`session_history` 含 `role: "tool"` 时渲染折叠行而非 user 泡泡，且带 `tool_calls` 的历史行显示真工具名 | 浏览器测试 + `test_session.py` 载荷断言 |
| L4 | 失败可见：`[Approval denied: …]` 这类可读失败首行顶到折叠摘要；`{"exit_code": 1, …}` 结构化失败保留命令、行尾给出 `exit 1`；均不自动展开 | node 纯函数测试 + 浏览器测试（用**真实** Bash JSON 形态） |
| L5 | 抽屉同口径：工作流抽屉「对话」tab 的工具调用也是单行折叠，且「参数已截断」提示**可见** | `test_workflow_graph_browser.py` 既有断言 + 本 change 新增可见性断言 |

阈值：L2 的门槛按「实测 20 行 ≈ 600 字符」留 2 倍余量取 1200。**不能取 4000**——把摘要换成「结果前 150 字符」时 20×150+600=3600 仍能通过，那正是刷屏回归却全绿的假保护形态。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 「harness 式 transcript」是成熟 coding agent 的**标配交互面**（对标业界产品），且本 change 要新建一个共享渲染层并改动对话区信息层级（架构级 UI 改造），命中 `full` 判据；必须先把业界与本地参考仓库的口径看实，否则容易做成「只是换了配色」。
- research questions:
  - RQ1 对话流如何区分 user 与 assistant：泡泡、左侧导轨、还是纯文档流？折叠态与展开态各是什么 DOM 形状？
  - RQ2 工具调用的**一行**由哪几段组成（图标 / 动词 / 目标 / 元数据），各段宽度与截断策略是什么？
  - RQ3 展开后渲染什么（原始参数、结果、diff、stdout 卡片），失败与进行中如何表现在**折叠行**上？
  - RQ4 连续多个工具调用是否合并成一组，组头怎么读？
  - RQ5 无框架（零构建、vanilla JS）实现这套信息层级时，哪些结构是必须的、哪些是框架带来的偶然复杂度？
- findings:
  - **本地参考仓库 `D:\code\deepseek-harness` 可用**（`packages/client/ui-tool`、`ui-conversation`、`ui-chat`、`ui-primitives`）。核心行组件 `ToolRow.tsx` 的折叠行是**固定 24px 单行**：`[16px leading 图标] gap6 [title 13/24] gap8 [2×2 圆点分隔符] gap8 [summary FILL 截断]`；`ToolRow.module.css` 把这条尺寸链写成注释，`.summary` 用 `flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap` 保证**永远一行**，`.summarySuffix` 用 `flex:none` 且**重复 nowrap**（注释明确：只 `flex:none` 挡不住文字换行，窄行会破行）。
  - RQ2/RQ3 的**关键设计事实**：`ToolRow.tsx` 先算 `inputRaw/outputText/card`，再 `expandable = state !== 'preparing' && (inputRaw !== null || outputText !== null || card !== null)`；`bodyRaw` 的注释写明「Original argument JSON formatted **only while the row is expanded**」——即折叠态**根本不渲染**参数与结果文本，展开才格式化。这正是本 change G1 要的语义。
  - RQ3 失败态：`ToolRow.tsx` 把失败单独建模——`failureLine = state === 'error' ? errorSummary ?? normalSummary : null`，折叠行**用失败首行替换原摘要**（`.errorSummary` 上错误色），并且**不自动展开**；`stopped`（被打断）保留业务图标、摘要转琥珀色。`stateStatus()` 额外输出视觉隐藏的运行/失败/停止文案给读屏——颜色不是唯一载体。
  - RQ1：对话侧的**正文**不套卡片，`ui-conversation` 的骨架（`ConversationContent` / `ConversationMainPanel` / `ConversationRoot.module.css`，`.column { max-width: var(--dsh-chat-content-width); width:100%; margin:0 auto }`）把消息排成一条定宽列，工具行与正文是**同一列的兄弟节点**、按到达顺序排列——与本仓 `messagesEl` 平铺 append 的结构同构，说明**不需要引入 turn 包装层**即可达成目标观感（这是本 change D1 的直接依据）。
  - **DSH 的 user 轮仍是右对齐泡泡**（`MessageItem.tsx::UserStyleBubble` → `.bubble { border-radius: 20px; padding: 10px 16px; max-width: min(70.2%, 82%) }`，靠对齐 + 底色承载角色，无头像无标签）。本 change **刻意偏离**这一条：用户诉求是「不要泡泡那种形式」，保留右对齐圆角泡泡会让整体观感仍是聊天窗。assistant 侧无泡泡 + 工具行折叠这两条**完全采纳**。
  - RQ3 补充：DSH 折叠行的展开体是头部行的**兄弟节点**（`DisclosureRow.tsx` 的 `{open && children}`），且 `keepContentWhenOpen` 让折叠摘要**展开后仍在**；展开体统一缩进 22px（= leading 16 + gap 6，对齐到标题文字）。三条都采纳。
  - RQ3 失败态补充：DSH 有 `bash` 专属修正 `terminalFailed()`——退出码非 0 的行**即使 `isError === false`** 也判 `error`，否则红色退出码只有展开才看得见。本 change 采纳并推广到「结构化 JSON 结果」（`exit_code` / `timed_out` / `oom_killed`）。
  - RQ4：DSH 有 `ToolCallTree` + `process-groups.ts` 做连续调用归组，组头是**类别短语**（`Ran commands` / `Read files, ran commands, searched code`，无数量）。本 change **偏离**：用户诉求是「工具执行都默认只展示一行」，按次一行是字面要求；且归组依赖每个调用有稳定 id 与可合并父节点，本仓事件无 id，合并错行风险大于「少几行」的收益。
  - RQ5：DSH 的复杂度大头来自它自己的 slot/主题/字号轴系统（`--dsh-content-font-size-secondary`、`TextShimmer`、`DisclosureRow`）——这些是框架与设计系统的产物，**不是**该信息层级的必要条件。vanilla 实现只需：一行 flex（图标 / 标题 / 圆点 / 可截断摘要 / 不换行的 meta）+ 一个 `hidden` 的 body + `aria-expanded` 驱动的 caret。
  - **后端错误通道调研（grill 追加，决定 L4 是否成立）**：本仓真实的失败文案由后端自己产生，前缀集见 `agent/loop.py::_text_prefix_guess`（`[Error` / `Error` / `[Permission denied` / `[MCP tool error`）+ `agent/tools/registry.py`（`[Permission denied` / `[Approval required`）+ `agent/loop.py` 的审批分支（`[Approval denied` / `[Approval unavailable`）；而 `Bash` 走的是 `SandboxResult.to_json()` **单行 JSON 信封**（`agent/tools/sandbox/base.py`），`SandboxResult.__str__` 的 `[Exit N] …` 形态在 chat 的 WS 路径上并不产生。这两条决定：失败判定必须对齐前缀集（否则「审批被拒」显示为成功），且结构化失败不能把首行顶到摘要上（那等于把命令删掉）。
  - 无本地参考仓库不可用的问题（`D:\code\deepseek-harness` 已 clone，HEAD `639ed01539`）。
- design impact:
  - D2（新增共享 `tool_rows.js`）来自 RQ2/RQ5：行组件必须同时服务对话区与抽屉，且要有可被 node 直接测的纯函数层。
  - D3（折叠态不渲染任何结果文本）来自 RQ3 的 `bodyRaw` 口径与 G1。
  - D4（失败不自动展开；可读首行上摘要 + 错误色）来自 RQ3 的 `failureLine`；「结构化失败保留参数摘要」来自后端错误通道调研。
  - D5（不新增事件 id、按到达顺序配对）来自 RQ4 的代价评估。
  - D1（不引入 turn 包装层）来自 RQ1 的同构结论；D8（展开保留头部）来自 `keepContentWhenOpen`。
  - D6（历史工具名）来自后端字段调研：`Message` 已带 `tool_call_id` / `tool_calls`，成本是一处载荷投影，不是协议改造。

## Impact Analysis

### 能力域

- `web-ui`：对话区（`#chat-view` 的消息流）展示契约变更；新增 `AsterwyndToolRows` 命名空间；`session_history` 载荷增补两个字段。
- 不改：`tool-system`（display policy 阈值不变）、`agent-runtime`（事件契约不变，未动 `agent/loop.py`）、`multi-agent-collaboration`（工作流图与快照不变，只改抽屉「对话」tab 的一行渲染）。

### 代码

| 文件 | 改动 |
|------|------|
| `web/static/tool_rows.js` | **新增**。`window.AsterwyndToolRows`：纯函数 `firstLine` / `truncate` / `compactJson` / `toolTitle` / `summarizeToolCall` / `summarizeToolResult` / `formatCharMeta` / `formatBodyText` / `prettyArgs` + DOM 构建 `createToolRow(doc, spec)` / `updateToolRow(doc, row, spec)`。纯函数不碰 DOM，DOM 构建只接受传入的 `document`。文件名刻意不含 `transcript` 字样（见下）。 |
| `web/static/chat.js` | `addToolCallBlock` 改建折叠行并入 FIFO 待配对队列；`addToolResultMessage` 改为**补全**已存在的行；新增 `settleOrphanToolRows`（`done`/`error` 收尾）；`renderHistory` 区分 `role === 'tool'` 并用 `tool_calls` 反查工具名；`addMessage` 增 `data-role` 与 user 角色微标签；新增 per-tab `pendingToolRows`（同时进 `createTab` / `bindActiveTab` / `syncActiveTab` 三处，否则跨 tab 串行）；`onclose`/`onerror` 的 `bindActiveTab` 加 `tabs.has` 守卫。 |
| `web/static/style.css` | `.message*` 家族去气泡；新增 `.tool-row*` 家族；`.tool-call-block` 由卡片改为行容器（**保留类名**，抽屉与浏览器测试都依赖）；`.message-reasoning*` 改单行；补 `--panel` / `--muted` / `--transcript-max-width` 定义；`@media (max-width: 600px)` 与 `720px` 两个既有断点内的 `.tab-messages` / `.message` 规则同步（注意 `.tab-messages` 在 `style.css` 内**重复定义两处**，后者生效，两处都要改）。 |
| `web/static/workflow_transcript.js` | `toolCallBlock()` 改用 `AsterwyndToolRows.createToolRow`；「参数已截断」提示移到**可见**的头部行（原先写在 `hidden` body 内，用户永远看不到）。 |
| `web/static/index.html` | 新增 `/static/tool_rows.js?v=1`；bump `style.css?v=21`、`chat.js?v=25`、`workflow_transcript.js?v=4`。**不动** wordmark 的 `?v=3`（`test_server.py` 逐字钉死）。 |
| `web/session.py` | `build_history_payload` 增补 `tool_call_id` 与 `tool_calls`（**仅 id/name**，不外发 `arguments`）；新增 `_history_tool_calls` 投影 helper。 |

**文件名取舍**：新模块最初叫 `transcript.js`，实测撞上既有浏览器测试的 URL 拦截 glob（`page.route` 的 `**/transcript*` 用于伪造后端 transcript 接口），静态资源会被一起拦下喂成 JSON，导致工作流抽屉整条渲染静默失败（`test_workflow_graph_browser.py` 由 28 绿变 3 红 + 7 error）。因此改名 `tool_rows.js`，命名空间语义保持（模块职责就是工具执行行的渲染）。

### 测试

- 新增 `tests/web_tests/test_transcript_js.py`：node + `vm` 纯函数测试（摘要生成逐工具族、**后端 canonical 失败前缀集**、结构化 Bash JSON、误报防线、截断、元数据单位、参数上限），沿用 `test_workflow_graph_js.py` 的 harness 写法并显式用 `utf-8` 解码子进程输出。
- 新增浏览器回归 `tests/web_tests/test_transcript_view_browser.py`（21 项）：用既有测试接缝 `window.AsterwyndChatTest.dispatch` 派发合成事件，断言 L0/L1/L2/L3/L4 + **配对顺序** + **run 结束收尾（含队列深度）** + **僵尸行不得认领下一轮结果** + **`/clear` 与 `session_history` 两条重绘路径清空未配对队列** + **行高恒定** + **结果 HTML 按纯文本** + **单列文档流** + **思维链折叠态单行高度**。
- **修改** `tests/web_tests/test_workflow_graph_browser.py`：抽屉的截断用例补一条 `inner_text` 可见性断言（原先只有 `text_content`，连 hidden 子树一起取，看不出「提示不可见」）。该文件因此不再属于「保持绿的既有断言」。
- 新增 `tests/web_tests/test_session.py::test_build_history_payload_projects_tool_calls_for_tool_rows`。
- 更新 `tests/web_tests/test_server.py::test_web_static_assets_include_session_and_run_display` 中随结构变化的源码字符串断言，**保持** `innerHTML` 与 `scrollHeight` 两条安全护栏的**意图**（改指向新函数），不放宽；并把该测试的 `read_text()` 显式设为 `utf-8`（缺省编码在 Windows 中文机器上是 GBK，含中文注释的静态资源会解不出来）。
- 保持绿的既有断言：`test_browser.py` 的 `.message.assistant` / `.message.system` / `.message-reasoning*`；`test_multi_session_browser.py` 的 `.message.user` 计数；`test_reconnect_pending_interaction_browser.py` 的重连卡片断言。

### 文档

- `README.md` / `README_EN.md`：Web UI 功能描述若提及聊天气泡形态，同步为 transcript 形态（关键词扫描后按事实更新）。
- `docs/architecture.md`：Web UI 小节补 `tool_rows.js` 与工具执行行折叠口径。
- `docs/openspec-change-backlog.md`：立项入队、归档出队（受保护路径，各需结构化事件）。

### process

- GitHub issue 无法在本机创建：`git fetch` 连续 6 次 `Failed to connect to github.com port 443` 超时（`origin/master` 仍等于本地 `master` = `3b48407`，未落后）。issue 创建 + 回填编号列为 `(post-merge)` 任务，proposal 与 tasks 均已如实记录。

### 边界与非目标

- **不**新增 WebSocket 事件字段（尤其不新增 `tool_call.id`）：那会动 `agent/loop.py` 两处事件发射点与 4 个测试文件，属于协议变更，与本 change「展示层」定位不符；配对改用到达顺序 FIFO + 同名优先，用合成事件测试锁住方向。
- **不**改 `agent/tool_result_display.py` 阈值（`4000` / `80` / `1200`）：折叠行不再消费 `preview`，但 `display` 契约与既有测试保持逐字不变。
- **不**引入构建步骤或前端框架。
- **不**做连续工具调用的组头（见 RQ4）。
- **不**做暗/亮主题切换（本仓 `style.css` 只有单一 `:root`，是既有事实，不在本 change 扩大范围）。
