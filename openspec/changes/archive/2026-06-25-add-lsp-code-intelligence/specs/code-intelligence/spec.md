## ADDED Requirements

### Requirement: 提供 LSP code intelligence provider

系统 SHALL 能通过显式配置的 LSP server 提供 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics 能力。配置 SHALL 挂在 `CodeIntelligenceConfig.lsp` 子字段下，按 language 匹配 server（一种语言一个 server）。

#### Scenario: 查询定义位置

- **GIVEN** workspace 中某文件有可用 LSP server
- **WHEN** agent 请求某个位置的 definition
- **THEN** 系统 SHALL 返回 LSP server 提供的定义位置
- **AND** SHALL 对结果做受限长度输出

### Requirement: LSP server 进程级单例与按需文档同步

系统 SHALL 按 (language, workspace_root) 缓存 LSP client 单例，第一次请求时 lazy 启动（initialize → initialized），agent run 结束时统一 shutdown。文档同步 SHALL 采用按需 didOpen（只在被查询文件未同步时才同步），Write/Edit 修改文件后 SHALL 通过 didChange 同步给 LSP。

#### Scenario: 首次请求触发启动

- **GIVEN** workspace 中某语言首次请求 LSP 操作
- **WHEN** agent 请求该语言的 definition
- **THEN** 系统 SHALL lazy 启动对应 LSP server
- **AND** SHALL 完成 initialize 握手后再发请求

#### Scenario: 重复请求复用单例

- **GIVEN** 同一 (language, workspace_root) 的 LSP client 已启动
- **WHEN** agent 再次请求 LSP 操作
- **THEN** 系统 SHALL 复用已有 client
- **AND** SHALL NOT 重复 initialize

### Requirement: LSP 能力可降级

系统 SHALL 在 LSP server 不可用、未配置、启动失败或请求超时时返回可读错误，而不是让 AgentLoop 崩溃。

#### Scenario: 没有可用 LSP server

- **GIVEN** workspace 中目标文件没有配置可用 LSP server
- **WHEN** agent 请求 LSP 操作
- **THEN** 系统 SHALL 返回说明性错误
- **AND** SHALL 保留 repo map / tree-sitter 等较轻能力可用

#### Scenario: 无 server 时 diagnostics 快速跳过

- **GIVEN** Write/Edit 成功修改文件但目标语言没有可用 LSP server
- **WHEN** 修改工具请求 diagnostics
- **THEN** 系统 SHALL 快速跳过 diagnostics 调用
- **AND** SHALL NOT 等待超时
- **AND** SHALL NOT 影响 Write/Edit 本身的成功返回

### Requirement: LSP diagnostics 进入验证反馈

系统 SHALL 能在文件修改后请求 LSP diagnostics，并将相关诊断以可读形式反馈给 agent。

#### Scenario: 编辑后产生诊断

- **GIVEN** agent 修改文件后 LSP server 返回诊断
- **WHEN** 修改工具返回结果
- **THEN** 工具结果 SHALL 包含相关 diagnostics 摘要
- **AND** SHALL 标识文件和位置
- **AND** SHALL 对诊断做数量和字符截断
