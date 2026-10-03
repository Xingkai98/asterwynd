# Design: harness 式 Web transcript（正文成文 + 工具执行单行折叠）

## Context

### 现状机制（逐条实测，file:line 为准）

1. **消息区是 flex 单列，所有条目平铺 append**。`web/static/style.css` 的 `.tab-messages` 定义成 `display:flex; flex-direction:column; gap:12px; padding:20px`（文件内**重复定义两处**，后者生效）。`.message.user/.assistant/.tool/.system` 用 `align-self` + `background` + `border-radius:12px` + `max-width:85%` 做出气泡。
2. **工具调用的两块是分开的、且都默认全展开**：
   - `chat.js::addToolCallBlock` 无条件 append `<div class="tool-call-block"><span class="tool-name">🔧 name</span><pre>JSON.stringify(args, null, 2)</pre></div>` 到 `messagesEl`。
   - `chat.js::addToolResultMessage` append `<div class="message tool">`，body 文本 = `display.collapsed ? display.preview : fullResult`——**collapsed 时把 1200 字符预览直接铺在时间线上**；仅 `display.collapsed` 为真时才给一个 `Expand` 按钮。
3. **display policy 的阈值**：`agent/tool_result_display.py` `max_result_chars=4000`、`max_result_lines=80`、`preview_chars=1200`、`DEFAULT_COLLAPSED_TOOLS=("WebFetch",)`；判定 `collapsed = tool in DEFAULT_COLLAPSED_TOOLS or char_count > 4000 or line_count > 80`。**短结果的 `collapsed` 为 false**，于是 `preview == 全文`，整段结果照样进对话流——这是「刷屏」的主因：折叠策略只对长结果生效，且「折叠」也只是把 5000 字符换成 1200 字符。
4. **事件不带调用 id**：`agent/loop.py` 的 `tool_call` = `{name, arguments, approval?}`；`tool_result` = `{name, result, display}`。唯一带 id 的是 `llm_response.data.tool_calls[].id` 与 `approval_request.data.tool_call_id`。同一 session 的全部事件走同一条 `asyncio.Queue`，**到达顺序可靠**；两处发射点都成对相邻（参数解析失败路径在 phase 1 提前发射，正常路径在 phase 3 按「original order」回放）。
5. **历史回放会降级**：`web/session.py::build_history_payload` 原先只发 `{role, content, reasoning}`；`Message` 有 `tool_call_id` 与 `tool_calls` 但**没有工具名字段**。`chat.js::renderHistory` 把非 assistant 一律折成 `user`，于是重连后所有 `role:"tool"` 的历史消息变成**巨大的 user 泡泡**（G3）。
6. **`currentAssistantMsg` 存的是 `.message-body`**，`reasoning_delta` 靠 `currentAssistantMsg.closest('.message')` 反查外壳；`ensureReasoningArea` 用 `messageEl.insertBefore(area, messageEl.firstChild)`。这两个是**硬结构假设**。
7. **`.tool-call-block` 是共享样式面**：`workflow_transcript.js` 手搓同一组类名（注释写明「与主 chat 的 `addToolCallBlock` 同口径」），浏览器测试在抽屉里断言它。
8. **单主题**：`style.css` 只有 `:root` 一处主题定义，无 `prefers-color-scheme` / `data-theme`。另 `--panel` 与 `--muted` 被引用但从未定义（既有缺陷）。

### 参考实现（`D:\code\deepseek-harness`，本地 clone 可用）

`packages/client/ui-tool/src/client/tool/components/ToolRow.tsx` + `ToolRow.module.css` 是折叠行的权威实现：固定 24px 单行 `[16 图标] gap6 [title] gap8 [2×2 圆点] gap8 [summary FILL 截断]`；`bodyRaw` 注释明确「**only while the row is expanded**」；失败态 `failureLine` 用结果首行替换摘要并上错误色且**不自动展开**；`stateStatus()` 给读屏补视觉隐藏的状态文案。对话正文侧不套卡片，消息与工具行是**同一列的兄弟节点**。详细对照与逐条取舍见 proposal 的 `## Reference Implementation Research` 与本文件末尾的 `## 参考实现对照与偏离记录`。

### 缺口

| 缺口 | 现状 | 目标 |
|------|------|------|
| G1 结果预览铺满时间线 | 1200 字符预览 inline | 折叠态**可见文本**零结果正文 |
| G2 参数默认全展开 | `<pre>` 无条件 append | 展开才格式化 |
| G3 重连把工具输出渲染成 user 泡泡 | `chat.js::renderHistory` | 折叠工具行（且带真名） |
| G4 调用与结果两块分离 | `.tool-call-block` + `.message.tool` | 合成一行 |
| G5 抽屉与对话口径漂移 | 两处手搓同类名 | 共用 `AsterwyndToolRows` |

## Goals / Non-Goals

**Goals**

- 对话区读起来是**一份文档**：assistant 正文是主角，工具执行退成可展开的脚注行。
- 一条工具执行**永远只占一行**，行高不随参数/结果长度变化。
- 失败信息**在折叠行上就能看见**（因由 + 错误色），不靠展开，且不自动展开。
- 对话区与工作流抽屉共用同一套行渲染，不再有两份口径。
- 零构建、零新依赖、零 WebSocket 事件契约变更。
- 折叠行是**可被 node 单测的纯函数产物**（摘要生成与 DOM 构建分离）。

**Non-Goals**

- 不做连续工具调用的组头（「运行了 5 个命令」）——本仓事件无 id，归组只能靠顺序推断，收益不抵合并错行风险（proposal RQ4）。
- 不新增 `tool_call.id` / `tool_result.status` / `duration_ms` 等**事件**字段（属 `agent/loop.py` 事件契约变更，另开 change）。注意：`session_history` 载荷的两个字段属于历史投影补充，已在本 change 内（D6）。
- 不做 diff / stdout / 语法高亮等专用结果卡片（DSH 的 `DiffBlock`/`TerminalBlock`/`ReadBlock` 家族）。本 change 展开后是「参数 JSON + 结果纯文本」两段。
- 不做暗/亮主题、不做字号轴、不做 `TextShimmer` 动效。
- 不改 `agent/tool_result_display.py` 的任何阈值或 `display` 字段语义。

## Decisions

### D1 保留 `.message` 语义类名与 DOM 骨架，只改视觉与工具行渲染；**不引入 turn 包装层**

- `addMessage` 仍产出 `<div class="message {role}">`，assistant 仍带 `.message-body.markdown-body`，reasoning 区仍是 `.message` 的子节点。
- 理由：三个硬结构假设都挂在 `.message` 上（Context 6），四个浏览器测试文件按 `.message.user` / `.message.assistant` / `.message.system` / `.message-reasoning*` 选择器断言。参考实现的正文侧同样是「消息与工具行同列兄弟」（Context 参考实现），**不需要**包装层即可达成目标观感。
- 被否方案：引入 `.turn` 包一层。代价是每个 append 点都要改归属、`appendAssistantContent` 的 `innerHTML` 整体重写会作废容器内引用、并且要重写 4 个浏览器测试；收益只是「语义更好看」。
- 实测补强（grill）：工具行始终 append 到 `messagesEl`，`appendAssistantContent` 的 `innerHTML` 重写只作用于传入的 `.message-body`，两者不共享子树，所以「工具行被 innerHTML 摧毁/重复」不可达。

### D2 新增 `web/static/tool_rows.js`（`window.AsterwyndToolRows`），对话区与抽屉共用

- 导出（与实现逐字一致）：纯函数 `firstLine` / `truncate` / `compactJson` / `toolTitle` / `summarizeToolCall` / `summarizeToolResult` / `formatCharMeta` / `formatBodyText` / `prettyArgs`；DOM 构建 `createToolRow(doc, spec)` / `updateToolRow(doc, row, spec)`；常量 `SUMMARY_LIMIT` / `ERROR_LIMIT` / `BODY_LIMIT` / `BODY_TRUNCATED_NOTE` / `TOOL_TITLES`。
- 理由：(a) 本仓已有 node + `vm` 跑前端纯函数的成熟写法（`tests/web_tests/test_workflow_graph_js.py`），把摘要逻辑做成纯函数就能进单测；(b) 消除 G5 的口径漂移；(c) DOM 构建放在 `chat.js` 之外，`chat.js` 的 `innerHTML` 安全护栏切片天然继续成立。
- 被否方案：把行渲染留在 `chat.js`，抽屉继续手搓。代价是两份口径，且 `chat.js` 里要新增 DOM 字符串拼接才能省代码，会撞 `innerHTML` 护栏。
- **文件名不含 `transcript` 字样**（实测踩坑）：既有浏览器测试用 `page.route` 的 `**/transcript*` glob 伪造后端 transcript 接口；模块原叫 `transcript.js` 时被同一 glob 拦下喂成 JSON，`window.AsterwyndToolRows` 因此 undefined，抽屉渲染整条静默失败（`test_workflow_graph_browser.py` 28 绿 → 3 红 + 7 error）。改名后恢复全绿。

### D3 折叠行 = `▸ Bash · pytest -q · 1.2k 字符`；**折叠态不渲染参数与结果的任何可见文本**

- 行结构：`<button class="tool-row-head" aria-expanded="false">` 内 `[caret] [title=tool-name] [圆点分隔] [summary 可截断] [note] [meta 不换行]`；body 为 `<div class="tool-row-body" hidden>`，参数与结果全文写在里面（展开才可见）。
- 摘要生成按工具族取「最能定位这次调用」的字段，取不到回退压缩 JSON。
- 理由：这是 G1 的根治手段，直接对应参考实现 `bodyRaw` 的「only while expanded」口径。
- 被否方案：折叠态保留一行截断的**结果**预览（例如首行 120 字符）。看起来「信息更多」，但结果正文长度不可控，正是刷屏来源；结果摘要只在**没有配对调用**的行（历史回放兜底）上作为摘要出现。
- 措辞订正（grill）：准确说法是「折叠态**可见文本**零结果正文」；DOM 里仍持有全文（受 `BODY_LIMIT` 约束），所以「折叠态零成本」不成立，成本分析见 `## Risks / Trade-offs` R7/R10。

### D4 失败态：可读首行顶到折叠摘要、错误色、**不自动展开**；结构化结果保留参数摘要

- `summarizeToolResult` 返回 `{state, summary, code, structured}`。失败判定**一律锚定行首**，前缀集对齐后端 canonical 错误通道：`[Exit N]` / `[Timeout` / `[OOM` / `[Error` / `[Permission denied` / `[Approval denied` / `[Approval unavailable` / `[Approval required` / `[MCP tool error` / `Error` / `Traceback` / `exit code N` / `exit status N` / `command failed`；另有结构化 JSON 判决（`exit_code != 0` / `timed_out` / `oom_killed` / `status ∈ {failed,error,cancelled,killed}`）。
- 折叠行表现：**可读**失败首行（非 JSON 信封）顶到摘要 + 错误色；**结构化**失败（Bash 的单行 JSON）**保留参数摘要**，把 `exit 1` / `timeout` 放行尾 meta；两者都不自动展开。
- 理由：参考实现 `failureLine` 同款；失败是最吵的场景，自动展开等于把刷屏还回来。
- 订正（grill 证伪初版）：初版的失败前缀集**漏掉了后端自己的 canonical 前缀**（`[Error` / `[Permission denied` / `[Approval denied` / `[MCP tool error`），导致审批被拒、权限拒绝这些最常见的失败显示为成功——L4 在主路径上是假绿。另初版有一条未锚定的 `failed with exit…` 模式，会把「Grep 命中的源码行里含该字样」的**成功**搜索标红。两条均已修。
- 被否方案：失败自动展开。

### D5 调用/结果按**到达顺序 FIFO + 同名优先**配对；`done`/`error` 收尾；不新增协议字段

- per-tab 维护 `pendingToolRows`（数组，元素 `{name, row}`）。`tool_call` push；`tool_result` 先在同名未配对项里取**最早**一个，取不到再取队首；都没有则**新建一行**兜底。
- 方向取舍（grill 提出改「取最近」，**不采纳**，理由如下）：同一轮里同名多次调用时 `tool_call`/`tool_result` 成对相邻、按原顺序发射（phase 3「original order」），取最近会把第 1 个调用的结果贴到最后一个同名行上——这正是「正常场景」而不是例外。grill 描述的错配场景（僵尸行跨轮残留）由**清队列**解决，而不是改配对方向。
- 收尾：`done` / `error` 到达时把剩余未配对行标成失败 + `未返回结果` 并清空队列；`session_history` 与 `/clear` 也清空（DOM 已整体重绘，行引用失效）。
- 理由：Context 4 已确证单队列到达顺序可靠，两处发射点都成对相邻；兜底新建保证**永不丢事件**。
- 被否方案：给 `tool_call`/`tool_result` 加 `id`。会动 `agent/loop.py` 两处发射点与四个测试文件，把「展示层 change」变成「协议 change」，超范围。

### D6 `renderHistory` 把 `role: "tool"` 渲染为折叠行，并靠 `session_history` 的 `tool_call_id`/`tool_calls` 拿回真名

- 后端 `build_history_payload` 增补 `tool_call_id`（每条消息）与 `tool_calls`（仅 `{id, name}`，**不外发 `arguments`**）；前端先建 `id → call` 表，再按 `tool_call_id` 反查标题与参数摘要。
- 拿不到时降级为通用标题「工具结果」+ 结果首行摘要（不抛错、不丢行）。
- 理由：G3 是「重连后更刷屏」的直接原因；同时 12 行一模一样的「工具结果」无法分辨是哪次调用。
- 订正（grill 证伪初版）：初版把「拿回工具名」列为 Non-Goal，理由是「要给 `Message` 加字段并穿透三个 provider」。实测 `Message` 已带 `tool_call_id`（`agent/message.py`）与 `tool_calls`，成本只是 `web/session.py` 一处载荷投影 + 前端一张表，**不是**协议改造。改为在本 change 内实现。

### D7 思考链折叠区改为同款单行，**保留 `.message-reasoning*` 类名与 `aria-expanded` 驱动**

- 结构不变（`ensureReasoningArea` 的 insertBefore 位置不变），只把外壳从「带边框整块」改为「单行 + 展开正文」；caret 仍由 `[aria-expanded="true"]::before` 驱动。
- 理由：浏览器测试直接点击 `.message-reasoning-toggle` 并断言 `.message-reasoning-content` 的 hidden 与文本，改类名是无谓的破坏。

### D8 展开时**保留**头部行

- 展开后 `tool-row-head` 仍在最上方（caret 转 `▾`），下面接 body。body 是 head 的**兄弟节点**，所以在 body 里点选文本不会触发折叠。
- 理由：防止「展开后不知道点的是哪一行」；参考实现的 `DisclosureRow` 也是 `keepContentWhenOpen`。

### D9 连续工具行共享左侧导轨，**不做组头**

- 每行自带 2px 左导轨 + 左内边距，相邻行之间留 3px 间距。
- 措辞订正（grill）：这是**分段导轨**（每行一段、彼此不连通），不是「连成一条连续导轨」。要连成一条需要额外做相邻行收口（`margin-top: 0` 之类），本 change 不做——收益（视觉连续性）不抵「行与行之间失去呼吸感」的代价，且当前形态已经能读出「这是一组工具执行」。
- 理由：零额外状态、零合并错行风险，就能把「一轮里连着调了 6 次工具」读成一段。

### D10 工具行外壳**保留** `.tool-call-block` 类名

- 新行 = `<div class="tool-call-block tool-row" data-state=… data-tool=…>`；标题 span 带 `tool-row-title tool-name`。
- 理由：`workflow_transcript.js` 与抽屉的浏览器断言依赖该类名；保留它让既有断言继续有意义（它们断言的是「抽屉里能看到工具名与参数」，与视觉无关）。
- 订正（grill）：抽屉侧此前不传 `state`，会落到默认 `data-state="running"`；已把 `createToolRow` 的默认值改为 `ok`（运行中由调用方显式传），避免历史行被标成「运行中」。

### D11 缓存击穿串与加载位置

- `index.html` 在 `markdown.js` 之后插入 `/static/tool_rows.js?v=1`（两个消费者之前）；bump `style.css?v=21`、`chat.js?v=25`、`workflow_transcript.js?v=4`；**不动** `/assets/asterwynd-web-wordmark.png?v=3`（`test_server.py` 逐字断言）。
- 理由订正（grill）：两个消费者都是**运行时**读 `window.AsterwyndToolRows`，脚本标签全是同步加载，所以「必须排在两者之前」并没有因果必要性——真正必要的是「必须被加载」。测试断言相应改为「被引用」，并保留既有 `markdown.js < chat.js` 那条顺序断言；不在本 change 里新增假的顺序断言。

### D12 源码字符串断言的更新原则：**保留意图，改指向**

- `test_server.py` 里随结构变化的断言（`tool-result-toggle`、`toggle.addEventListener` 切片）改写为对新结构的等价断言；`innerHTML` 与 `scrollHeight` 两条护栏的**意图**原样保留。
- 订正（grill）：初版把 `assert "body.textContent" in tool_result_renderer` 换成 `assert "textContent" in tool_rows`——后者几乎恒真（文件里多处 `textContent`），属**弱化**。现改为点名 `resultPre.textContent`（真正写结果正文的那一行）。
- `scrollHeight` 护栏从窄切片升级为**整个 `tool_rows.js`**（覆盖面更宽，意图不变：折叠切换不得滚动）。

## 参考实现对照与偏离记录

补调研（`ui-conversation` / `ui-chat` / `ui-primitives` 全量读完后）发现三处与初版设想不同的事实，逐条记录**采纳 / 偏离**及理由：

| 事实 | 本 change 取舍 | 理由 |
|---|---|---|
| DSH 的 **user 轮确实是右对齐泡泡**：`MessageItem.tsx::UserStyleBubble` → `.bubble { border-radius: 20px; padding: 10px 16px; max-width: min(70.2%, 82%) }`，靠对齐 + 底色承载角色，**没有**头像/`You` 标签/左导轨 | **偏离**：本仓 user 轮改为整列宽输入块（左强调条 + `你` 微标签），不做右对齐圆角 | 用户诉求原话是「现在 web 界面还是对话的泡泡那种形式……搞成业界 harness 的 web 展示形式」——保留右对齐圆角泡泡会让整体观感仍然是聊天窗。assistant 侧无泡泡与工具行折叠这两条**完全采纳**，它们才是「harness 观感」的主体 |
| DSH **有**连续工具调用归组（组头 `Ran commands` / `Read files, ran commands, searched code`，**不带数量**） | **偏离**：不做组头，只做分段导轨（D9） | (a) 用户诉求是「工具执行都**默认只展示一行**」——按次一行是字面要求；(b) DSH 归组依赖每个调用有稳定 id 与可合并父节点，本仓事件无 id，合并错行风险大于「少几行」的收益 |
| DSH 折叠行的展开体是**头部行的兄弟节点**，且 `keepContentWhenOpen` 让折叠摘要**展开后仍在**；展开体统一缩进 22px（= leading 16 + gap 6，对齐到标题文字） | **采纳**（D8） | 三条都是「不改变 DOM 语义就能拿到的正确性」：兄弟节点让展开体里的点击不会误触折叠；保留头部给出锚点；缩进让层级一眼可读 |
| DSH **没有**「失败自动展开」，失败只是把 `errorSummary = firstLine(output)` 顶上折叠摘要并转红 | **采纳**（D4） | 失败是最吵的场景，自动展开等于把刷屏还回来 |
| DSH 的 `bash` 专属修正 `terminalFailed()`：退出码非 0 的行**即使 `isError === false`** 也判 `error` | **采纳并推广**（D4） | 否则「命令失败了」只有展开才看得见，与 L4 验收冲突；本仓推广到结构化 JSON 结果（`exit_code`/`timed_out`/`oom_killed`） |
| DSH 折叠摘要**没有字符预算**，截断靠 `firstLine` + CSS `text-overflow: ellipsis` | **部分采纳**：CSS 截断照做；纯函数仍返回**截断后的字符串**（默认 80 字符） | 本仓有 node 纯函数测试，字符串本身可断言才测得到「不会无限增长」；CSS 截断在无头测试里不可观测 |
| DSH 折叠行标题是动词词组（`Read` / `Grep` / `Bash` / `Write` / `Edit` / `Fetch`…），未知工具标题为 `Tool call` 且摘要前缀线名 | **采纳**：标题表映射到本仓工具名，未知工具标题 = 线名本身 | 线名本身就是英文动词，中文标题反而与工具名脱节 |

## Pre-Implementation Review

设计追问由**独立零记忆 subagent** 执行（`/grill` 等价流程），产出 `openspec/changes/harness-style-web-transcript/reviews/grill-design.md`：12 条 `- **决策**:` 逐条对照源码核验、6 条 Open Questions（每条配具体例子）、以及 4 条 MUST-FIX。本设计的最终形态已按该文件订正，逐条落点如下：

| grill 结论 | 落点 |
|---|---|
| R-A/Q1 失败前缀集漏掉后端 canonical 通道（L4 假绿） | D4 重写前缀集 + 收紧未锚定模式；`test_transcript_js.py` 新增 `[Error`/`[Permission denied`/`[Approval denied`/`[Approval unavailable`/`[MCP tool error` 用例与「成功结果含失败字样不得误报」用例 |
| Q2 结构化失败覆盖命令 | D4 改为「结构化失败保留参数摘要 + 因由进行尾 meta」；浏览器 L4 改用真实 Bash JSON 形态 |
| Q3 args 无上限 + 截断提示不可见 | `prettyArgs` 走同一条 `BODY_LIMIT`；`note` 移到头部行；新增可见性断言 |
| Q4 pending 行跨轮残留 | D5 增 `settleOrphanToolRows`；新增配对顺序与 run 结束收尾的浏览器回归 |
| Q5 L2 预算 4000 过松 | 收紧到 1200 + 每行摘要结构断言；proposal 的对照口径订正为实测 ~24000 |
| Q6 历史工具名成本被高估 | D6 改为在本 change 内实现（`session_history` 增补投影） |
| D2/D9/D11/D12 表述与实现不符 | 逐条订正（导出清单、分段导轨、顺序因果、`resultPre.textContent` 锚点） |
| R-I 流程：实现先于 grill 完成 | 如实记录：本 change 的实现早于 grill 产出（同一会话内），grill 的 4 条 MUST-FIX 已全部回改实现与测试，Open Questions 逐条处理后写入 `## User Confirmation` |

## Risks / Trade-offs

| 编号 | 风险 | 严重度 | 缓解 |
|------|------|--------|------|
| R1 | 配对在同轮「解析失败 + 同名正常调用」时可能张冠李戴 | 低 | 同名优先取最早未配对项；兜底新建保证不丢事件；`done`/`error` 清队列消除跨轮僵尸；已用合成事件回归锁住配对方向 |
| R2 | 折叠态不渲染结果文本，用户可能觉得「看不到输出了」 | 中 | 行上有字符数/行数 meta 与 caret 提示可展开；失败因由直接上折叠行；L1/L2 两条验收分别锁「展开可用」与「不刷屏」 |
| R3 | 历史行拿不到工具名时只能叫「工具结果」 | 低 | 已在 D6 内解决主路径（`tool_call_id` 反查）；拿不到时降级为通用标题 + 结果首行摘要，不算错误路径 |
| R4 | 去气泡后 user 轮与 assistant 轮区分度下降 | 中 | user 轮保留整列宽输入块（左强调条 + `你` 微标签）；system 居中细线；error 错误色边框 |
| R5 | `.tab-messages` 在 `style.css` 里重复定义两处，只改一处会静默不生效 | 中 | 两处同步修改，并在 tasks 里列为独立检查项 |
| R6 | `--panel` / `--muted` 未定义，审批/提问卡静默失效 | 低 | 本 change 补上定义（小、可测、同属对话区视觉） |
| R7 | 大结果的 DOM 成本：`result` 服务端无上限，前端把全文写进 hidden body（上限 200000 字符） | 中 | 结果与参数**共用**同一条 `BODY_LIMIT` + 截断提示；`error` 行的 meta 仍报真实 `char_count`。真正的放大器是重连时 `renderHistory` 一次性渲染全部历史工具行——已按 `BODY_LIMIT` 截断每条，但仍应作为后续优化项（惰性渲染） |
| R8 | 更新 `test_server.py` 源码断言被审阅视为「改测试迁就实现」 | 中 | D12 明写原则：只改锚点不改意图；两条安全护栏必须仍然存在且指向新函数；新增的 `resultPre.textContent` 断言点名具体行而非恒真 |
| R9 | 多文件零构建前端的缓存组合风险：旧 `index.html` + 新 `chat.js` 会让 `window.AsterwyndToolRows` 为 undefined | 低-中 | `?v=N` 击穿串全部 bump；新模块加载失败时 `transcriptApi()` 的调用点会抛错并被 `handleEvent` 的调用方吞掉——已记录为已知边界而非静默降级设计（未做运行时兜底，避免掩盖接线错误） |
| R10 | `formatCharMeta` 的大数单位可读性 | 低 | ≥1e6 用 `M` 单位（避免 `1048.6k 字符`） |

## Testing Strategy

### 分层

1. **纯函数单测（node + vm）** — `tests/web_tests/test_transcript_js.py`：
   - `summarizeToolCall` 逐工具族（读/搜/shell/写/未知/空参数/参数非对象/超长值截断/TodoWrite 两态）；
   - `summarizeToolResult`（后端 canonical 前缀集逐条、结构化 Bash JSON、超时 JSON、非零退出码文本形态、**成功结果含失败字样不得误报**）；
   - `formatCharMeta`（字符数/行数、单行不加行数、`M` 单位）；
   - `prettyArgs`（缩进 JSON、注入小上限验证截断路径——真上限 200000 无法走命令行传入 node harness）；
   - 健壮性：`null` / 字符串 / 非对象参数不得抛异常。
2. **源码接线断言** — `test_server.py::test_web_static_assets_include_session_and_run_display`：`tool_rows.js` 被引用且位于 `chat.js` 之前；新结构的等价断言；`innerHTML` / `scrollHeight` 护栏改锚点后仍有效；`read_text(encoding="utf-8")`。
3. **浏览器行为回归（Playwright，无需 LLM）** — `tests/web_tests/test_transcript_view_browser.py`（21 项）：L0 折叠（含**可见文本 < 1200 + 每行摘要 ≤ 90 的结构断言**）、L1 展开/收起/展开体内点击、配对顺序、结果先到兜底、run 结束收尾（含**队列深度**断言）与**僵尸行不得认领下一轮结果**、**`/clear` 与 `session_history` 两条重绘路径清空队列**、失败（结构化 JSON / 可读首行 / `TaskOutput` 多行 / 浏览器族前缀）、成功摘要保真、L3 历史（含工具名反查与摘要降级）、参数缩进 JSON、**行高恒定**、**结果 HTML 按纯文本**、**单列文档流**、**思维链折叠态单行高度**。
4. **既有浏览器测试保持绿** — `test_browser.py`（`.message.assistant`、`.message-reasoning*`）、`test_multi_session_browser.py`（`.message.user` 计数）、`test_reconnect_pending_interaction_browser.py`；`test_workflow_graph_browser.py`（抽屉 `.tool-call-block`）**由本 change 修改**（新增截断提示可见性断言），不再是「保持绿的既有断言」。
5. **载荷单测** — `test_session.py` 新增历史投影断言（`tool_calls` 只含 id/name、`tool_call_id` 透传、无调用时为 `None`）。
6. **全量** `uv run pytest -q` 并与 pristine baseline 对照失败集；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`；`scripts/check_openspec_artifacts.py`。

### 测试先行顺序

先写 `test_transcript_js.py`（红）→ 写 `tool_rows.js` 使其转绿 → 写浏览器回归（红）→ 改 `chat.js`/`style.css`/`workflow_transcript.js`/`index.html`/`web/session.py` → 修 `test_server.py` 锚点 → 全量。

### 变异验证（每条新测试至少做一次，改坏实现必须变红）

已实测 5 条，逐条变红后还原：
- `createToolRow` 的 body 默认不 hidden → L0 变红；
- 折叠行摘要换成结果预览 → L0/L2 变红；
- `summarizeToolResult` 永不判失败 → 失败相关 node 用例变红；
- `renderHistory` 的 `role:"tool"` 分支去掉 → L3 变红；
- 配对改取最近（`lastIndexOf`）→ 配对顺序回归变红。
