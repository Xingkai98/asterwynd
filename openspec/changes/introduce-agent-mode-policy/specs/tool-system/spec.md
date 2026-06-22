## ADDED Requirements

### Requirement: 工具暴露受 agent mode 约束

ToolRegistry 或工具集合构造层 SHALL 根据当前 agent mode 决定哪些工具 schema 暴露给 LLM，并在执行层拒绝 mode 不允许的工具调用。

#### Scenario: mode 过滤工具 schema

- **GIVEN** 当前 mode 不允许某个工具
- **WHEN** 调用 `get_all_schemas()`
- **THEN** 返回的 schema SHALL 不包含该工具

#### Scenario: 执行被 mode 禁止的工具

- **GIVEN** 工具调用请求命中当前 mode 禁止的工具
- **WHEN** registry 执行该 tool call
- **THEN** 系统 SHALL 返回可读权限错误
- **AND** SHALL NOT 破坏 tool-call 消息链
