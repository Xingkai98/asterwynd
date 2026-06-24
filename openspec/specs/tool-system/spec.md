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

工具 SHALL 能声明 `read_only`、`dangerous` 和可选 `allowed_modes` 元数据；registry SHALL 能暴露指定工具是否 dangerous。`allowed_modes` 用于 mode-specific 工具，例如只允许在 `plan` mode 暴露和执行的 `UpdatePlan` / `ExitPlanMode`。

#### Scenario: 检查 Bash 权限

- **GIVEN** BashTool 被注册
- **WHEN** 调用 `get_sandbox("Bash")`
- **THEN** 系统 SHALL 返回该工具的 dangerous 标记

#### Scenario: mode-specific 工具

- **GIVEN** 工具声明 `allowed_modes`
- **WHEN** 当前 mode 不在该列表中
- **THEN** 系统 SHALL 不暴露该工具 schema
- **AND** 执行该工具时 SHALL 返回权限拒绝结果

### Requirement: ToolRegistry 读取当前 session mode

ToolRegistry SHALL 通过 runtime state 读取当前 session mode，而不是只依赖 AgentLoop 构造时的初始 mode。

#### Scenario: mode 切换后 schema 立即变化

- **GIVEN** ToolRegistry 当前以 `build` mode 暴露工具
- **WHEN** session mode 切换为 `read_only`
- **THEN** 下一次 `get_all_schemas()` SHALL 按 `read_only` mode 过滤工具

#### Scenario: 已生成的 tool call 在执行前重新判权

- **GIVEN** LLM 已在旧 mode 下生成 tool call
- **WHEN** 该 tool call 真正执行前 session mode 已切换为更严格的 mode
- **THEN** ToolRegistry SHALL 按最新 mode 判断权限
- **AND** 被禁止的工具 SHALL 返回权限拒绝结果

### Requirement: 工具错误边界

工具实现 SHALL 将可恢复错误转成可读字符串；协议层 SHALL NOT 因普通工具失败破坏消息链。

#### Scenario: 工具返回错误文本

- **GIVEN** 工具执行遇到可捕获异常
- **WHEN** 工具返回 `Error: ...`
- **THEN** AgentLoop SHALL 将该文本作为 tool result 追加
- **AND** 继续保持 tool-call 链合法
