# subagents spec delta: 按名启动 workflow 资产的工具纳入深度闸

## MODIFIED Requirements

### Requirement: 深度到限撤 spawn 工具

当子 session 的 spawn 深度达到 `max_depth` 时，系统 SHALL 从该子 agent 的工具注册中移除 spawn 类工具（`CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent` **以及 `StartWorkflow`/`RunWorkflow`/`RunWorkflowAsset`**，后三者语义上等价于一次性拉起整张图），让子 agent 自行完成任务，而非返回错误。资产的**读取与保存**类工具（`ListWorkflowAssets`/`GetWorkflowAsset`/`SaveWorkflowAsset`）SHALL NOT 被撤除——它们既不起图也不消耗并发许可，撤除只会让深度到限的子 agent 无法保存自己刚跑完的图。

#### Scenario: 深度到限子 agent 无 spawn 工具

- **GIVEN** 一个子 session 的 spawn 深度已达到 `max_depth`
- **WHEN** 构建该子 agent 的工具注册
- **THEN** 其工具集 SHALL NOT 包含 spawn 类工具（含 `StartWorkflow`/`RunWorkflow`/`RunWorkflowAsset`）
- **AND** SHALL 保留其余工具（含只读的 `GetWorkflow`/`DeclareWorkflow`/`CancelWorkflow`）完成自身任务

#### Scenario: 深度到限仍可保存与列出资产

- **GIVEN** 一个子 session 的 spawn 深度已达到 `max_depth`，且它刚跑完一张图
- **WHEN** 构建该子 agent 的工具注册
- **THEN** 其工具集 SHALL 保留资产读取与保存类工具（`ListWorkflowAssets`/`GetWorkflowAsset`/`SaveWorkflowAsset`）
- **AND** 它 SHALL 能保存该图并列出已有资产
- **AND** 它 SHALL NOT 能按名启动一张新的图（`RunWorkflowAsset` 已撤）
