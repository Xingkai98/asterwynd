## ADDED Requirements

### Requirement: 子 agent 工具权限受 mode policy 约束

子 agent 暴露的工具 SHALL 受其 mode policy 约束，默认不得获得比父 agent 更高的工具权限。

#### Scenario: 父 agent 为 read-only

- **GIVEN** 父 agent 以 read-only mode 运行
- **WHEN** 创建子 agent
- **THEN** 子 agent SHALL NOT 获得写入或 dangerous 工具权限
