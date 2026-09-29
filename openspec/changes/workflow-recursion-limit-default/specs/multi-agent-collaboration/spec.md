# multi-agent-collaboration spec delta: workflow 图级 recursion_limit 默认值调大

## MODIFIED Requirements

### Requirement: reducer 声明与图级递归上限

系统 SHALL 要求并行分支写同一结果槽时声明 reducer（无损合并），校验阶段对「多入边写同字段」无 reducer 时报 schema 错。系统 SHALL 施加图级 recursion_limit（默认 100），超限 SHALL 报错。该默认值 SHALL 可被配置项 `subagents.workflow.recursion_limit` 覆盖（显式值含小于默认值的值 SHALL 精确生效）。

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
