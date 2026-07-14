## ADDED Requirements

### Requirement: Agent Runtime 作为 Workflow Executor

当 Agent runtime 由 Workflow Control Plane 管理时，每个 run SHALL 在处理用户任务前通过 adapter 获取 WorkItem，并在结束时提交 WorkResult。Agent session snapshot MAY 保存 workflow id 和最后观察到的 version，但 SHALL NOT 成为 workflow 状态 source of truth。

#### Scenario: 运行前恢复 Workflow 上下文

- **GIVEN** session 绑定一个 active workflow
- **WHEN** Agent runtime 开始新 run
- **THEN** adapter SHALL 调用 workflow enter
- **AND** runtime SHALL 使用 WorkItem 中的 workspace、允许操作、phase 和 next action

#### Scenario: Session 快照状态过期

- **GIVEN** session snapshot 记录 workflow version 10
- **AND** 控制面当前 version 为 12
- **WHEN** session 恢复
- **THEN** runtime SHALL 使用控制面 version 12
- **AND** SHALL NOT 用 session snapshot 回写旧状态

#### Scenario: Gate 阻止 Agent Run

- **GIVEN** WorkItem 标记 waiting_for_human
- **WHEN** Agent runtime 准备执行工具或修改文件
- **THEN** runtime SHALL 停止自动执行
- **AND** SHALL 只展示 gate 状态和所需人工操作

#### Scenario: Runtime 提交执行结果

- **WHEN** Agent runtime 完成当前 WorkItem
- **THEN** adapter SHALL 提交 WorkResult、artifact refs 和安全的 evidence summary
- **AND** runtime SHALL 等待控制面返回 accepted、rejected、blocked 或 gate_reached

