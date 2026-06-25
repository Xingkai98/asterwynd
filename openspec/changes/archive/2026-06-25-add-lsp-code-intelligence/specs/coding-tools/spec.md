## ADDED Requirements

### Requirement: 提供六个独立只读 LSP 工具

系统 SHALL 提供六个独立只读 LSP 工具：`LspDefinition`、`LspReferences`、`LspHover`、`LspDocumentSymbols`、`LspWorkspaceSymbols`、`LspDiagnostics`，分别对应 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics 查询。

#### Scenario: 调用 LSP 工具

- **GIVEN** agent 请求 LSP 查询
- **WHEN** 调用任一 LSP 工具
- **THEN** 工具 SHALL NOT 修改工作区文件
- **AND** SHALL 返回受限长度的结构化或可读结果
- **AND** SHALL 受 agent mode 约束（read_only/plan mode 可用，build mode 可用）

#### Scenario: 重复请求复用单例

- **GIVEN** 同一 (language, workspace_root) 的 LSP client 已启动
- **WHEN** 调用另一 LSP 工具查询同语言文件
- **THEN** 系统 SHALL 复用已有 client
- **AND** SHALL NOT 重复启动 server

### Requirement: Write/Edit 成功修改后 SHALL 触发 diagnostics

Write/Edit 成功修改后 SHALL 调用 LSP diagnostics 并把诊断摘要以简单行列表（`path:line:col [severity] message`）追加到工具返回。diagnostics 不可用时 SHALL 快速跳过且不改 Write/Edit 本身行为。修改权限仍由原工具控制，diagnostics 不影响修改是否成功。

#### Scenario: Edit 后附加诊断

- **GIVEN** Edit 成功修改文件且目标语言有可用 LSP server
- **WHEN** Edit 返回结果
- **THEN** 结果 SHALL 包含该文件的 diagnostics 摘要
- **AND** SHALL 标识文件和位置
- **AND** SHALL 对诊断做数量和字符截断

#### Scenario: 无 server 时 Edit 不受影响

- **GIVEN** Edit 成功修改文件但目标语言没有可用 LSP server
- **WHEN** Edit 返回结果
- **THEN** 结果 SHALL NOT 包含 diagnostics
- **AND** SHALL NOT 因 diagnostics 不可用而回滚成功编辑
- **AND** SHALL NOT 等待 LSP 超时
