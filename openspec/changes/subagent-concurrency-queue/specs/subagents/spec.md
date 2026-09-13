# subagents spec delta: 并发队列化

## ADDED Requirements

### Requirement: 跨子 session 并发队列化

系统 SHALL 支持多个子 session 并发运行，并对物理并发施加有界队列约束：同时执行 LLM/tool 的子 run 数 SHALL 不超过 `max_active`（默认 5）；超过 `max_active` 的 spawn SHALL 进入队列而非失败；排队中的 run 数 SHALL 不超过 `max_queued_runs`（默认 20），队列满时 SHALL 返回明确 `queue_full` 信号。

#### Scenario: 瞬时并发超限进入队列

- **GIVEN** 当前正在执行的子 run 数已达到 `max_active`
- **WHEN** 调用 `RunSubagent` 创建新的子 run
- **THEN** 系统 SHALL 将该 run 标记为 `queued` 并返回 `run_id`
- **AND** 当有执行槽释放时 SHALL 按队列顺序放行

#### Scenario: 队列满返回 queue_full

- **GIVEN** 排队中的 run 数已达到 `max_queued_runs`
- **WHEN** 再次调用 `RunSubagent`
- **THEN** 系统 SHALL 返回 `queue_full` 信号而非无限排队或失败

### Requirement: 并发许可绑定执行而非等待

系统的并发许可 SHALL 只绑定「实际 LLM/tool 执行」阶段，SHALL NOT 覆盖父 agent 阻塞等待子 agent 的等待区间。父 agent 等待子 run 时 SHALL NOT 占用执行许可。

#### Scenario: 父等待子不占用许可

- **GIVEN** 父 agent 已发起多个子 run 并阻塞等待全部完成
- **WHEN** 父 agent 处于等待状态
- **THEN** 父 agent SHALL NOT 占用并发许可
- **AND** 所有子 run 均能获得许可并完成（不自我饥饿）

### Requirement: 深度到限撤 spawn 工具

当子 session 的 spawn 深度达到 `max_depth` 时，系统 SHALL 从该子 agent 的工具注册中移除 spawn 类工具（`CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent`），让子 agent 自行完成任务，而非返回错误。

#### Scenario: 深度到限子 agent 无 spawn 工具

- **GIVEN** 一个子 session 的 spawn 深度已达到 `max_depth`
- **WHEN** 构建该子 agent 的工具注册
- **THEN** 其工具集 SHALL NOT 包含 spawn 类工具
- **AND** SHALL 保留其余工具完成自身任务

### Requirement: 累计 spawn 计数上限

系统 SHALL 对每次 orchestration（根 run 起算）维护累计 spawn 计数，并 SHALL 在该计数超过 `max_spawns`（默认 200）时拒绝新的 spawn。

#### Scenario: 累计 spawn 超限拒绝

- **GIVEN** 某 orchestration 的累计 spawn 计数已达 `max_spawns`
- **WHEN** 再次创建或运行子 agent
- **THEN** 系统 SHALL 拒绝该请求
- **AND** 不影响既有运行中的子 run

### Requirement: 子 session 显式父子身份

`SubagentSessionRecord` SHALL 维护 `parent_run_id`/`workflow_id`/`node_id`/`depth` 显式字段，使延迟执行的子 run 仍能追溯其逻辑父子关系与归属。

#### Scenario: 排队延迟执行的子 run 保留身份

- **GIVEN** 一个子 run 在队列中延迟到父 run 结束后才执行
- **WHEN** 读取该子 run 的身份信息
- **THEN** 系统 SHALL 返回其正确的 `parent_run_id` 与 `depth`
- **AND** SHALL 返回其所属 `workflow_id`（若存在）

## MODIFIED Requirements

### Requirement: 多个子 session 可并发，同一子 session 内 run 串行

系统 SHALL 支持多个子 session 同时存在并并发运行（并发受「跨子 session 并发队列化」约束）。同一个 `subagent_id` 任一时刻 SHALL 最多只有一个 active run；再次运行同一子 session 仍 SHALL 拒绝并等待或取消当前 run（不进入跨 session 队列）。

#### Scenario: 已有 active run 时再次运行同一子 session

- **GIVEN** 某个子 session 当前已有运行中的子 run
- **WHEN** 再次调用 `RunSubagent`
- **THEN** 系统 SHALL 拒绝该请求
- **AND** SHALL 要求先等待或取消当前 run
