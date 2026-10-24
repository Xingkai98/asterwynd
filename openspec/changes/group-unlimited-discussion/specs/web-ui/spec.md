## MODIFIED Requirements

### Requirement: 人设与房间的管理入口

Web UI SHALL 提供以下管理入口：创建/改名/改指令/改模型/删除人设；创建/改名/改成员/改 admin/改讨论模式/删除房间；以及进入某人设单聊的入口。房间的讨论模式（`discussion_mode`：`single` / `unlimited`）SHALL 仅在房间 `reply_mode = everyone` 时允许选择 `unlimited`（`reply_mode = admin` 时设置对话框中的 `unlimited` 选项 SHALL 不可用）。删除 SHALL 执行级联，级联顺序 SHALL 为「先删会话底座与该人设/房间的**全部记忆 scope**，最后删 roster/房间条目」，且 SHALL 幂等（中断后重试 SHALL 可继续）。

#### Scenario: 进入人设单聊

- **GIVEN** 已存在一个人设
- **WHEN** 用户从管理入口进入该人设单聊
- **THEN** Web UI SHALL 打开该人设的独立单聊视图

#### Scenario: 删除人设触发级联

- **GIVEN** 一个人设同时是某房间成员且有自己的单聊会话与多份记忆 scope
- **WHEN** 用户删除该人设
- **THEN** 系统 SHALL 删除其单聊会话底座与**该人设的全部记忆 scope**（含各群 scope），并从所有房间移除该成员
- **AND** 该人设的群内会话底座 SHALL 一并删除

#### Scenario: 删除房间触发级联

- **GIVEN** 一个房间有若干成员、房间日志、(人设, 房间) 群内会话与 (人设, 房间) 记忆目录
- **WHEN** 用户删除该房间
- **THEN** 系统 SHALL 删除房间记录、房间日志、所有该房间的群内会话底座与所有该房间的 (人设, 房间) 记忆目录
- **AND** 相关人设本身 SHALL NOT 被删除

#### Scenario: 级联中断可重试且不留孤儿

- **GIVEN** 一次删除人设的级联在中途失败
- **WHEN** 用户重试该删除
- **THEN** 级联 SHALL 从不完整状态继续并完成
- **AND** SHALL NOT 留下「既不出现在 hub、又拒绝被删除」的孤儿内部会话

#### Scenario: 房间设置修改讨论模式

- **GIVEN** 一个 `reply_mode = everyone` 的房间
- **WHEN** 用户在房间设置中把讨论模式改为 `unlimited`
- **THEN** 系统 SHALL 持久化 `discussion_mode = unlimited`
- **AND** 该房间后续用户消息 SHALL 开启讨论链

## ADDED Requirements

### Requirement: 群聊讨论链状态与停止讨论控件

Web UI 的群聊视图 SHALL 展示当前讨论状态，并 SHALL 在 `discussion_mode = unlimited` 的讨论链进行中提供「停止讨论」控件。房间设置 SHALL 提供讨论模式选择（`single` / `unlimited`），且 SHALL 仅在房间 `reply_mode = everyone` 时允许选择 `unlimited`；`reply_mode = admin` 时该选项 SHALL 不可用（置灰或隐藏），服务端返回结构化错误时前端 SHALL 展示该错误，SHALL NOT 静默丢弃。讨论进行中 SHALL 显示「讨论中（第 k 轮）」；整条讨论结束时 SHALL 按 `discussion_ended.reason` 显示「讨论已收敛」（`converged`）/「讨论已停止」（`stopped`）/「讨论达安全上限」（`max_rounds` / `max_turns` / `max_seconds`）/「讨论已中止（本轮无人发言，存在失败）」（`all_failed`）/「讨论模式已切换为单轮」（`mode_changed`）/「讨论已中止」（`cancelled`）/「讨论异常结束」（`error`）/「讨论因本轮达上限结束」（`round_limit`）/「讨论已结束」（`completed`）。`round_ended` 且 `chain_continues = true` 时 SHALL NOT 显示「本轮结束」。讨论事件的终态 SHALL 按 `chain_id` 归属校验：只应用与当前讨论链 `chain_id` 一致的 `round_ended` / `system_entry` / `discussion_stop_requested` / `discussion_ended`，迟到的旧链终态 SHALL NOT 覆盖新链状态。链内新增的 `system` 条目 SHALL 通过 `system_entry` 事件实时追加到时间线（按 `seq` 去重），SHALL NOT 只依赖刷新。停止控件 SHALL 通过房间级 WebSocket 发送 `stop_discussion`；WS 未连通时 SHALL 降级为 `POST /api/team/rooms/{room_id}/discussion/stop`。点击后控件 SHALL 置灰并显示「正在停止…」，收到 `discussion_ended` 后恢复。停止控件 SHALL 收纳进房间头部既有次要动作区，`max-width: 720px` 视口下 SHALL NOT 造成房间头部横向溢出。`discussion_mode = single` 的房间 SHALL 保持既有状态文案与行为不变，SHALL NOT 显示停止控件。

#### Scenario: 无限讨论中的第 k 轮状态

- **GIVEN** 一个 `discussion_mode = unlimited` 的房间，讨论链进入第 2 轮
- **WHEN** 前端收到 `round_ended(chain_continues = true)` 后第 2 轮开始
- **THEN** 房间头部 SHALL 显示「讨论中（第 2 轮）」
- **AND** SHALL NOT 显示「本轮结束」

#### Scenario: 收敛后状态

- **GIVEN** 讨论链以自然收敛结束
- **WHEN** 前端收到 `discussion_ended(reason = "converged")`
- **THEN** 房间头部 SHALL 显示「讨论已收敛」
- **AND** 停止控件 SHALL 隐藏

#### Scenario: 停止控件

- **GIVEN** 讨论链进行中且房间 WS 已连通
- **WHEN** 用户点击「停止讨论」
- **THEN** 前端 SHALL 发送 `stop_discussion`，控件 SHALL 置灰并显示「正在停止…」
- **AND** 收到 `discussion_ended(reason = "stopped")` 后 SHALL 恢复

#### Scenario: 旧链终态不覆盖新链状态

- **GIVEN** 旧链的迟到 `discussion_ended` 到达时，房间已开启新链
- **WHEN** 前端处理该事件
- **THEN** 因 `chain_id` 不一致，前端 SHALL NOT 用旧终态覆盖新链的「讨论中（第 k 轮）」
- **AND** 时间线合并 SHALL 按 `seq` 保留两条链的消息

#### Scenario: admin 模式不可选无限讨论

- **GIVEN** 房间 `reply_mode = admin`
- **WHEN** 用户打开房间设置
- **THEN** 讨论模式的 `unlimited` 选项 SHALL 不可用
- **AND** 服务端返回结构化错误时前端 SHALL 展示该错误

#### Scenario: 单轮房间零变化

- **GIVEN** 一个 `discussion_mode = single` 的房间
- **WHEN** 一轮结束
- **THEN** 前端 SHALL 沿用既有「本轮结束 / 本轮因达上限结束 / 本轮已中止 / 本轮异常结束」文案
- **AND** SHALL NOT 显示停止控件
