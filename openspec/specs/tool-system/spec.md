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

工具权限模型 SHALL 区分工具能力、风险等级和来源元数据。工具能力描述 tool 能做什么，风险等级描述默认安全风险，来源元数据描述 tool 从哪里来；三者 SHALL NOT 互相替代。系统 SHALL 在迁移期保留现有 `read_only`、`dangerous` 和可选 `allowed_modes` 行为，并能从旧字段推导新权限元数据。`dangerous` 是 legacy compatibility flag，不表示工具来源。`allowed_modes` 用于 mode-specific 工具，例如只允许在 `plan` mode 暴露和执行的 `UpdatePlan` / `ExitPlanMode`。

#### Scenario: 检查 Bash 权限

- **GIVEN** BashTool 被注册
- **WHEN** 调用 `get_sandbox("Bash")`
- **THEN** 系统 SHALL 返回该工具的 dangerous 标记
- **AND** Bash 工具 SHALL 具有 command_execute capability、high risk level 和 builtin origin

#### Scenario: 外部来源不直接等同高风险

- **GIVEN** 一个 tool 的 origin 是 `mcp`
- **AND** 该 tool 被明确标注为 low risk read-only capability
- **WHEN** ModePolicy 判定该 tool 是否允许
- **THEN** 系统 SHALL NOT 仅因为 origin 是 `mcp` 而拒绝该 tool

#### Scenario: legacy read-only tool

- **GIVEN** 一个旧工具只声明 `read_only=True` 且 `dangerous=False`
- **WHEN** 系统读取该工具权限元数据
- **THEN** 系统 SHALL 将其视为 low risk read capability 的兼容工具

#### Scenario: legacy dangerous tool

- **GIVEN** 一个旧工具声明 `dangerous=True`
- **WHEN** 系统读取该工具权限元数据
- **THEN** 系统 SHALL 将其视为 high risk command execution 工具

#### Scenario: mode-specific 工具

- **GIVEN** 工具声明 `allowed_modes`
- **WHEN** 当前 mode 不在该列表中
- **THEN** 系统 SHALL 不暴露该工具 schema
- **AND** 执行该工具时 SHALL 返回权限拒绝结果

### Requirement: Tool permission decision SHALL support approval

工具权限判定 SHALL 返回 `allow`、`deny` 或 `require_approval`，而不是只返回 boolean。系统 SHALL 在 schema 暴露和执行前重新判权时使用同一判定语义。需要审批的工具 SHALL 对模型可见，但不得在缺少批准时执行。

#### Scenario: 工具可直接执行

- **GIVEN** 一个 tool 的 capability 被当前 permission profile 允许
- **AND** 该 tool 的 risk level 不超过 profile 的 auto-approve 阈值
- **WHEN** 系统判定该 tool 权限
- **THEN** 判定结果 SHALL 是 `allow`

#### Scenario: 工具需要用户审批

- **GIVEN** 一个 tool 的 capability 被当前 permission profile 允许
- **AND** 该 tool 的 risk level 超过 profile 的 auto-approve 阈值
- **AND** 该 tool 的 risk level 不超过 profile 的 approval-required 阈值
- **WHEN** 系统判定该 tool 权限
- **THEN** 判定结果 SHALL 是 `require_approval`

#### Scenario: 工具被拒绝

- **GIVEN** 一个 tool 的 capability 不被当前 permission profile 允许
- **OR** 该 tool 命中当前 permission profile 的 denied tools
- **WHEN** 系统判定该 tool 权限
- **THEN** 判定结果 SHALL 是 `deny`

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

### Requirement: 子 session runtime 工具按职责拆分

子 session runtime 工具 SHALL 按窄职责拆分，而不是复用一个带 `action` 参数的大工具。当前模型至少包含创建子 session、启动子 run、列出子 session、获取子 run、取消子 run 和 inspect transcript 这些能力。

#### Scenario: 暴露子 session runtime 工具

- **GIVEN** 顶层 AgentLoop 显式开启子 session 工具
- **WHEN** ToolRegistry 暴露工具 schema
- **THEN** 系统 SHALL 暴露窄职责工具集合
- **AND** SHALL NOT 暴露单个 `ManageSubagent(action=...)` 风格的大工具

### Requirement: 子 transcript inspect 工具默认受限

父 agent 查看子 session transcript 的能力 SHALL 通过单独 inspect 工具提供，并默认限制返回范围，例如摘要或最近 `N` 条消息。

#### Scenario: 查看子 run 最近消息

- **GIVEN** 父 agent 需要检查某个子 run 最近的执行情况
- **WHEN** 调用 transcript inspect 工具且提供范围参数
- **THEN** 系统 SHALL 返回受限范围内的消息
- **AND** SHALL NOT 默认返回整份子 transcript

### Requirement: ToolRegistry 支持 MCP-backed tools

ToolRegistry SHALL 能注册由 MCP adapter 包装的工具，并按普通 Tool 一样暴露 schema、执行调用、执行 mode policy 判定和返回字符串结果。

#### Scenario: 执行 MCP-backed tool

- **GIVEN** registry 中存在 MCP-backed tool
- **WHEN** 调用 `execute(tool_call)`
- **THEN** registry SHALL 通过 MCP adapter 执行远端工具
- **AND** 返回字符串结果

#### Scenario: MCP-backed tool 需要审批

- **GIVEN** registry 中存在 high risk MCP-backed tool
- **AND** 当前 mode policy 要求审批
- **WHEN** 调用 `execute(tool_call)` 且未传入 approval
- **THEN** registry SHALL 返回 approval required 文本
- **AND** SHALL NOT 调用远端 MCP server

### Requirement: browser tools 声明权限元数据

Browser tools SHALL 声明权限元数据（capability=BROWSER_CONTROL、risk_level=MEDIUM、origin=BROWSER），并受 agent mode policy 控制。

#### Scenario: build mode 下 browser tools 可见

- **GIVEN** BrowserConfig.enabled 为 true 且 playwright 可用
- **WHEN** build mode 暴露工具 schema
- **THEN** 系统 SHALL 暴露所有 browser tools
- **AND** 截图等 MEDIUM risk 工具 SHALL 需要审批

#### Scenario: read-only mode 拒绝 browser tools

- **GIVEN** browser tool 声明 BROWSER_CONTROL capability
- **WHEN** read_only mode 暴露工具 schema
- **THEN** 系统 SHALL NOT 暴露 browser tools
