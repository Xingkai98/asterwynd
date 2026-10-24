## MODIFIED Requirements

### Requirement: 房间级互斥与轮次终止

同一房间同一时刻 SHALL 至多存在一个进行中的**讨论**：`discussion_mode = single` 时讨论 = 一轮；`discussion_mode = unlimited` 时讨论 = 一条讨论链（见「讨论链自动续轮与收敛」）。用户在同一讨论进行中发送的消息 SHALL 排队进入当前轮：只追加进房间日志，其行首 `@` 追加为当前位次之后的发言位；若消息到达时当前轮已结束、下一轮尚未开始，其行首 `@` SHALL 记入待应用点名并在下一轮开局 slot 中生效；两种情况下 SHALL NOT 改变当前轮的上限基数，SHALL NOT 改变链级安全阀基数，SHALL NOT 并行开启第二条讨论。若消息在**所有成员回合的切片构造之后**到达（无任何回合看到它），系统 SHALL 将其记为本链的未消费用户消息，按「讨论链自动续轮与收敛」的收敛规则处理；本 Requirement SHALL NOT 保证链内用户消息必有成员回合消费它。一轮 SHALL 在以下出口之一结束：所有发言位走完 / 达到本轮上限 / 所有剩余成员运行失败或超时 / 用户请求停止讨论（`single` 模式不提供停止讨论）。达到本轮上限而结束的轮次 SHALL 在房间日志记录一条 `system` 条目（原因「因达上限结束」）。`discussion_mode = single`（缺省）下，系统 SHALL NOT 在用户再次发言前自行开启新一轮；`discussion_mode = unlimited` 下，整条链的结束出口以「讨论链自动续轮与收敛」为准。取消（例如发起讨论的房间 WS 断开）或意外异常导致的 teardown SHALL NOT 构成新的轮次出口：系统 SHALL 在任何 await 之前同步清空全部成员状态；状态表实际发生变化时 SHALL 递增状态序号（空表/已全部 idle 时 SHALL NOT 递增），并先于释放房间认领；系统 SHALL 尽力发布 `round_ended`（`termination = "cancelled"` 或 `"error"`，携带当前 `status_seq`）；`unlimited` 链下 SHALL 另尽力发布 `discussion_ended`（`reason` 同为 `cancelled` / `error`），并 SHALL 在房间日志写一条 `system`「讨论因页面断开而中止」（链因断线取消时，让用户知道中止原因）；该 `round_ended` / `discussion_ended` 通知 SHALL NOT 被解释为新增的轮次出口、SHALL NOT 产生 `RoundResult`，只用于让客户端把成员状态重置为 `idle` 与展示中止原因。

#### Scenario: 达到本轮上限而结束

- **GIVEN** 一轮群聊达到本轮上限
- **WHEN** 编排器停止该轮
- **THEN** 房间日志 SHALL 记录一条 `system` 条目（原因「因达上限结束」）
- **AND** 若房间为 `discussion_mode = single`，系统 SHALL NOT 在用户再次发言前自行开启新一轮
- **AND** 若房间为 `discussion_mode = unlimited`，系统 SHALL 按「讨论链自动续轮与收敛」判定整条链的结束出口

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
- **AND** 在 `unlimited` 链中，该排队 SHALL NOT 改变链的安全阀基数，也 SHALL NOT 打断续轮

#### Scenario: 轮间窗口到达的消息不丢失点名

- **GIVEN** 一条 `discussion_mode = unlimited` 的讨论链刚结束第 k 轮、第 k+1 轮尚未开始
- **WHEN** 用户发送以 `@B` 开头的消息
- **THEN** 该消息 SHALL 追加进房间日志
- **AND** `@B` SHALL 记入待应用点名，并在第 k+1 轮开局 slot 中生效（B 优先于默认顺序，且被消费后立即清空）
- **AND** 系统 SHALL NOT 因此开启第二条讨论链

#### Scenario: 用户停止结束当前轮（`unlimited` 第四出口）

- **GIVEN** 一条 `discussion_mode = unlimited` 的讨论链正在进行，且用户请求停止讨论
- **WHEN** 当前成员回合运行结束
- **THEN** 编排器 SHALL 结束当前轮并跳过本轮剩余发言位
- **AND** SHALL 以 `termination = "stopped"` 发布 `round_ended`
- **AND** SHALL NOT 打断该成员正在进行的运行（工具调用 SHALL 正常结束）
- **AND** `discussion_mode = single` 的房间 SHALL NOT 提供该出口

#### Scenario: 取消 teardown 不作为轮次出口

- **GIVEN** 一个轮次正在进行，且部分成员状态为忙
- **WHEN** 发起轮次的房间 WS 断开导致轮次被取消
- **THEN** 系统 SHALL 发布 `round_ended`（`termination = "cancelled"`）
- **AND** 全部成员状态 SHALL 为 `idle`
- **AND** 该通知 SHALL NOT 写房间日志、SHALL NOT 产生 `RoundResult`、SHALL NOT 被解释为新增的轮次出口
- **AND** `unlimited` 链下 SHALL 另尽力发布 `discussion_ended`（`reason = "cancelled"`），同样 SHALL NOT 写房间日志

### Requirement: 房间应答模式

每个房间 SHALL 拥有应答模式 `reply_mode`，取值 `admin`（缺省）/ `everyone`；并 SHALL 拥有讨论模式 `discussion_mode`，取值 `single`（缺省）/ `unlimited`。`admin` 模式下，无 `@` 的普通消息 SHALL 由房间 admin 应答（无 admin 则 roster 首个 `mainBot`）；`everyone` 模式下，无 `@` 的普通消息 SHALL 让全体成员按序各得一次发言机会（admin 先），每名成员自行决定发言或静默。`discussion_mode = unlimited` 仅在 `reply_mode = everyone` 时合法：创建或更新房间时若合并后的生效值为 `unlimited` 且 `reply_mode != everyone`，系统 SHALL 以结构化错误拒绝该请求（SHALL NOT 静默改写用户数据）；把 `reply_mode` 改为 `admin` 时若房间的 `discussion_mode` 仍为 `unlimited` 且请求未同时给出 `single`，系统同样 SHALL 拒绝。两种应答模式均 SHALL 受每轮每成员发言上限约束。

#### Scenario: admin 模式仅管理员应答

- **GIVEN** 一个 `reply_mode = admin` 的房间，用户发送不含 `@` 的普通消息
- **THEN** 只有房间 admin SHALL 成为本轮初始发言者

#### Scenario: everyone 模式全员各得一次机会

- **GIVEN** 一个 `reply_mode = everyone` 的房间有 3 名成员，用户发送不含 `@` 的普通消息
- **THEN** 三名成员 SHALL 按序各得一次发言机会（admin 先）
- **AND** 没有新增内容的成员 SHALL 可以静默

#### Scenario: 讨论模式非法组合被拒绝

- **GIVEN** 一个 `reply_mode = admin` 的房间
- **WHEN** 用户请求把该房间的 `discussion_mode` 设为 `unlimited`
- **THEN** 系统 SHALL 返回结构化错误（`discussion_mode_requires_everyone`）并拒绝该请求
- **AND** 房间配置 SHALL 保持原值

#### Scenario: 切换应答模式时拒绝悬空讨论模式

- **GIVEN** 一个 `reply_mode = everyone`、`discussion_mode = unlimited` 的房间
- **WHEN** 用户只把 `reply_mode` 改为 `admin`（请求中未同时给出 `discussion_mode = single`）
- **THEN** 系统 SHALL 返回结构化错误并拒绝该请求
- **AND** 房间的 `reply_mode` 与 `discussion_mode` SHALL 均保持原值

## ADDED Requirements

### Requirement: 讨论链自动续轮与收敛

在 `discussion_mode = unlimited` 且 `reply_mode = everyone` 的房间中，一轮正常结束（`termination = "completed"`）且本轮有成员发言时，系统 SHALL 自动开启下一轮，SHALL NOT 等待用户再次发言；每轮 SHALL 由全体成员按序各得一次发言机会（admin 先），成员 SHALL 可静默（`[PASS]`）。整条讨论链 SHALL 在以下出口之一结束（按钉死的优先级判定，同一时刻多个条件成立时取优先级高者）：① `stopped`（用户请求停止）；② `completed`（房间已无成员，退化为单轮语义）；③ `mode_changed`（链中房间的 `discussion_mode` 被改回 `single` 或 `reply_mode` 不再是 `everyone`）；④ `round_limit`（当前轮达本轮预算、链不再续）；⑤ `max_rounds`；⑥ `max_turns`；⑦ `max_seconds`；⑧ `converged`（本轮 0 条成员发言且 0 次失败，且无未消费用户消息）；⑨ `all_failed`（本轮 0 条成员发言且存在失败/超时）；⑩ 取消/意外异常（`cancelled` / `error`）。链结束时系统 SHALL 在房间日志写一条对应原因的 `system` 条目（取消/异常与"房间已无成员"退化路径除外），并 SHALL 发布 `discussion_ended` 事件，携带 `chain_id`、`reason`、已完成轮数 `rounds`、进入轮数 `rounds_started`、总成员回合数 `turns`、耗时 `elapsed_seconds` 与 `status_seq`；`discussion_ended` 每条链 SHALL 至多发布一次。每轮结束 SHALL 发布 `round_ended`，携带 `chain_id`、链内轮次序号 `round_index` 与是否续轮 `chain_continues`；链内新增的 `system` 条目（续轮 / 收敛 / 停止 / 达上限 / 模式切换）SHALL 通过 `system_entry` 事件实时发布，携带 `chain_id`、`seq` 与 `text`。续轮前 SHALL 在房间日志记录 `system` 条目「讨论继续（第 k 轮）」，其 `seq` 作为该轮的 `start_seq`。**未消费用户消息**：链内到达、但在所有成员回合的切片构造之后才到达的用户消息 SHALL 记入待消费集合；存在未消费用户消息时，链 SHALL NOT 以 `converged` 结束——若安全阀仍有余量则 SHALL 强制再开一轮，否则按对应安全阀 reason 结束（消息保留在房间日志）。**待应用点名** SHALL 在某轮开局 slot 消费后立即清空，链结束随链丢弃、SHALL NOT 跨链。安全阀取值 SHALL 来自配置的 `team.discussion_max_rounds`（缺省 200）、`team.discussion_max_turns`（缺省 600）、`team.discussion_max_seconds`（缺省 6000），并 SHALL 在链启动时快照；链内成员回合总数 SHALL NOT 超过 `max_turns`，每轮上限 SHALL 取「本轮 slot 预算」与「链剩余回合额度」的较小者。系统 SHALL NOT 为"是否继续讨论"额外调用模型判定；收敛判定 SHALL 只基于本轮实际发言条数、失败条数与未消费用户消息。`discussion_mode = single` 的房间 SHALL NOT 触发本 Requirement 的任何行为。

#### Scenario: 有发言则自动续轮

- **GIVEN** 一个 `discussion_mode = unlimited` 的 3 人房间，第 1 轮 3 名成员各发言一次后本轮正常结束
- **WHEN** 编排器完成第 1 轮
- **THEN** 系统 SHALL 自动开启第 2 轮（写 `system`「讨论继续（第 2 轮）」并发布 `system_entry`）
- **AND** `round_ended` SHALL 携带 `chain_id`、`round_index = 1` 与 `chain_continues = true`
- **AND** 第 2 轮三名成员 SHALL 再次各得一次发言机会（各自可静默）

#### Scenario: 全员静默收敛

- **GIVEN** 一条讨论链运行到第 4 轮
- **WHEN** 第 4 轮全体成员都回复 `[PASS]`（0 条发言、0 次失败、无未消费用户消息）
- **THEN** 系统 SHALL 结束整条链（`reason = "converged"`）
- **AND** 房间日志 SHALL 记录 `system`「讨论已收敛（本轮全员静默）」
- **AND** SHALL 发布 `discussion_ended`（`rounds = 4`、`reason = "converged"`、`chain_id` 与当轮 `round_ended` 一致）

#### Scenario: 部分成员静默不终止

- **GIVEN** 一条讨论链的第 2 轮中成员 A 发言、成员 B 与 C 静默
- **WHEN** 第 2 轮结束
- **THEN** 本条链 SHALL 继续（`chain_continues = true`），SHALL NOT 以收敛结束

#### Scenario: 用户停止优雅结束整条链

- **GIVEN** 一条讨论链第 3 轮正在进行，用户点击「停止讨论」
- **WHEN** 当前成员回合运行结束
- **THEN** 系统 SHALL 结束当前轮（跳过剩余发言位）并结束整条链
- **AND** SHALL 写 `system`「讨论已由用户停止」并发布 `discussion_ended`（`reason = "stopped"`；`rounds = 2`、`rounds_started = 3`）

#### Scenario: 安全阀轮数到达

- **GIVEN** `team.discussion_max_rounds = 3`
- **WHEN** 第 3 轮正常结束且第 4 轮本可继续
- **THEN** 系统 SHALL 结束整条链（`reason = "max_rounds"`）
- **AND** 房间日志 SHALL 记录 `system`「讨论达安全上限结束」

#### Scenario: 安全阀回合额度截断当前轮

- **GIVEN** 一条链的剩余回合额度小于某轮 slot 预算
- **WHEN** 该轮开始
- **THEN** 本轮上限 SHALL 取剩余额度（较小者）
- **AND** 该轮达到上限后 SHALL 以 `termination = "limit"` 结束本轮，并 SHALL 以 `reason = "round_limit"` 结束整条链

#### Scenario: 安全阀墙钟到达（slot 之间检查）

- **GIVEN** 一条链的耗时达到 `team.discussion_max_seconds`
- **WHEN** 某个成员回合结束、下一成员回合尚未开始
- **THEN** 系统 SHALL 不再开启新回合，并以 `reason = "max_seconds"` 结束整条链
- **AND** SHALL NOT 打断正在运行的成员回合

#### Scenario: 讨论中插话不打断续轮

- **GIVEN** 一条讨论链第 2 轮正在进行
- **WHEN** 用户发送「@B 你再展开一下」
- **THEN** 该消息 SHALL 进入房间日志，B SHALL 插到当前位次之后发言
- **AND** 整条链 SHALL 继续自动续轮，SHALL NOT 因插话中断

#### Scenario: 未被任何成员看到的用户消息不触发收敛

- **GIVEN** 第 3 轮最后一名成员的回合已开始（其切片已构造），此时用户发来一条不含 `@` 的消息
- **WHEN** 第 3 轮因 0 条成员发言而结束
- **THEN** 系统 SHALL NOT 以 `converged` 结束（该用户消息未被任何回合看到）
- **AND** 安全阀仍有余量时 SHALL 再开一轮，使成员看到该消息
- **AND** 安全阀耗尽时 SHALL 以对应安全阀 reason 结束，消息保留在房间日志

#### Scenario: 链中切回单轮模式

- **GIVEN** 一条讨论链正在运行，房间 `discussion_mode` 被改为 `single`
- **WHEN** 当前轮结束
- **THEN** 系统 SHALL 不再续轮，并以 `reason = "mode_changed"` 结束整条链
- **AND** 房间日志 SHALL 记录 `system`「讨论模式已切换为单轮」

#### Scenario: 空成员房间退化为单轮

- **GIVEN** 一个 `discussion_mode = unlimited` 但没有任何成员的房间
- **WHEN** 用户发送消息
- **THEN** 系统 SHALL 按单轮语义结束（`round_ended(termination = "completed")`），SHALL NOT 发布 `discussion_started` / `discussion_ended`
- **AND** 房间日志 SHALL NOT 记录「讨论已收敛」

#### Scenario: 单轮模式不触发讨论链

- **GIVEN** 一个 `discussion_mode = single` 的房间
- **WHEN** 一轮正常结束且有成员发言
- **THEN** 系统 SHALL NOT 自动开启下一轮
- **AND** SHALL NOT 发布 `discussion_started` / `discussion_ended` / `system_entry`
