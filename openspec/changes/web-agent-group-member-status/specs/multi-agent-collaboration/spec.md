## ADDED Requirements

### Requirement: 成员运行状态可观测性

群聊编排器 SHALL 为每个房间成员维护一个可观测的运行状态，状态枚举 SHALL 为 `idle`（空闲）/ `running`（运行中兜底）/ `thinking`（LLM 调用在途）/ `typing`（已收到可见流式增量）/ `tool`（工具执行中），优先级 SHALL 为 `tool > typing > thinking > running > idle`。状态 SHALL 仅由真实运行事件驱动，SHALL NOT 由定时器、轮询或推测推进。状态变化 SHALL 通过房间级 `member_status` 事件发布：该事件 SHALL 携带房间级单调递增的 `status_seq` 与当前**完整的非空闲状态表** `statuses`（每项含 `persona_id` / `phase` / `tools` / `tool_count`），缺失成员 SHALL 视为 `idle`。短窗口内的多次变化 MAY 被合并为一次携带最新完整表的 `member_status`（跳过的中间序号不表示状态回退）；最终状态 SHALL 与 `room_state` 快照一致。系统 SHALL NOT 把 token 级 `assistant_delta` / `reasoning_delta` 内容转发到房间级事件。`tool` 状态 SHALL 按工具调用 id 记账，支持并发工具与同名工具，并在集合清空后回落 `running`；新一次 LLM 调用开始（`before_iteration`）SHALL 清空上一批在途工具，避免异常路径残留。终态事件 `member_post` / `member_silent` / `member_failed` / `round_ended` SHALL 权威地把对应成员（或全房间）重置为 `idle`，SHALL 携带**重置后**的 `status_seq`；成员已处于 `idle` / 表为空时，重置 SHALL NOT 递增序号或产生额外状态事件（幂等），此时终态事件 SHALL 携带当前 `status_seq`；`member_failed` SHALL 携带成员显示名 `name`。

#### Scenario: 工具优先于正在输入

- **GIVEN** 成员甲已收到可见流式增量（状态 `typing`）
- **WHEN** 甲开始执行工具 `Bash`
- **THEN** 其状态 SHALL 变为 `tool` 且状态表含 `Bash`
- **AND** 工具执行期间到达的低优先级信号 SHALL NOT 把状态降为 `typing` / `thinking`

#### Scenario: 并发工具聚合与回落

- **GIVEN** 成员甲同时执行 `Bash` 与 `Read`（不同工具调用 id）
- **WHEN** 两个工具都未结束
- **THEN** 状态 SHALL 为 `tool`，`tools` SHALL 含 `Bash`、`Read`，`tool_count` SHALL 为 2
- **AND** 当 `Bash` 结束而 `Read` 未结束时状态 SHALL 保持 `tool`
- **AND** 当最后一个工具结束时状态 SHALL 回落 `running`

#### Scenario: 同名工具并发

- **GIVEN** 成员甲同时执行两个 `Bash` 调用（不同工具调用 id）
- **WHEN** 其中一个结束
- **THEN** `tool_count` SHALL 减为 1 且状态 SHALL 保持 `tool`
- **AND** 只有两个都结束时才 SHALL 离开 `tool`

#### Scenario: 工具异常不卡死工具状态

- **GIVEN** 某工具抛出异常，未触发 `after_tool_execute`
- **WHEN** 编排器收到下一次 `before_iteration`（新一轮 LLM 调用开始）
- **THEN** 上一批在途工具 SHALL 被清空
- **AND** 状态 SHALL 从 `tool` 转为 `thinking`
- **AND** SHALL NOT 一直显示该工具直到终态

#### Scenario: 非流式不伪造正在输入

- **GIVEN** provider 未启用流式（没有 `assistant_delta`）
- **WHEN** 成员甲的一次 LLM 调用在途
- **THEN** 状态 SHALL 停在 `thinking`
- **AND** 系统 SHALL NOT 发出 `typing` 状态

#### Scenario: 空产出回合回到空闲

- **GIVEN** 成员甲的一个回合返回 `text` 出口但文本为空（自定义 runner 路径）
- **WHEN** 编排器处理该出口
- **THEN** 系统 SHALL 发布 `member_silent`（防御性契约；生产 `WebSessionRunner` 已把空文本归一为 silent）
- **AND** 甲的状态 SHALL 重置为 `idle`

#### Scenario: 建会话失败回到空闲

- **GIVEN** 轮到成员甲时其群内会话创建失败
- **WHEN** 编排器处理该失败
- **THEN** 系统 SHALL 发布 `member_failed`（`status = failed`，含 `name`）
- **AND** 甲的状态 SHALL 重置为 `idle`
- **AND** 轮次 SHALL 继续推进，SHALL NOT 永久阻塞

#### Scenario: 状态变化可合并但终点正确

- **GIVEN** 成员甲在一个短窗口内连续经历 `thinking → typing → running`
- **WHEN** 发射器合并这些变化
- **THEN** 系统 MAY 只发布最终状态
- **AND** `status_seq` SHALL 单调递增
- **AND** 任意时刻按最新 `member_status` 或 `room_state` 恢复出的状态 SHALL 等于服务端当前状态

#### Scenario: 不转发 token 增量

- **GIVEN** 一个流式回合产生多个 `assistant_delta` / `reasoning_delta`
- **WHEN** 房间 WS 广播状态
- **THEN** 事件 SHALL 只含状态表，SHALL NOT 含 token 文本
- **AND** 同一状态内的后续增量 SHALL NOT 重复发布状态事件

### Requirement: 房间级成员状态快照与重连

房间级 `room_state` 快照 SHALL 携带当前轮次的 per-member 完整状态表（`member_statuses`）与单调 `status_seq`，使重连或新标签页无需等待下一次状态变化即可恢复；快照未列出的成员 SHALL 视为 `idle`；`round_active = false` 时 SHALL 全部视为 `idle`。房间 WS SHALL 保证 `room_state` 是连接建立后的第一帧，且订阅后的状态事件 SHALL NOT 先于快照到达；握手失败时 SHALL 清理订阅。客户端 SHALL 以新连接的 `room_state` 快照重置状态表与序号水位（包括服务端重启后序号变小的情况）；随后的 `member_status` 与终态事件 SHALL 按 `status_seq` 排序，序号更旧的事件 SHALL 被丢弃。轮次结束/取消/意外异常 SHALL 在任何 await 之前同步清空该房间的成员状态；状态表实际发生变化时 SHALL 递增序号（空表/已全部 idle 时 SHALL NOT 递增），并先于释放房间认领；断线期间客户端 SHALL 把最后已知状态标记为可能过期，重连后以快照为准。

#### Scenario: 长工具执行中重连

- **GIVEN** 成员甲正在执行一个耗时工具，状态为 `tool(Bash)`
- **WHEN** 用户打开第二个房间 WS 或在断线后重连
- **THEN** 收到的 `room_state` SHALL 是首帧
- **AND** `member_statuses` SHALL 含甲的 `phase = tool`、`tools = [Bash]` 与当前 `status_seq`
- **AND** 客户端 SHALL NOT 在等待下一次状态变化前把甲显示为空闲

#### Scenario: 迟到的状态或终态不回退

- **GIVEN** 客户端已应用 `status_seq = 17` 的状态
- **WHEN** 收到 `status_seq = 12` 的 `member_status`，或带 `status_seq = 12` 的终态事件
- **THEN** 客户端 SHALL 丢弃该事件
- **AND** SHALL NOT 把已更新的成员状态回退或清空

#### Scenario: 跨轮终态不抹掉新轮

- **GIVEN** 旧轮次已释放房间认领，新轮次已发出 `status_seq = 20` 的状态
- **WHEN** 旧轮次迟到的 `round_ended`（`status_seq = 18`）到达
- **THEN** 客户端 SHALL 丢弃该终态
- **AND** 新轮次的成员状态 SHALL 保持

#### Scenario: 服务端重启后的新快照

- **GIVEN** 客户端在旧连接上已应用 `status_seq = 42`
- **WHEN** 服务端重启后客户端重连，收到 `status_seq = 0` 的 `room_state`
- **THEN** 客户端 SHALL 以新快照为准重置状态表与序号
- **AND** SHALL NOT 因旧序号更高而拒绝新快照或忽略后续状态事件

#### Scenario: 取消/断线 teardown 对其他标签页可见

- **GIVEN** 两个标签页订阅同一房间，轮次由标签页 A 发起
- **WHEN** 标签页 A 断开导致轮次被取消
- **THEN** 编排器 SHALL 同步清空全部成员状态；状态表实际变化时 SHALL 递增 `status_seq`（空表/已全部 idle 时不递增）
- **AND** 系统 SHALL 尽力向剩余订阅者发布 `round_ended`（`termination = "cancelled"`）
- **AND** 标签页 B SHALL 不再显示任何成员为忙（收到终态或重连快照为 idle）

#### Scenario: 握手失败不留下悬挂订阅

- **GIVEN** 房间 WS 订阅后发送 `room_state` 时连接失败
- **WHEN** 握手路径退出
- **THEN** 该连接 SHALL 被从房间订阅者中移除
- **AND** 后续广播 SHALL NOT 再尝试向该连接发送

## MODIFIED Requirements

### Requirement: 房间级互斥与轮次终止

同一房间同一时刻 SHALL 至多存在一个进行中的轮次；用户在同一轮进行中发送的消息 SHALL 排队进入该轮（只追加进房间日志，其行首 `@` 追加为当前位次之后的发言位，且 SHALL NOT 改变本轮上限基数），SHALL NOT 并行开启第二轮。一轮 SHALL 在**三个出口**之一结束：所有发言位走完 / 达到本轮上限 / 所有剩余成员运行失败或超时；达到上限而结束的轮次 SHALL 在房间日志记录一条 `system` 条目（原因「因达上限结束」）；系统 SHALL NOT 在用户再次发言前自行开启新一轮。（首版不提供轮次取消出口。）取消（例如发起轮次的房间 WS 断开）或意外异常导致的 teardown SHALL NOT 构成新的轮次出口：系统 SHALL 在任何 await 之前同步清空全部成员状态；状态表实际发生变化时 SHALL 递增状态序号（空表/已全部 idle 时 SHALL NOT 递增），并先于释放房间认领；系统 SHALL 尽力发布 `round_ended`（`termination = "cancelled"` 或 `"error"`，携带当前 `status_seq`）；该通知 SHALL NOT 写房间日志、SHALL NOT 产生 `RoundResult`，只用于让客户端把成员状态重置为 `idle`。

#### Scenario: 达到上限而结束

- **GIVEN** 一轮群聊达到本轮上限
- **WHEN** 编排器停止该轮
- **THEN** 房间日志 SHALL 记录一条 `system` 条目（原因「因达上限结束」）
- **AND** 系统 SHALL NOT 在用户再次发言前自行开启新一轮

#### Scenario: 成员运行失败不挂死整轮

- **GIVEN** 本轮某成员的运行失败或超时
- **WHEN** 编排器处理该成员的出口
- **THEN** 该失败 SHALL 以 `system` 条目记入房间日志
- **AND** 轮次 SHALL 继续推进，SHALL NOT 永久阻塞

#### Scenario: 并发消息进入同一轮

- **GIVEN** 一个房间已有一轮在进行中
- **WHEN** 用户再发一条消息
- **THEN** 该消息 SHALL 排队进入当前轮（追加进房间日志）
- **AND** 其行首 `@` SHALL 追加为当前位次之后的发言位
- **AND** 系统 SHALL NOT 并行开启第二个轮次

#### Scenario: 取消 teardown 不作为第四个出口

- **GIVEN** 一个轮次正在进行，且部分成员状态为忙
- **WHEN** 发起轮次的房间 WS 断开导致轮次被取消
- **THEN** 系统 SHALL 发布 `round_ended`（`termination = "cancelled"`）
- **AND** 全部成员状态 SHALL 为 `idle`
- **AND** 该通知 SHALL NOT 写房间日志、SHALL NOT 产生 `RoundResult`、SHALL NOT 被解释为新增的轮次出口
