## MODIFIED Requirements

### Requirement: 支持显式 agent mode

系统 SHALL 支持显式 agent mode，并用 mode 决定工具可见性、工具执行权限和运行记录。`plan` mode SHALL 是可执行 mode，而不是仅文档预留。

#### Scenario: plan mode 只读运行

- **GIVEN** AgentLoop 以 `plan` mode 运行
- **WHEN** 系统暴露工具 schema
- **THEN** schema SHALL 只包含只读工具
- **AND** 系统 SHALL 拒绝写入和 dangerous 工具调用

#### Scenario: plan mode 生成计划

- **GIVEN** 用户请求先规划任务
- **WHEN** AgentLoop 以 `plan` mode 完成
- **THEN** 系统 SHALL 允许模型通过自然语言继续讨论计划
- **AND** MAY 生成 Markdown Plan Document 草案
- **AND** 在计划定稿时 SHALL 生成最终 Markdown Plan Document
- **AND** SHALL 将 Plan Document 中的高层步骤同步为结构化 planning state
- **AND** 最终回复 SHALL 给出自然语言计划说明

#### Scenario: plan mode 提交计划后不自动执行

- **GIVEN** AgentLoop 以 `plan` mode 提交了 Plan Document
- **WHEN** 本轮运行继续到最终回复
- **THEN** 系统 SHALL NOT 自动切换到 `build` mode
- **AND** SHALL NOT 执行计划中的写入、编辑或命令步骤
