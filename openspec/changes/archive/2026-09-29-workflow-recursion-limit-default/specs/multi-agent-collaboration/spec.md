# multi-agent-collaboration spec delta: workflow 图级 recursion_limit 默认值调大

## MODIFIED Requirements

### Requirement: reducer 声明与图级递归上限

系统 SHALL 要求并行分支写同一结果槽时声明 reducer（无损合并），校验阶段对「多入边写同字段」无 reducer 时报 schema 错。系统 SHALL 施加图级 recursion_limit（默认 100），超限 SHALL 报错。该默认值 SHALL 可被配置项 `subagents.workflow.recursion_limit` 覆盖（显式值含小于默认值的值 SHALL 精确生效）。当超限的触发图由模板产出且其构造携带 `max_rounds` 声明时，系统 SHALL 在 `graph_recursion_exceeded` 的诊断中如实报告 `declared_max_rounds`（声明值）、`rounds_actually_run`（实际轮数）与 `limit_source`（界来自 `recursion_limit`，及其数值），使模型能判断截断由自身 `max_rounds` 声明过大导致并据此调整；纯 DSL 图（无 `max_rounds` 概念）时这些字段 SHALL 为 `null`。系统 SHALL NOT 因「`max_rounds` 大于图级上限」而在编译期拒绝（其换算比依赖拓扑，静态界会误判）。

#### Scenario: 图级递归上限

- **GIVEN** 一个 workflow 的执行步数达到 recursion_limit
- **WHEN** 调度器尝试再前进一步
- **THEN** 系统 SHALL 报 GraphRecursionError
- **AND** SHALL NOT 无限循环

#### Scenario: 默认配置不掐断迭代式任务

- **GIVEN** 一份未显式配置 `subagents.workflow.recursion_limit` 的配置（默认 100）
- **WHEN** 一个 `route` 回边循环的执行步数超过旧默认值 25 但未超过 100
- **THEN** 系统 SHALL NOT 因图级 recursion_limit 终止该图
- **AND** 该图的终点 SHALL 由 route 节点自身的 `max_routes` 决定（超限时 reason SHALL 为 `max_routes`，SHALL NOT 为 `recursion_limit`）
- **AND** 这 SHALL 使「调大 `max_rounds`」在默认配置下重新生效

#### Scenario: 显式更小的 recursion_limit 仍精确生效

- **GIVEN** 一份显式配置 `subagents.workflow.recursion_limit: 7` 的配置
- **WHEN** 一个 workflow 的执行步数达到 7
- **THEN** 系统 SHALL 按该显式值报 GraphRecursionError（reason `recursion_limit`）
- **AND** SHALL NOT 回退到默认值 100

#### Scenario: max_rounds 声明被图级上限截断时诊断可行动

- **GIVEN** `template="peer-review"` 声明 `max_rounds=25`，其图在 `recursion_limit=25` 下实际约 9 轮即撞顶
- **WHEN** 该图以 `graph_recursion_exceeded` 终止
- **THEN** 诊断 SHALL 含 `declared_max_rounds=25`、`rounds_actually_run`（实际轮数）与 `limit_source`（`recursion_limit`=25）
- **AND** 模型 SHALL 能据此判断是自身声明过大，而非只看到「超了递归上限」这一无法行动的提示
