## MODIFIED Requirements

### Requirement: Web UI SHALL support tool approval requests

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。每个 Web session 同一时刻 SHALL 只有一个 pending approval。WebSocket 断开 SHALL NOT 让 pending approval 立即失败；重连后服务端 SHALL 补发该卡片（见「pending 提问与审批跨 WebSocket 连接存活」与「重连补发 pending 交互卡片」）。**「内部会话」（人设单聊会话与 (人设, 群) 群内会话）除外**：内部会话 SHALL NOT 把审批暴露为交互式 pending，而是按 fail-closed 立即可用性判定处理（见「内部会话的交互式 pending 降级」）。

#### Scenario: Web 用户批准 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户批准该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: 内部会话不暴露交互式审批

- **GIVEN** 一个群内会话触发了一个需审批的工具调用
- **WHEN** 该调用到达审批判定点
- **THEN** 系统 SHALL NOT 把该审批暴露为交互式 pending 卡片
- **AND** SHALL 按 fail-closed 立即判定其可用性

### Requirement: pending 提问与审批跨 WebSocket 连接存活

Web session SHALL 把「运行中等待用户响应的 pending 提问/审批」当作 session 级状态，而不是某条 WebSocket 连接的状态。WebSocket 断开 SHALL NOT 让仍在等待用户响应的 pending 提问/审批失败；服务端 SHALL NOT 因断开而返回 `[Error: websocket disconnected]` 之类的失败答复给 AgentLoop。**本 Requirement 适用于「面向用户的会话」（`kind: chat`）；内部会话（人设单聊与群内会话）SHALL NOT 建立交互式 pending，故不适用。**

pending 状态 SHALL 由 `WebQuestionHandler` / `WebApprovalHandler` 在建立时保留完整的可重放载荷（提问的 `title`/`body`/`options`、审批的 `tool_name`/`risk`/`redacted_args` 等 `to_event_data()` 全部字段），供重连补发使用。

#### Scenario: 切后台断连不判定 pending 审批失败

- **GIVEN** 一个 Web session 有 pending approval request，AgentLoop 正在等待用户决定
- **WHEN** 浏览器 WebSocket 断开（移动端切后台）
- **THEN** pending approval SHALL 保持有效，SHALL NOT 被判定为 `unavailable`
- **AND** AgentLoop SHALL 继续等待用户响应，SHALL NOT 收到 `websocket disconnected` 失败

#### Scenario: 切后台断连不判定 pending 提问失败

- **GIVEN** 一个 Web session 有 pending question，AgentLoop 正在等待用户作答
- **WHEN** 浏览器 WebSocket 断开
- **THEN** pending question SHALL 保持有效，SHALL NOT 被判定为超时或失败

## ADDED Requirements

### Requirement: 群聊视图与房间级 WebSocket

Web UI SHALL 提供群聊视图，展示某个群聊的消息流（来自房间日志）、成员列表与当前发言者；用户 SHALL 能在该视图中发送群消息，并以 `@<名称>` 点名成员。群聊视图 SHALL 通过**房间级 WebSocket** 订阅该房间的成员输出（现有 WS 路由按 session 绑定，不适用于房间聚合）。

#### Scenario: 打开群聊视图

- **GIVEN** 存在一个群聊
- **WHEN** 用户在 Web UI 打开该群聊
- **THEN** 视图 SHALL 展示该群聊的消息流与成员列表

#### Scenario: 在群聊视图中点名成员

- **GIVEN** 用户处于某群聊视图
- **WHEN** 用户输入以 `@<名称>` 开头的消息并发送
- **THEN** 系统 SHALL 将该消息作为群消息处理
- **AND** SHALL 让被点名的成员成为下一个发言者

### Requirement: 多 agent 消息按来源区分

群聊视图 SHALL 按发言人区分来自不同 agent 的消息，SHALL NOT 把不同 agent 的消息渲染为同一来源。

#### Scenario: 多个 agent 先后发言

- **GIVEN** 群聊轮次中两个不同 agent 先后发言
- **WHEN** 视图渲染这些消息
- **THEN** 两条消息 SHALL 可见地来自不同的 agent

### Requirement: 人设与房间的管理入口

Web UI SHALL 提供以下管理入口：创建/改名/改指令/改模型/删除人设；创建/改名/改成员/改 admin/删除房间；以及**进入某人设单聊**的入口。删除人设或房间 SHALL 执行级联（见「内部会话的生命周期保护」）。

#### Scenario: 进入人设单聊

- **GIVEN** 已存在一个人设
- **WHEN** 用户从管理入口进入该人设单聊
- **THEN** Web UI SHALL 打开该人设的独立单聊视图

#### Scenario: 删除人设触发级联

- **GIVEN** 一个人设同时是某房间成员且有自己的单聊会话与 persona 记忆
- **WHEN** 用户删除该人设
- **THEN** 系统 SHALL 删除其单聊会话底座、其 persona 记忆、并从所有房间移除该成员
- **AND** 该人设的群内会话底座 SHALL 一并删除

### Requirement: 内部会话的生命周期保护

Web UI SHALL NOT 把人设单聊会话与群内会话作为普通会话展示在会话列表（hub / `GET /api/sessions`）；且 SHALL NOT 允许任何会销毁内部会话底座的路径（会话删除接口、WS `reset`）直接作用于它们——删除 SHALL 只能经人设/房间接口进行。

#### Scenario: hub 不列出内部会话

- **GIVEN** 已存在一个人设与一个群聊
- **WHEN** 用户打开 hub
- **THEN** 该人设的单聊会话与 (人设, 群) 群内会话 SHALL NOT 作为普通会话出现

#### Scenario: 内部会话不可经会话删除接口删除

- **GIVEN** 某个人设单聊会话的底座 id
- **WHEN** 调用会话删除接口删除该 id
- **THEN** 该删除 SHALL 被拒绝
- **AND** 人设 SHALL 只能经人设/房间的删除接口清理

#### Scenario: 内部会话不可经 WS reset 换底座

- **GIVEN** 某个人设单聊会话的 WS 连接
- **WHEN** 客户端对该连接发送 `reset`
- **THEN** 系统 SHALL 拒绝销毁其底座（或复用原 session id 并回写 roster）
- **AND** roster 中的「人设 → 单聊会话 id」映射 SHALL 保持有效

### Requirement: 内部会话的交互式 pending 降级

内部会话（人设单聊与群内会话）SHALL NOT 暴露交互式提问工具；其审批类工具调用 SHALL 按 fail-closed 立即判定为不可用，SHALL NOT 阻塞可能无人值守的轮次。

#### Scenario: 群聊轮次不因审批阻塞

- **GIVEN** 一个群聊轮次中某成员触发了需审批的工具调用
- **WHEN** 该调用到达审批判定点
- **THEN** 系统 SHALL 立即按 fail-closed 判定其不可用
- **AND** 轮次 SHALL NOT 阻塞等待用户响应

#### Scenario: 内部会话无交互式提问工具

- **GIVEN** 一个人设的群内会话
- **WHEN** 检查该会话可用的工具面
- **THEN** 交互式提问类工具 SHALL NOT 在其中
