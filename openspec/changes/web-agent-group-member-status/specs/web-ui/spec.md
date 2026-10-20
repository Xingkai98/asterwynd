## ADDED Requirements

### Requirement: 群聊成员状态栏

Web UI 的群聊视图 SHALL 展示每个成员的运行状态：空闲 / 运行中 / 正在思考 / 正在输入 / 正在使用工具（SHALL 含工具名；多个工具 SHALL 显示名称列表与数量）。状态 SHALL 只由房间级 WebSocket 的真实事件驱动（`member_status`、终态事件、`room_state` 快照；旧服务端降级时另含 `member_speaking`），SHALL NOT 使用定时器推进、推断或伪造。桌面视图 SHALL 在群聊布局左侧（时间线左侧）展示 per-member 状态栏；在 `max-width: 720px` 视口下 SHALL 采用不挤压时间线的移动端形态，并 SHALL 保证 390px 视口下群聊主区可用。状态栏 SHALL 位于房间头部之后，SHALL NOT 覆盖或复用连接/错误/轮次提示区域。状态更新 SHALL NOT 触发时间线整体重绘或打断用户滚动；群公告 SHALL 在状态栏取代成员 chip 行后仍然可见。状态 SHALL 以文字表达，SHALL NOT 只靠颜色区分；`aria-live` SHALL 使用独立区域且只在成员 phase 变化时写入单条文案；动效 SHALL 尊重 `prefers-reduced-motion`。断线期间最后已知状态 SHALL 被标记为可能过期，重连后 SHALL 以 `room_state` 快照整体替换。服务端未提供 `member_status` 时，前端 SHALL 降级为用 `member_speaking` 表示运行中、终态事件回空闲，SHALL NOT 空白或报错。

#### Scenario: 桌面展示五档状态与工具名

- **GIVEN** 一个群聊房间有成员甲、乙
- **WHEN** 甲开始执行工具 `Bash`，乙空闲
- **THEN** 状态栏 SHALL 显示甲为「正在使用工具 · Bash」
- **AND** SHALL 显示乙为「空闲」
- **AND** SHALL NOT 在同一视图对同一成员显示互相矛盾的状态

#### Scenario: 状态随真实事件变化

- **GIVEN** 房间 WS 先推送包含甲 `thinking` 的状态表，再推送包含甲 `typing` 的状态表
- **WHEN** 前端处理这两条 `member_status`
- **THEN** 状态栏 SHALL 依次显示「正在思考」「正在输入」

#### Scenario: 无事件时状态不变

- **GIVEN** 状态栏当前显示甲「正在使用工具 · Bash」
- **WHEN** 在没有任何新事件的情况下经过一段时间
- **THEN** 状态 SHALL 保持不变
- **AND** 前端 SHALL NOT 用定时器自行推进或清除状态

#### Scenario: 状态更新不打断时间线

- **GIVEN** 用户正在向上滚动查看较早的群消息
- **WHEN** 收到新的 `member_status`
- **THEN** 状态栏 SHALL 更新
- **AND** 时间线 SHALL NOT 整体重绘、SHALL NOT 强制滚动到底部

#### Scenario: 状态栏与提示区域互不覆盖

- **GIVEN** 房间头部正在显示「已连接」或「连接断开，重连中...」
- **WHEN** 收到新的 `member_status`
- **THEN** 头部提示 SHALL 保持
- **AND** 成员状态 SHALL 在独立状态栏中更新

#### Scenario: 静默/失败后头部不残留发言文案

- **GIVEN** 成员甲曾发言，随后静默或失败
- **WHEN** 前端处理 `member_silent` / `member_failed`
- **THEN** 房间头部 SHALL NOT 残留「甲 正在发言...」
- **AND** 状态栏 SHALL 显示甲为「空闲」
- **AND** 同一视图 SHALL NOT 对甲显示互相矛盾的状态

#### Scenario: 新一轮开始清除上一轮结束提示

- **GIVEN** 房间头部显示「本轮结束」或「本轮因达上限结束」
- **WHEN** 用户发送新消息（`user_message`，`queued = false`）或收到首个非空闲 `member_status`
- **THEN** 头部的上一轮结束提示 SHALL 被清除
- **AND** 连接/错误提示 SHALL 保持更高优先级

#### Scenario: 自动滚入不打断时间线滚动

- **GIVEN** 用户在手机端向上滚动查看较早消息
- **WHEN** 某成员状态变化触发状态条自动滚入
- **THEN** 自动滚入 SHALL 只影响状态条自身的横向滚动
- **AND** 时间线的纵向滚动位置 SHALL 保持不变

#### Scenario: 群公告不因取代 chip 行而丢失

- **GIVEN** 一个房间配置了群公告
- **WHEN** 打开房间并显示成员状态栏
- **THEN** 群公告 SHALL 仍然可见

#### Scenario: 重连从快照恢复

- **GIVEN** 成员甲正在执行工具，用户断线后重连
- **WHEN** 前端收到 `room_state`
- **THEN** 状态栏 SHALL 立即恢复甲的工具状态
- **AND** 缺失的成员 SHALL 显示为空闲
- **AND** 断线期间的状态 SHALL 不再被视为权威

#### Scenario: 移动端主区可用

- **GIVEN** 视口宽度为 390px
- **WHEN** 用户打开一个群聊
- **THEN** 群聊主区 SHALL 可用（SHALL NOT 因固定 260px 侧栏而只剩约 100px）
- **AND** 成员状态 SHALL 以 design 选定的移动端形态可见，且位于房间头部之后
- **AND** 房间头部 SHALL NOT 横向溢出（设置/删除等次要动作可收纳）
- **AND** 未选择房间时的空状态 SHALL 提供可见的「打开群聊/人设」入口，SHALL NOT 只提示「从左侧选择」

#### Scenario: 旧服务端降级

- **GIVEN** 服务端不发送 `member_status`
- **WHEN** 前端收到 `member_speaking`
- **THEN** 对应成员 SHALL 显示为「运行中」
- **AND** 收到终态事件后 SHALL 回到「空闲」
- **AND** 视图 SHALL NOT 空白或报错

#### Scenario: 迟到的状态不回退

- **GIVEN** 前端已应用较早的终态重置（`status_seq = 20`）
- **WHEN** 收到 `status_seq = 18` 的 `member_status`
- **THEN** 前端 SHALL 丢弃该事件
- **AND** 该成员 SHALL 保持「空闲」

#### Scenario: 可访问性播报

- **GIVEN** 状态栏中有多个成员
- **WHEN** 只有当甲从 `thinking` 变为 `typing` 时
- **THEN** 独立的 `aria-live` 区域 SHALL 只写入与甲变化相关的单条文案
- **AND** SHALL NOT 重复播报未变化成员
- **AND** 在 `prefers-reduced-motion` 下 SHALL NOT 依赖动画传达状态
