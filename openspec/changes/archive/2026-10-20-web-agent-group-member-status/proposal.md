# Proposal: 群聊成员运行状态栏（真实事件驱动的 per-member 状态）

关联 issue：[#307](https://github.com/Xingkai98/asterwynd/issues/307)（本 change 的跟踪入口）。
前置交付：`web-agent-group-chat`（群聊编排、房间级 WS、成员 `speaking` 高亮）与 issue #302。
前置调研：issue #307 的 2026-10-20 调研 comment（事件面、钩子、状态映射、缺口、代价、UI 建议；
本 change 的所有「现状」事实均在该 comment 中附 `文件:行号`，并在下文重新抽列关键证据）。

## Change Type

- primary: feature
- secondary: []

## Why

用户发送一条群消息后，成员从被轮到到真正发言之间的 LLM 调用、工具执行、记忆压缩等阶段在界面上
**完全静默**：现状房间级 WS 只有 7 种编排器事件，核心是 `member_speaking` + 四种回合终态
（`agent/team/orchestrator.py:440-442`、`:449-474`、`:378-382`）。成员会话内部其实已经产生
`run_started` / `reasoning_delta` / `assistant_delta` / `assistant_stream_complete` / `done`
与 `before_iteration` / `before_tool_execute` / `after_tool_execute` 钩子
（`agent/loop.py:758-762`、`:1272-1309`、`:790`、`:1417`、`:1447`；
`agent/hooks/manager.py:16-27`），但群聊 runner 是无连接驱动
（`web/session.py:2178-2228` 调用 `manager.run_session(session, message)` 时不传句柄），
这些事件被 `SessionEventChannel.broadcast` 在没有订阅者时直接丢弃（`web/session.py:420-437`）。

用户已拍板：不做时间线里的小动效，而是像真实聊天室一样，在**左侧**加 per-member 状态栏，实时显示
**空闲 / 正在思考 / 正在输入 / 正在使用工具（带工具名）/ 运行中（兜底）**。状态必须由真实事件驱动，
禁止定时器伪造；移动端必须专门处理（现状群聊 CSS 位于最后一条 `@media (max-width: 720px)`
之后，`web/static/style.css:2064`、`:2096-2136`，390px 视口下 260px 侧栏 + 间距后主区仅约 100px）。

## What Changes

1. **状态模型**：新增 per-member 五档状态 `idle | running | thinking | typing | tool`，优先级
   `tool > typing > thinking > running > idle`；`tool` 维护在途工具集合（支持并发/同名工具聚合）；
   终态事件权威重置；轮次 `finally` 无条件清空；重连用 `room_state` 快照恢复。
2. **后端事件面**：把成员 run 的 AgentLoop 事件与钩子接成状态 reducer 的输入；新增房间级
   `member_status` 事件（只在状态变化时发；携带**完整非空闲状态表** + 房间级单调 `status_seq`；
   短窗口内允许合并）。**不转发** `assistant_delta` / `reasoning_delta` 的 token 内容。
   事件为新增类型/新增字段，对旧前端向后兼容。
3. **补终态缺口与防御性契约**：
   - `ensure_room_session` 失败（`agent/team/orchestrator.py:415-423`）补发
     `member_failed`（含成员名）；
   - 轮次取消/意外异常（`:361-362` 的 `finally` 只 pop）补发
     `round_ended(termination=cancelled|error)`，并在任何 await 之前同步清空状态；
   - 空产出回合：生产 `WebSessionRunner` 已把空文本归一为 silent（`web/session.py:2226-2227`），
     编排器 `:475-477` 的分支只对自定义 runner 可达；本 change 在编排器层补防御性
     `member_silent` 契约，不把它当用户可见 bug；
   - `room_state` 增加 `member_statuses` + `status_seq` 快照，并修正「先订阅后发快照」的
     发送顺序窗口（`web/server.py:651-661`）与握手失败未 unsubscribe 的问题。
4. **前端**：左侧成员状态栏（桌面第三列）+ 独立的 `renderMemberPresence()`（不重绘时间线）；
   独立纯函数模块承载 reducer 以便 node 单测；旧服务端降级；移动端按 design 的候选形态处理，
   同时修复群聊视图现有的移动端挤压。
5. **测试**：纯函数 reducer 单测 + 编排器/WS 集成测试 + 浏览器 smoke（桌面与 390px）；
   用 `ScriptedLLM`（`tests/support/llm_harness.py:27`）与假 runner 覆盖，无需真实 provider。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：新增「成员运行状态可观测性」与「房间级状态快照与重连」两条
  Requirement，并 MODIFIED「房间级互斥与轮次终止」以明确 teardown 的 `round_ended`
  （`cancelled` / `error`）不是新增轮次出口；不改既有「同一时刻至多一个成员发言」
  （`openspec/specs/multi-agent-collaboration/spec.md:1267`）的语义。
- `web-ui`：新增「群聊成员状态栏」Requirement（per-member 展示、事件驱动、移动端可用、
  重连快照、旧服务端降级、可访问性）。

## 需求

1. **五档状态**：每个成员 SHALL 有独立状态，取值 `idle`（空闲）/ `running`（运行中）/
   `thinking`（正在思考）/ `typing`（正在输入）/ `tool`（正在使用工具）。状态 SHALL 只由真实运行
   事件驱动，SHALL NOT 由定时器推进、推断或伪造。
2. **优先级与回落**：优先级 SHALL 为 `tool > typing > thinking > running > idle`；工具执行中
   即使此前有流式文本也 SHALL 显示工具；工具结束后回落 `running`，下一次 LLM 调用开始转
   `thinking`；流式增量 SHALL 把 `thinking` 升为 `typing`。
3. **工具聚合**：`tool` 状态 SHALL 维护在途工具集合，支持并发工具与同名工具；展示 SHALL 带
   工具名（一个显示名称，多个显示名称列表与数量）。
4. **序列表述**：`member_status` SHALL 携带房间级单调 `status_seq` 与当前完整非空闲状态表；
   短窗口内的多次变化 MAY 合并为一次携带最新状态的 `member_status`，最终状态 SHALL 与快照一致。
5. **终态权威重置**：`member_post` / `member_silent` / `member_failed` / `round_ended` SHALL
   把对应成员（或全房间）重置为 `idle`；终态事件 SHALL 携带**重置后**的 `status_seq`，客户端
   SHALL 丢弃比已应用序号更旧的 `member_status` 与终态事件；`member_failed` SHALL 带成员名。
6. **轮次 teardown**：轮次 `finally` SHALL 在任何 await 之前同步清空该房间的全部成员状态并
   递增序号；取消/断线/意外异常导致的 teardown SHALL 尽力发送
   `round_ended`（`termination = "cancelled" | "error"`），不写房间日志、不产生 `RoundResult`。
7. **快照与重连**：`room_state` SHALL 携带当前轮次的 `member_statuses` 与 `status_seq`；
   重连/第二标签页 SHALL 不等待下一次状态变化即可恢复；快照缺失的成员 SHALL 视为 `idle`；
   `round_active = false` 时 SHALL 全部视为 `idle`；新连接的快照 SHALL 重置客户端序号水位
   （服务端重启后序号变小也必须接受）。
8. **不转发增量**：token 级 `assistant_delta` / `reasoning_delta` SHALL NOT 转发到房间 WS；
   状态 reducer 只消费「首个增量」信号。
9. **不可观测不假装**：非流式 provider SHALL NOT 进入 `typing`；子 agent/workflow 内部阶段、
   预拒绝工具的开始、用户打断 SHALL NOT 被表示为虚假状态。
10. **前端**：桌面 SHALL 在群聊布局左侧（时间线左侧）展示 per-member 状态栏；状态更新 SHALL
    NOT 触发时间线整体重绘或打断滚动；群公告 SHALL 在状态栏取代成员 chip 后仍可见；移动端
    （≤720px）SHALL 在不挤压时间线的形态下展示状态，390px 视口下主区 SHALL 可用；旧服务端无
    `member_status` 时 SHALL 降级为 `member_speaking` 显示运行中、终态事件回空闲。
11. **可访问性**：状态 SHALL 以文字表达，SHALL NOT 只靠颜色区分；`aria-live` SHALL 使用独立
    区域且只在状态变化时播报单条文案；动效 SHALL 尊重 `prefers-reduced-motion`。

## Non-Goals

- **不做真正的多成员并发**：当前 `_drive` 严格串行（`agent/team/orchestrator.py:393-399`），
  规格钉死同一时刻至多一个成员发言（`openspec/specs/multi-agent-collaboration/spec.md:1267`）。
  本 change 的 per-member 模型为未来并发留出接口，但同一时刻仍至多一个成员非空闲；真正的并发
  是编排语义变更，另立 change。**该解释作为 Open Question Q3 交用户确认**（issue #307 原文用了
  「多成员并发」），确认前不写实现。
- **不做用户打断/轮次取消出口**：房间 WS 只处理 `chat` / `ping`，规格明确首版不提供轮次取消
  （`web/server.py:678-690`、`spec.md:1304`）。本 change 只为既有「断线取消整轮」补状态 teardown，
  不新增取消协议。
- **不展示子 agent/workflow 内部阶段**：成员调用 `StartWorkflow` / 子 agent 时，父会话只能看到
  外层工具调用（整个子图期间显示「正在使用工具 StartWorkflow」）；内部 LLM/工具事件不回流，
  不假装可细分。
- **非流式时不显示「正在输入」**：无 `assistant_delta`（`agent/loop.py:1389-1395`、
  `agent/llm.py:98`），状态停在 `thinking` 直到下一次真实信号；不伪造。
- **不转发 token 增量**：只发状态变化，避免刷屏与多订阅者带宽放大。
- **不持久化状态**：状态是进程内存中的运行期投影；进程重启后按空闲，重连只依赖内存快照与
  `round_active`。
- **不改变既有事件字段与语义**：`member_speaking` / `member_post` / `member_silent` /
  `member_failed` / `round_ended` 只增不改（新增 `status_seq` 等附加字段、新增
  `termination=cancelled` 值）；不写房间日志、不影响记忆 review 与轮次终止判定。
- **不修「断线取消整轮」的既有语义**：本 change 只保证状态正确回落。
- **不做失败徽标状态**：失败/超时回 `idle`，错误信息由时间线 system 条目承载；是否保留
  「上次失败」标记作为独立 Open Question（Q2）由用户拍板。

## Impact Analysis

- 影响代码：
  - `agent/team/orchestrator.py`：per-room 完整状态表与 `status_seq`、纯 reducer（工具按
    `tool_call.id` 记账、`iteration_started` 清理残留）、合并发射器、`member_status` 事件、
    建会话失败/取消/意外异常的 teardown、`status_snapshot()` 查询。
  - `agent/team/runner.py`：`SessionRunner.run` 增加可选 `on_progress` 进度回调（不传时行为不变）。
  - `web/session.py`：`run_session` / `_run_session_locked` 增加可选进度观察者；挂/摘
    `ProgressHook`（实现完整 7 方法，生命周期覆盖超时/取消）；把 AgentLoop 事件归一为无内容
    的进度信号。
  - `web/team.py`：`_WorkspaceRunner.run` 透传进度回调。
  - `web/server.py`：`room_state` 增加 `member_statuses` / `status_seq`；房间 WS 用发送锁保证
    「快照先行」，把订阅+首帧放进 try/finally，握手失败也清理订阅；订阅后所有帧走同一 send。
  - `web/static/group.js`、新增 `web/static/group_status.js`、`web/static/index.html`、
    `web/static/style.css`：状态栏 DOM（在房间头部之后）、群公告独立元素、纯函数 reducer、
    桌面/移动端布局、独立 `aria-live` 区域、脚本加载顺序/版本。
- 影响测试：
  - 新增 `tests/agent/team/test_member_status.py`（纯 reducer）；
  - 扩展 `tests/agent/team/test_orchestrator.py`（含取消/意外异常/resume/工具异常、
    `on_progress` 契约）；
  - 扩展 `tests/web_tests/test_group_chat_server.py` 与 `test_group_chat_team.py`
    （`room_state` 快照、首帧、双标签页 teardown、握手失败清理、现有事件循环改为收集到
    `round_ended` 为止）；
  - 新增 `tests/web_tests/test_group_status_js.py`（node + vm 纯函数单测，复用
    `tests/web_tests/test_workflow_graph_js.py` 的 harness）；
  - 新增 `tests/web_tests/test_group_status_browser.py`（群聊专用 fixture；桌面 1200px、
    手机 390px；无事件时状态不变的反定时器断言；公告/aria-live/脚本版本）。
- 影响规格：`web-ui` 新增 1 条 Requirement；`multi-agent-collaboration` 新增 2 条 + MODIFIED
  1 条（轮次终止的 teardown 口径）。
- 影响文档：
  - `docs/openspec-change-backlog.md`（登记本 change，关联 #307）；
  - `docs/architecture.md` 群聊小节补状态事件面；
  - `README.md` / `README_EN.md` 若群聊能力描述需要同步，按仓库规则同 PR 更新；
  - `docs/interview-script/` 相关讲稿建议性更新。
- 风险面：
  - 钩子生命周期：必须在 `finally` 摘除，覆盖超时/取消，否则后续 run 重复触发；
  - 回压：状态只在变化时发、允许合并，但房间广播逐连接 `await`（`web/team.py:112-121`），
    慢客户端可能拖慢终态；终态走既有路径，本 change 不新增协议级超时；
  - 乱序/跨轮：全量表 + `status_seq` + 终态按 seq 守卫；服务端在释放房间认领前同步重置；
  - 快照竞态：发送锁 + `room_state` 首帧 + 客户端水位重置（含服务端重启 seq 变小）；
  - 取消 teardown 投递：强引用后台 task + 2s 上限；循环关闭仍可能丢，重连快照兜底；
  - 事件量：无工具回合约 4-6 条状态事件，每工具 +2 条；全量状态表单条 < 1KB，不落盘。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 非平凡 feature（新增 WS 事件面 + 运行时状态机 + Web 布局/移动端），走 grill；状态语义、
  重连快照、并发工具聚合与聊天产品 presence/typing 的业界做法直接相关，需完整调研。
- research questions:
  - 聊天产品如何建模「正在输入 / 正在思考 / 正在使用工具」这类瞬态状态？事件、租约还是轮询？
    哪一层是权威？
  - 重连/多标签页如何恢复瞬态状态而不被旧快照覆盖？序号/游标与快照的边界怎么定？
  - 并发工具、终态事件与迟到事件如何聚合与排序？
  - 本仓已有的群聊参考实现（DS Bot / dsh-agent-group）用了什么形态，哪些做法必须避免？
- findings:
  - **Discord**：`TYPING_START` 是 Gateway 的瞬态事件，用户开始输入时下发，载荷含
    `channel_id` / `user_id` / `timestamp`；不提供「持续 typing」的权威状态，客户端只做短暂展示。
    来源：[Discord Gateway events](https://discord.com/developers/docs/topics/gateway-events#typing-start)
    与 [discord.js `GatewayTypingStartDispatchData`](https://discord.js.org/docs/packages/discord.js/14.26.5/GatewayTypingStartDispatchData:Interface)。
  - **Matrix**：`m.typing` 是房间级 **ephemeral** 事件；客户端 `PUT /rooms/{roomId}/typing/{userId}`
    带 `timeout`（建议 20–30s）并在过期前续期；接收端 **MUST 用 `user_ids` 列表整体替换**已知
    typing 集合，未列出的用户视为不 typing；服务端不记住不在列表中的用户。这是「租约 + 全量快照」
    模型，与本 change 的「终态权威重置 + 快照」同构，但本 change 的状态生命周期由 run 事件界定，
    不需要时间租约。来源：
    [Matrix typing notifications](https://github.com/matrix-org/matrix-spec-proposals/blob/44772ba81d0ae6199a8548bc8d54e9a54afa4f86/content/client-server-api/modules/typing_notifications.md)。
  - **Presence 状态机**：成熟实现把 presence 收敛为小的、服务端权威的状态机，只发布**状态迁移**
    而不是心跳；重连时以「快照 + 单调游标」收敛，客户端丢弃 `<= 游标` 的增量，缺口过大则重新
    取快照。来源：
    [GoogleCloudPlatform/scion presence.go](https://github.com/GoogleCloudPlatform/scion/blob/main/pkg/hub/presence.go)
    （active/idle 双态、2 分钟窗口、只发迁移）、
    [Fan-Out Guarantees for Browser Reconnects](https://dev.to/tatefletcher6754/fan-out-guarantees-for-browser-reconnects-in-team-presence-and-live-polls-36ig)
    （快照 + cursor 收敛、丢弃过期增量）、
    [Realtime State Convergence](https://dev.to/philemonshaw8453/realtime-state-convergence-7-security-controls-for-concert-livestream-chat-24m8)
    （服务端分配顺序、gap buffer、超界重取快照）。
  - **本地参考实现 DS Bot**（Fei2411/DeepSeek-Bot，Apache-2.0）：`ds-bot/src/client/activity-row.js`
    有 thinking/working 文案与工具名映射，但其短语保持依赖 `setTimeout`、群聊进度靠定时轮询
    （`ds-bot/src/client/cells.js` 的 `GroupReplies` 每 1s `roomProgress`）；`cells.js:536`
    明确「Members speak one at a time, so only the current speaker is typing」。⇒ 可借鉴
    「工具名即状态文案」的表达，**但必须拒绝**客户端定时器/轮询驱动状态——正是本 change 的
    硬约束。
  - **本仓现实**（issue #307 调研 comment，2026-10-20，基线 `48d25f0`）：一个带 1.2s 工具的
    成员回合房间 WS 只有 4 条事件；`before_tool_execute` 能在工具真正开始时给出工具名
    （`agent/loop.py:1417`），而事后 `tool_call` 事件不能当开始信号；非流式无
    `assistant_delta`；建会话失败/轮次取消没有终态事件；`room_state` 无 per-member 快照。
    （grill 复核补充：空产出在生产 `WebSessionRunner` 已归一为 silent，`web/session.py:2226-2227`；
    设计把它降级为编排器层的防御性契约，不列为用户可见缺口。）
- design impact:
  - 采用「服务端权威、只发迁移」的状态模型：reducer 在编排器层，事件只在 phase 变化时发；
    不使用租约/心跳/轮询（与用户「禁止定时器伪造」一致）。
  - 采用「单调 `status_seq` + 终态权威重置 + 重连快照」：对应业界 presence 的 cursor/snapshot
    模式；终态事件携带重置后的序号，客户端据此丢弃迟到事件。
  - 工具状态用「在途集合」而不是单个工具名：对应并行工具分组
    （`agent/loop.py:1450-1526`）。
  - 状态只作为观察面：不写房间日志、不改 `TurnOutcome`、不影响记忆 review 与终止判定。
  - UI 借鉴「工具名即状态」的表达，但移动端与桌面形态由本 change 的布局方案决定，不引入轮询。

## 用户故事

- 作为群聊用户，我发送消息后能立刻看到谁在忙、在思考、在输入、在跑哪个工具，而不是盯着静止的时间线。
- 作为在手机上使用群聊的用户，状态栏不会把消息区挤到只剩约 100px，且我仍能看到谁在做什么。
- 作为维护者，新增状态是真实运行事件的投影：没有事件就不变，工具/流式/终态都能正确回落，
  重连不会留下脏状态。
- 作为未来实现并发的开发者，状态模型按成员独立维护，串行编排只是当前调用方约束，不需要重写 reducer。
