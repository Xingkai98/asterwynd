## ADDED Requirements

### Requirement: browser tools 声明权限元数据

Browser tools SHALL 声明权限元数据，并受 agent mode policy 控制。

#### Scenario: read-only mode 使用 browser read tool

- **GIVEN** browser read tool 被标记为 read-only
- **WHEN** read-only mode 暴露工具 schema
- **THEN** 系统 MAY 暴露该 browser read tool
- **AND** SHALL NOT 暴露 destructive 或 credential-mutating browser tool
