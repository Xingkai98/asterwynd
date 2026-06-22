## MODIFIED Requirements

### Requirement: 模式预留不得冒充实现

系统 SHALL 将尚未完整实现的 agent mode 标注为预留或部分实现，直到对应 change 被接受并实现。

#### Scenario: 文档描述未来模式

- **GIVEN** 文档或路线图提到未来运行模式
- **WHEN** 这些模式尚无代码入口或测试
- **THEN** 规格 SHALL 标注为预留或未实现

## ADDED Requirements

### Requirement: 支持显式 agent mode

系统 SHALL 支持显式 agent mode，并用 mode 决定工具可见性、工具执行权限和运行记录。初始 mode SHALL 至少包含 `read_only`、`build`、`plan` 和 `bypass`。

#### Scenario: read-only mode 禁止修改

- **GIVEN** AgentLoop 以 `read_only` mode 运行
- **WHEN** 系统向 LLM 暴露工具 schema
- **THEN** schema SHALL 不包含写入工具和 dangerous 工具
- **AND** 直接执行被禁止工具 SHALL 返回权限错误

#### Scenario: build mode 保持 coding agent 能力

- **GIVEN** AgentLoop 以 `build` mode 运行
- **WHEN** 系统构造工具集合
- **THEN** 系统 SHALL 暴露受 WorkspacePolicy 约束的读取、编辑、搜索、diff 和验证命令工具

#### Scenario: plan 和 bypass mode 先定义边界

- **GIVEN** `plan` 或 `bypass` mode 被文档引用
- **WHEN** 对应完整行为尚未实现
- **THEN** 系统 SHALL 明确标注其约束和未交付部分
