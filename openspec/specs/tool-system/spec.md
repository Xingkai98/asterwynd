# tool-system 规格

## Purpose

定义工具基类、schema 暴露、注册、执行和权限元数据。当前实现位于 `agent/tools/base.py` 和 `agent/tools/registry.py`。

## Requirements

### Requirement: 工具必须暴露 OpenAI-compatible function schema

每个 Tool SHALL 提供名称、描述和 JSON Schema 参数，并由 `get_schema()` 转换为 `type: function` 的工具声明。

#### Scenario: 获取所有工具 schema

- **GIVEN** ToolRegistry 已注册多个工具
- **WHEN** 调用 `get_all_schemas()`
- **THEN** 系统 SHALL 返回每个工具的 function schema

### Requirement: 工具注册按名称索引

ToolRegistry SHALL 按工具名称注册和查找工具。

#### Scenario: 注册工具

- **GIVEN** 一个 Tool 实例
- **WHEN** 调用 `register(tool)`
- **THEN** registry SHALL 使用 `tool.name` 作为键保存该工具

### Requirement: 工具执行使用 ToolCall

ToolRegistry SHALL 接收包含 id、name 和 arguments 的 ToolCall，并把 arguments 展开传入对应工具。

#### Scenario: 执行已注册工具

- **GIVEN** registry 中存在目标工具
- **WHEN** 调用 `execute(tool_call)`
- **THEN** registry SHALL 调用该工具的 `execute(**arguments)`
- **AND** 返回工具输出字符串

### Requirement: 工具权限元数据

工具 SHALL 能声明 `read_only` 和 `dangerous` 元数据；registry SHALL 能暴露指定工具是否 dangerous。

#### Scenario: 检查 Bash 权限

- **GIVEN** BashTool 被注册
- **WHEN** 调用 `get_sandbox("Bash")`
- **THEN** 系统 SHALL 返回该工具的 dangerous 标记

### Requirement: 工具错误边界

工具实现 SHALL 将可恢复错误转成可读字符串；协议层 SHALL NOT 因普通工具失败破坏消息链。

#### Scenario: 工具返回错误文本

- **GIVEN** 工具执行遇到可捕获异常
- **WHEN** 工具返回 `Error: ...`
- **THEN** AgentLoop SHALL 将该文本作为 tool result 追加
- **AND** 继续保持 tool-call 链合法
