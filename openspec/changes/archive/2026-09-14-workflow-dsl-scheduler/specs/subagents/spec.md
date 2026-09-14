# subagents spec delta: Workflow DSL 调度器

## MODIFIED Requirements

### Requirement: 深度到限撤 spawn 工具

当子 session 的 spawn 深度达到 `max_depth` 时，系统 SHALL 从该子 agent 的工具注册中移除 spawn 类工具（`CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent` **以及 `StartWorkflow`/`RunWorkflow`**，后两者语义上等价于一次性拉起整张图），让子 agent 自行完成任务，而非返回错误。

#### Scenario: 深度到限子 agent 无 spawn 工具

- **GIVEN** 一个子 session 的 spawn 深度已达到 `max_depth`
- **WHEN** 构建该子 agent 的工具注册
- **THEN** 其工具集 SHALL NOT 包含 spawn 类工具（含 `StartWorkflow`/`RunWorkflow`）
- **AND** SHALL 保留其余工具（含只读的 `GetWorkflow`/`DeclareWorkflow`/`CancelWorkflow`）完成自身任务

### Requirement: 累计 spawn 计数上限

系统 SHALL 对累计 spawn 计数（create 与每次 run 各计一次）执行 `max_spawns`（默认 200）上限，超限时拒绝新的 spawn。计数的 orchestration 边界 SHALL 是 workflow run（桶键 = `workflow_id`）：一个 workflow run 的展开项共享一个桶，嵌套 workflow 各自独立成桶；无 workflow 的主 loop SHALL 沿用按 manager 生命周期的累计语义（每 turn 复位归后续 change）。

#### Scenario: 嵌套 workflow 各自独立成桶

- **GIVEN** workflow A 的某个节点内又声明并启动了 workflow B
- **WHEN** B 在其节点里 spawn 子 agent
- **THEN** 这些 spawn SHALL 计入 B 自己的桶
- **AND** SHALL NOT 因 A 的累计消耗而失败
