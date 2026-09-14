# multi-agent-collaboration spec delta: Workflow 级预算与成本归因

## ADDED Requirements

### Requirement: workflow 级四维度总预算

系统 SHALL 对一个 workflow run 施加四维度总预算：`max_total_tokens` / `max_total_cost_usd` / `max_total_runs` / `max_wall_time_s`（默认 200k / 5.0 / 300 / 1800，可配置；任一维度 `0` SHALL 表示「该维度不限」，但 `max_total_runs=0` SHALL NOT 解除 C2 的 `max_runs` 结构闸）。任一维度超限时系统 SHALL 停止派发新节点、取消排队中未执行的 run、drain 已启动的 run、并将根节点标记为 `budget_exceeded`。

#### Scenario: token 预算超限停止派发

- **GIVEN** 一个 workflow run 的累计 token 达到 `max_total_tokens`
- **WHEN** 调度器尝试派发下一个节点
- **THEN** 系统 SHALL 停止派发新节点
- **AND** 已启动的 run SHALL drain 到终态
- **AND** 根节点 SHALL 标记 `budget_exceeded`

#### Scenario: runs 预算派发前预扣拒绝

- **GIVEN** 一个 workflow 的累计 run 数达到 `max_total_runs`
- **WHEN** 调度器预扣下一个 run 的预算
- **THEN** 系统 SHALL 拒绝派发
- **AND** envelope SHALL 报 `budget.exceeded = true`

#### Scenario: 超限出口不逃出 run

- **GIVEN** 任一维度预算超限触发 stop_new
- **WHEN** 调度器收敛
- **THEN** 系统 SHALL 返回 envelope（`status="budget_exceeded"`）
- **AND** SHALL NOT 向父 agent 抛未捕获异常

### Requirement: 成本归因四维账单

`CostLedger` SHALL 增四维成本归因：by_workflow / by_node / by_depth / by_edge。每个 LLM 调用 SHALL 携带其 workflow_id / node_id / depth / edge 归因键，使系统能回答「哪个节点最贵、哪层重复 token 最多、动态 vs 固定 pattern 差多少」。不带归因键的记录 SHALL 保持既有 by_session/by_phase/by_tool 三维账单不变。`by_depth` 的分层口径 SHALL 为 workflow 图距（0=leaf / 1=shard / 2=domain / 3+=root），与 `spawn_depth` 无关。归因分桶值 SHALL round 到 9 位小数、tokens 口径为 input+output（不含 cache）、cost 单位为 USD、未知模型 SHALL 标 `estimated: true`。

#### Scenario: 找出最贵节点

- **GIVEN** 一个含 N 个节点的 workflow run 完成后
- **WHEN** 查询 `CostLedger.bill()` 的 `by_node` 分桶
- **THEN** 系统 SHALL 返回每个节点的 token/cost 聚合
- **AND** SHALL 能定位最贵的节点

#### Scenario: 按图距归因层级成本

- **GIVEN** 一个 leaf→shard→domain→root 的分层汇聚 workflow 完成后
- **WHEN** 查询 `bill()` 的 `by_depth` 分桶
- **THEN** 系统 SHALL 按图距分桶（0/1/2/3+）
- **AND** SHALL 能定位重复 token 最多的层

### Requirement: 动态 route 条件源

route 节点的 `when` SHALL 支持 `$ref:<node_id>:<slot>` 引用上游结果槽；运行时解析 SHALL 只读已声明/已落盘的 `NodeState.slots`，SHALL NOT 执行模型生成代码。`$ref` 解析出的槽值 SHALL 取首个非空行作为期望标签，SHALL 传入 `matches_route` 做行首匹配。`$ref` 引用的 slot 无键命中 SHALL 视为不匹配，SHALL 保留 `default` 兜底。

#### Scenario: $ref 引用命中分支

- **GIVEN** 一个 route 节点的 `when` 为 `$ref:reviewer:verdict` 且上游 reviewer 的 verdict 槽为 "APPROVED"
- **WHEN** route 执行
- **THEN** 系统 SHALL 命中该 case 的目标边
- **AND** SHALL NOT 匹配字面文本标签

#### Scenario: $ref 槽缺失走 default

- **GIVEN** 一个 route 节点的 `when` 为 `$ref:planner:items` 但上游无 `items` 槽
- **WHEN** route 执行
- **THEN** 系统 SHALL 视为不匹配
- **AND** SHALL 保留 `default` 兜底（不报错，diagnostics 记录未命中原因）

### Requirement: 动态 foreach 跨层 source

foreach 节点的 `source` SHALL 支持跨层递归解析（沿数据边向上解析上游产出，优先读 source 节点自身 `result` 槽、无唯一数据上游则报 schema 歧义）；环回边（source 指向 route 参与环内）SHALL 在校验期拒绝。`source_field` SHALL 只应用一次。`max_items=0` SHALL 表示「不静态截断、展开到图级 run 预算耗尽为止」。

#### Scenario: 跨层 source 递归解析

- **GIVEN** 一个 foreach 节点的 `source` 指向一个「自身还有数据上游」的 aggregate 节点
- **WHEN** foreach 执行
- **THEN** 系统 SHALL 先递归解析该 aggregate 的上游产出
- **AND** 再取 `source_field` 展开集合

#### Scenario: max_items=0 按剩余预算截断

- **GIVEN** 一个 foreach 节点 `max_items=0` 且图级 run 预算未耗尽
- **WHEN** foreach 执行
- **THEN** 系统 SHALL 展开全部集合项（不做静态截断）
- **AND** SHALL 在剩余 run/节点预算耗尽时按剩余容量截断停止派发
