# multi-agent-collaboration spec delta: workflow 四维预算默认无上限

## MODIFIED Requirements

### Requirement: workflow 级四维度总预算

系统 SHALL 对一个 workflow run 施加四维度总预算：`max_total_tokens` / `max_total_cost_usd` / `max_total_runs` / `max_wall_time_s`。四维度**默认均为 `0`（不限）**——只有显式配置（`subagents.workflow.budget.*`）才设上限，`0` SHALL 表示「该维度不限」，但 `max_total_runs=0` SHALL NOT 解除 C2 的 `max_runs` 结构闸。配置 `subagents` / `subagents.workflow` / `subagents.workflow.budget` 中任一段落**键存在但值为 `null`** 时，系统 SHALL 报配置错误（`ConfigError`），SHALL NOT 静默视为「未配置 = 不限」。任一维度超限时系统 SHALL 停止派发新节点、取消排队中未执行的 run、drain 已启动的 run、并将根节点标记为 `budget_exceeded`。

#### Scenario: 未配置预算时不设上限

- **GIVEN** 一份未配置 `subagents.workflow.budget` 的配置
- **WHEN** 一个 workflow run 的累计 token / cost / 挂钟时间超过旧默认值（200k tokens / 5.0 USD / 1800 s）
- **THEN** 系统 SHALL NOT 因预算中止派发
- **AND** workflow SHALL 正常跑完，envelope 的 `budget.exceeded` SHALL 为 `false`
- **AND** run 数维度 SHALL NOT 被本 Requirement 中止（仍受 C2 `max_runs` 结构闸约束，见下方 Scenario）

#### Scenario: token 预算超限停止派发

- **GIVEN** 一个 workflow run 的累计 token 达到显式配置的 `max_total_tokens`
- **WHEN** 调度器尝试派发下一个节点
- **THEN** 系统 SHALL 停止派发新节点
- **AND** 已启动的 run SHALL drain 到终态
- **AND** 根节点 SHALL 标记 `budget_exceeded`

#### Scenario: runs 预算派发前预扣拒绝

- **GIVEN** 一个 workflow 的累计 run 数达到显式配置的 `max_total_runs`
- **WHEN** 调度器预扣下一个 run 的预算
- **THEN** 系统 SHALL 拒绝派发
- **AND** envelope SHALL 报 `budget.exceeded = true`

#### Scenario: 超限出口不逃出 run

- **GIVEN** 任一维度预算超限触发 stop_new
- **WHEN** 调度器收敛
- **THEN** 系统 SHALL 返回 envelope（`status="budget_exceeded"`）
- **AND** SHALL NOT 向父 agent 抛未捕获异常

#### Scenario: 段落级 null 判为配置错误

- **GIVEN** 一份配置在 `subagents.workflow.budget`（或 `subagents.workflow` / `subagents`）处**写了键但值为 `null`**
- **WHEN** 加载配置
- **THEN** 系统 SHALL 抛 `ConfigError`
- **AND** SHALL NOT 静默把该段视为「未配置」（否则会静默把四维预算全部置为不限）

#### Scenario: 预算不限不解除 C2 结构闸

- **GIVEN** 四维度预算均未配置（默认不限）
- **WHEN** 一个 workflow 的累计 run 数达到 C2 的 `max_runs`
- **THEN** 系统 SHALL 仍按 C2 结构闸拒绝派发（reason `max_runs`）
- **AND** SHALL NOT 因预算为「不限」而放行超限的 run 数
