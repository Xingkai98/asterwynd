## ADDED Requirements

### Requirement: Workflow 绑定 Workspace 写权限

受 Workflow Control Plane 管理的 agent run SHALL 将写权限绑定到当前 WorkItem 指定的 workspace 和 workflow version。进入 design 后，业务代码和 change 文档写入 SHALL 只允许发生在绑定 worktree；处于 gate、blocked 或 stale state 时 SHALL fail closed。

#### Scenario: Requirements 阶段禁止业务代码写入

- **GIVEN** workflow 处于 exploring 或 requirements
- **WHEN** agent 尝试修改业务代码
- **THEN** workspace policy SHALL 拒绝写入
- **AND** SHALL 提示当前阶段只允许讨论和需求 artifact 操作

#### Scenario: Design 阶段写入绑定 Worktree

- **GIVEN** workflow 已绑定 worktree A
- **WHEN** agent 尝试在 canonical main repository 写入 design artifact
- **THEN** workspace policy SHALL 拒绝写入
- **AND** SHALL 指示使用 worktree A

#### Scenario: Gate 后拒绝写入

- **GIVEN** workflow 处于任一 `ready_for_review` gate
- **WHEN** agent 尝试写文件或运行产生修改的命令
- **THEN** workspace policy SHALL 拒绝操作

#### Scenario: Stale WorkItem 拒绝写入

- **GIVEN** agent 的 WorkItem version 低于控制面当前 version
- **WHEN** agent 尝试执行写操作
- **THEN** workspace policy SHALL 拒绝操作
- **AND** SHALL 要求重新 enter 获取当前 WorkItem

#### Scenario: 非隔离 Executor 降级

- **GIVEN** executor host 无法保护控制面数据库和 approval capability
- **WHEN** workflow 为该 executor 分配任务
- **THEN** 系统 SHALL 将 enforcement level 标记为 audit-only 或拒绝执行
- **AND** SHALL NOT 宣称该环境具备强制可信 Gate

