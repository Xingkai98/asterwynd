## ADDED Requirements

### Requirement: Web 支持 plan mode session

Web UI SHALL 支持创建或选择 plan mode session。

#### Scenario: Web plan mode

- **GIVEN** session 使用 plan mode
- **WHEN** 用户发送规划请求
- **THEN** 服务端 SHALL 以 plan mode 运行 AgentLoop
- **AND** 前端 SHALL 展示计划状态和最终计划说明
