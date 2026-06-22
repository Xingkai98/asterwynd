## ADDED Requirements

### Requirement: 提供 LSP code intelligence provider

系统 SHALL 能通过显式配置的 LSP server 提供 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics 能力。

#### Scenario: 查询定义位置

- **GIVEN** workspace 中某文件有可用 LSP server
- **WHEN** agent 请求某个位置的 definition
- **THEN** 系统 SHALL 返回 LSP server 提供的定义位置
- **AND** SHALL 对结果做受限长度输出

### Requirement: LSP 能力可降级

系统 SHALL 在 LSP server 不可用、未配置、启动失败或请求超时时返回可读错误，而不是让 AgentLoop 崩溃。

#### Scenario: 没有可用 LSP server

- **GIVEN** workspace 中目标文件没有配置可用 LSP server
- **WHEN** agent 请求 LSP 操作
- **THEN** 系统 SHALL 返回说明性错误
- **AND** SHALL 保留 repo map / tree-sitter 等较轻能力可用

### Requirement: LSP diagnostics 进入验证反馈

系统 SHALL 能在文件修改后请求 LSP diagnostics，并将相关诊断以可读形式反馈给 agent。

#### Scenario: 编辑后产生诊断

- **GIVEN** agent 修改文件后 LSP server 返回诊断
- **WHEN** 修改工具返回结果
- **THEN** 工具结果 SHALL 包含相关 diagnostics 摘要
- **AND** SHALL 标识文件和位置
