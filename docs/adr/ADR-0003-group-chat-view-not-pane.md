# ADR-0003: 群聊在 Web 端是顶层视图而非 Chat pane 类型

- **Status**: accepted
- **Date**: 2026-10-13
- **Deciders**: 实施 agent（web-agent-group-chat change 的 building 阶段）

## Context

`openspec/changes/web-agent-group-chat/design.md` 的 Goals 写「Web 群聊 pane（新增 **pane 类型** + 房间级 WS）」，`proposal.md` 的 Impact Analysis 也写「`web/static/`：新增群聊 pane JS/CSS；扩展 WS 路由（房间级）」。

实现时撞到的事实约束（读 `web/static/chat.js` 得到，非推断）：

- 该文件里 **tab** 是「一个会话的容器」：`createTab` 每条 tab 持自己的 `messagesEl` / `ws` / `currentAssistantMsg` / `approvalCards`，`bindActiveTab` 在切换时把模块级变量指向该 tab 的 DOM（`chat.js:10-45,211-244`）。
- **view** 是顶层页面：`showView` 切换 `hub` / `chat` / `workflow` / `debug`，各自一个 `#xxx-view` section（`chat.js:291-311`）。
- 一次群聊**不是一个会话**：它是「一个房间的时间线 + N 个成员会话的输出聚合」，其事件来自房间级 WS（`/ws/room/{roomId}`），而不是任何一个 `AgentSession` 的 `event_channel`。

把群聊做成「Chat pane 类型」意味着：要么让一条 tab 的 `ws` 指向房间 WS（则该 tab 不再满足 `createTab` 的「一个会话一条 WS」不变量，`handleTabEvent` 的 `event.session_id` rekey 逻辑、`syncActiveTab` 的 per-session 字段全部失去意义），要么在 tab 内部再嵌一层「房间子视图」。两者都要把「tab = 会话」这条既有不变量拆开。

## Decision

群聊实现为一个**新的顶层视图**（`#group-view` + `data-tab="group"` 的 Group 标签），而不是 Chat 视图内的一种 pane 类型：

- 视图内左侧是人设/房间管理，右侧是房间时间线与成员列表；
- 数据来自房间级 WS `/ws/room/{room_id}`（与 `/ws/{session_id}` 并列的新路由）；
- **人设单聊**反过来复用既有 Chat 机制：点人设走 `/api/team/personas/{id}/chat` 拿到会话 id，再用 `window.AsterwyndOpenSession`（`chat.js` 新导出的 `openSessionTab`）开一条**普通 Chat tab**——这正是 design Decision 2 的「单聊就是普通 AgentSession」在这一层的直接体现。

即：把 design 的「pane 类型」读作「一个新的 UI 单元」，落在 **view** 这一档，因为它承载的不是一个会话而是一个房间。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| Chat 视图内的新 pane 类型 | 在 `chat.js` 的 `createTab` 里加 `kind: 'room'`，让该 tab 的 `ws` 指向房间 WS | 拆掉「tab = 一个会话」的不变量：`handleTabEvent` 的 session 重键、`syncActiveTab` 的 per-session 字段、pending 卡片注册表、图片上传 state 全部对房间 tab 无意义，需要在每条路径上加分支；且房间不是会话，`sessionId` 这个 tab 主键填什么都不对 |
| 每个成员一条 Chat tab、前端合并渲染 | 复用既有 per-tab 通道，前端按时间戳合并 N 条流 | `Message` 没有 timestamp / speaker（`agent/message.py:144-155`），`build_history_payload` 只发 role——重连后无法还原有序群时间线。这正是 design Decision 6 引入「房间日志是群时间线唯一权威」的原因；前端合并会绕过这条权威数据 |
| 新建独立的群聊页面（独立 HTML） | 完全不复用现有页面 | 与 hub 的 workspace 选择、身份栏、样式体系割裂；用户要在两套页面之间跳，且 workspace 概念要再实现一遍 |

## Consequences

- 正面影响：
  - 保持「tab = 一个会话」的既有不变量不动，`chat.js` 的 per-tab 机制零改动（只新增两个显式导出 `window.AsterwyndOpenSession` / `window.AsterwyndShowView`）。
  - 群聊的状态与生命周期独立于 Chat tab（关掉所有 Chat tab 不影响正在看的房间），与「房间是长期存在的」语义一致。
  - 单聊天然复用全部既有 Chat 能力（审批卡片、pending 补发、图片上传、slash command）。
- 负面影响：
  - 与 design 的「pane 类型」措辞不一致（本 ADR 即该偏离的记录）。
  - 前端多一个 `#group-view` section 与一个 `group.js` 模块；顶层 view 的数量从 4 增到 5，`showView` 多一个分支。
  - 群聊视图**不参与** `session_tabs` 标签栏（它不是一个 tab），切换靠顶部 Group 标签。
- 需要的相关变更：
  - `web/static/index.html`（Group 标签 + `#group-view`）、`web/static/group.js`、`web/static/style.css`；
  - `web/static/chat.js` 导出 `openSessionTab` / `showView`（供 group.js 回调）。

## Revisit Conditions

- [ ] 若后续要求「群聊与单聊并排显示在一个页面里」（真正的 pane 化布局），需要重新评估：那时房间与 tab 的区别会变成布局层的问题，而不是容器语义的问题。
- [ ] 若 `chat.js` 的 per-tab 机制被重构（例如 tab 泛化为「任意可订阅单元」），上面的第一条拒绝理由消失，可以重新考虑把房间做成一种 tab。
