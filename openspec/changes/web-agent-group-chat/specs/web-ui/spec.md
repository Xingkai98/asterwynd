## MODIFIED Requirements

### Requirement: Web UI SHALL support tool approval requests

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。每个 Web session 同一时刻 SHALL 只有一个 pending approval。WebSocket 断开 SHALL NOT 让 pending approval 立即失败；重连后服务端 SHALL 补发该卡片（见「pending 提问与审批跨 WebSocket 连接存活」与「重连补发 pending 交互卡片」）。**群内会话（`kind: room_member`）除外**：群内会话 SHALL NOT 把审批暴露为交互式 pending，而是按 fail-closed 立即可用性判定处理（见「群内会话的交互式 pending 降级」）。（人设单聊会话 `kind: persona_chat` 是用户在场的会话，SHALL NOT 降级，照常暴露 pending。）

#### Scenario: Web 用户批准 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户批准该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: Web 用户拒绝 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户拒绝该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** Web UI SHALL 展示该审批已拒绝

#### Scenario: 并发 session 的审批路由互相隔离

- **GIVEN** 两个 Web UI session 都有 pending approval request
- **WHEN** 用户处理其中一个请求
- **THEN** 该决定 SHALL 只恢复匹配的 session/run
- **AND** SHALL NOT 影响其他 session 的 pending approval

#### Scenario: 断连重连后审批仍可作答

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 浏览器 WebSocket 断开后重连同一 session
- **WHEN** 用户在重连后的页面批准该请求
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: 群内会话不暴露交互式审批

- **GIVEN** 一个群内会话（`kind: room_member`）触发了需审批的工具调用
- **WHEN** 该调用到达审批判定点
- **THEN** 系统 SHALL NOT 把该审批暴露为交互式 pending 卡片
- **AND** SHALL 按 fail-closed 立即判定其可用性

### Requirement: pending 提问与审批跨 WebSocket 连接存活

Web session SHALL 把「运行中等待用户响应的 pending 提问/审批」当作 session 级状态，而不是某条 WebSocket 连接的状态。WebSocket 断开 SHALL NOT 让仍在等待用户响应的 pending 提问/审批失败；服务端 SHALL NOT 因断开而返回 `[Error: websocket disconnected]` 之类的失败答复给 AgentLoop。**群内会话（`kind: room_member`）除外**：它 SHALL NOT 建立交互式 pending（见「群内会话的交互式 pending 降级」），故本 Requirement 对其不适用。

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

### Requirement: Web UI 提供 session hub 列表

Web UI SHALL 提供 session 入口页（hub），列出已保存会话并允许按 workspace 切换与新建。hub 通过 `GET /api/workspaces` 获取允许的 workspace 列表，通过 `GET /api/sessions?workspace=<path>` 获取指定 workspace 的会话列表（复用 `SessionStore.list_sessions()` 元数据：session_id、mode、created_at、updated_at、messages）。workspace 不在 allowlist 或路径不存在时 SHALL 返回结构化拒绝（HTTP 403 + `{"error": "workspace_not_allowed"}`）。缺省 `workspace` SHALL 使用主 workspace。**内部会话（人设单聊 `kind: persona_chat` 与群内会话 `kind: room_member`）SHALL NOT 出现在该列表中**（见「内部会话的生命周期保护」）；该过滤 SHALL 由 id 前缀/roster 映射判定，SHALL NOT 依赖读取会话快照，故内部会话快照损坏时也不泄漏进列表。

**单条损坏 SHALL NOT 打掉整个列表**：某条会话的落盘数据不可解码/损坏时，`GET /api/sessions` SHALL 仍返回 200；该条 SHALL 以可区分的降级形态出现在列表里——带 `damaged` 标记与可读 `reason`（`session_id` 取目录名，因为文件不可读时目录名是唯一可信标识）——SHALL NOT 静默消失（「少了几个会话但没人解释」与「不显示 = 没事」是同一种误读）。其余会话的元数据 SHALL 正常返回。（内部会话的损坏条因上述过滤不出现，不属于本条覆盖范围。）

#### Scenario: 获取 workspace 列表

- **GIVEN** Web UI 配置了主 workspace 与 allowlist
- **WHEN** 前端请求 `GET /api/workspaces`
- **THEN** 响应 SHALL 包含主 workspace 与 allowlist 内存在的路径
- **AND** 每个 workspace SHALL 标注是否为主 workspace
- **AND** 每个 workspace SHALL 标注运行期是否存在

#### Scenario: 获取会话列表

- **GIVEN** 主 workspace 下存在已保存会话
- **WHEN** 前端请求 `GET /api/sessions`
- **THEN** 响应 SHALL 返回会话列表，字段含 session_id、mode、created_at、updated_at、messages
- **AND** 列表 SHALL 按 updated_at 倒序

#### Scenario: 未授权 workspace 被拒绝

- **GIVEN** 请求指定了一个不在 allowlist 的 workspace
- **WHEN** 前端请求 `GET /api/sessions?workspace=<path>`
- **THEN** 响应 SHALL 返回 HTTP 403 与结构化错误
- **AND** SHALL NOT 返回任何会话数据

#### Scenario: 单条会话损坏不拖垮列表

- **GIVEN** 存储目录里存在一条不可解码/损坏的会话数据（例如 locale 非 UTF-8 时代写入的脏文件）
- **WHEN** 客户端请求 `GET /api/sessions`
- **THEN** 接口 SHALL 返回 200
- **AND** 该条 SHALL 以 `damaged` 标记 + 可读 `reason` 出现在列表里（`session_id` 取目录名）
- **AND** 其余会话的元数据 SHALL 正常返回

#### Scenario: 内部会话不出现且损坏也不泄漏

- **GIVEN** 一个 workspace 下同时存在一个普通会话（`kind: chat`）与一个人设单聊会话（`kind: persona_chat`）
- **WHEN** 客户端请求 `GET /api/sessions`
- **THEN** 列表 SHALL 只含该普通会话
- **AND** 即使人设单聊会话的快照损坏，它 SHALL NOT 出现在列表中

### Requirement: Web UI 提供会话删除

Web UI hub SHALL 通过 `DELETE /api/sessions/{session_id}?workspace=<path>` 提供会话删除。删除 SHALL 移除内存中的会话（若在）与指定 workspace store 下的持久化快照；workspace 参数 SHALL 经 allowlist 校验。删除已打开会话时 SHALL 关闭对应标签页。**若 `session_id` 是内部会话（人设单聊 `kind: persona_chat` 或群内会话 `kind: room_member`），该请求 SHALL 被拒绝**，删除 SHALL 只能经人设/房间接口进行（见「内部会话的生命周期保护」与「人设与房间的管理入口」）。

#### Scenario: 删除会话

- **GIVEN** hub 列表中某会话已被删除请求
- **WHEN** 前端调用 `DELETE /api/sessions/<session_id>?workspace=<path>`
- **THEN** 该会话从内存与磁盘快照移除
- **AND** 列表 SHALL 不再展示该会话
- **AND** 若存在打开的同 id 标签页，该标签页 SHALL 被关闭

#### Scenario: 删除冷会话

- **GIVEN** 某会话未在内存中打开（仅存在磁盘快照）
- **WHEN** 前端调用 `DELETE /api/sessions/<session_id>?workspace=<path>`
- **THEN** 服务端 SHALL 按请求 workspace 定位 store 并删除磁盘快照
- **AND** 返回 `{"deleted": true, "session_id": <id>, "workspace": "<resolved>"}`

#### Scenario: 删除时缺 workspace 参数

- **GIVEN** 前端调用 `DELETE /api/sessions/<session_id>`（无 `?workspace=`）
- **WHEN** 发起删除
- **THEN** 响应 SHALL 返回 HTTP 400 与结构化错误
- **AND** SHALL NOT 删除任何快照

#### Scenario: 删除时未授权 workspace 被拒

- **GIVEN** 请求 `DELETE /api/sessions/<session_id>?workspace=<不在 allowlist 的路径>`
- **WHEN** 前端发起删除
- **THEN** 响应 SHALL 返回 HTTP 403 与结构化错误
- **AND** SHALL NOT 删除任何快照

#### Scenario: 内部会话不可经会话删除接口删除

- **GIVEN** 一个人设单聊会话的内部 id
- **WHEN** 前端调用 `DELETE /api/sessions/<内部 id>?workspace=<path>`
- **THEN** 响应 SHALL 被拒绝
- **AND** 该会话快照 SHALL NOT 被删除

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
- **AND** SHALL 让被点名的成员成为本轮首先发言者

### Requirement: 多 agent 消息按来源区分

群聊视图 SHALL 按发言人区分来自不同 agent 的消息，SHALL NOT 把不同 agent 的消息渲染为同一来源。

#### Scenario: 多个 agent 先后发言

- **GIVEN** 群聊轮次中两个不同 agent 先后发言
- **WHEN** 视图渲染这些消息
- **THEN** 两条消息 SHALL 可见地来自不同的 agent

### Requirement: 人设与房间的管理入口

Web UI SHALL 提供以下管理入口：创建/改名/改指令/改模型/删除人设；创建/改名/改成员/改 admin/删除房间；以及进入某人设单聊的入口。删除 SHALL 执行级联，级联顺序 SHALL 为「先删会话底座与 persona 记忆，最后删 roster/房间条目」，且 SHALL 幂等（中断后重试 SHALL 可继续）。

#### Scenario: 进入人设单聊

- **GIVEN** 已存在一个人设
- **WHEN** 用户从管理入口进入该人设单聊
- **THEN** Web UI SHALL 打开该人设的独立单聊视图

#### Scenario: 删除人设触发级联

- **GIVEN** 一个人设同时是某房间成员且有自己的单聊会话与 persona 记忆
- **WHEN** 用户删除该人设
- **THEN** 系统 SHALL 删除其单聊会话底座与 persona 记忆，并从所有房间移除该成员
- **AND** 该人设的群内会话底座 SHALL 一并删除

#### Scenario: 删除房间触发级联

- **GIVEN** 一个房间有若干成员、房间日志与 (人设, 房间) 群内会话
- **WHEN** 用户删除该房间
- **THEN** 系统 SHALL 删除房间记录、房间日志与所有该房间的群内会话底座
- **AND** 相关人设本身 SHALL NOT 被删除

#### Scenario: 级联中断可重试且不留孤儿

- **GIVEN** 一次删除人设的级联在中途失败
- **WHEN** 用户重试该删除
- **THEN** 级联 SHALL 从不完整状态继续并完成
- **AND** SHALL NOT 留下「既不出现在 hub、又拒绝被删除」的孤儿内部会话

### Requirement: 内部会话的生命周期保护

Web UI SHALL NOT 把人设单聊会话与群内会话作为普通会话展示在会话列表；且 SHALL NOT 允许任何会销毁内部会话底座的路径（会话删除接口、WS `reset`）直接作用于它们——删除 SHALL 只能经人设/房间接口进行。内部会话 id SHALL 使用可判定的前缀约定（`persona-` / `room-`），使 hub 过滤与保护判定不依赖读取会话快照。

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

### Requirement: 群内会话的交互式 pending 降级

群内会话（`kind: room_member`）SHALL NOT 暴露交互式提问工具；其审批类工具调用 SHALL 按 fail-closed 立即判定为不可用，SHALL NOT 阻塞可能无人值守的轮次。人设单聊会话（`kind: persona_chat`）是用户在场的会话，SHALL NOT 降级，照常暴露交互式 pending。

#### Scenario: 群聊轮次不因审批阻塞

- **GIVEN** 一个群聊轮次中某成员触发了需审批的工具调用
- **WHEN** 该调用到达审批判定点
- **THEN** 系统 SHALL 立即按 fail-closed 判定其不可用
- **AND** 轮次 SHALL NOT 阻塞等待用户响应

#### Scenario: 群内会话无交互式提问工具

- **GIVEN** 一个人设的群内会话
- **WHEN** 检查该会话可用的工具面
- **THEN** 交互式提问类工具 SHALL NOT 在其中

#### Scenario: 人设单聊照常暴露交互式 pending

- **GIVEN** 一个人设单聊会话（`kind: persona_chat`）
- **WHEN** 其触发了需审批的工具调用或交互式提问
- **THEN** 系统 SHALL 照常向用户暴露该 pending
- **AND** SHALL NOT 按群内会话的降级口径处理
